# mypy: disable-error-code="attr-defined"
"""
LDAP ORM manager and query logic.

This module provides manager, query, and helper classes for interacting with LDAP
servers using Django-like ORM patterns. It includes decorators for atomic LDAP
operations, helpers for modlist construction, and a QuerySet-like F class for
building LDAP queries.
"""

import hashlib
import logging
import os
import re
import threading
import warnings
from base64 import b64encode as encode
from collections import namedtuple
from collections.abc import Callable
from contextlib import suppress

# Handle StrictVersion import for Python < 3.13 and >= 3.13 compatibility
try:
    from distutils.version import StrictVersion  # type: ignore[import]
except ImportError:
    # Python 3.13+ - distutils is removed, use packaging.version
    from packaging.version import Version as StrictVersion  # type: ignore[assignment]

from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Optional, cast

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from ldap import modlist
from ldap.controls import LDAPControl, SimplePagedResultsControl
from ldap_filter import Filter
from pyasn1.codec.ber import encoder  # type: ignore[import]
from pyasn1.type import namedtype, tag, univ  # type: ignore[import]

from ldaporm import ldap

from .typing import AddModlist, LDAPData, ModifyDeleteModList

if TYPE_CHECKING:
    from ldap_filter.filter import GroupAnd

    from .models import Model
    from .options import Options

LDAP24API = StrictVersion(ldap.__version__) >= StrictVersion("2.4")
logger = logging.getLogger("django-ldaporm")


# -----------------------
# LDAP Controls
# -----------------------


# SortKey definition
class SortKey(univ.Sequence):
    """
    SortKey is a sequence of attributeType, orderingRule, and reverseOrder.

    This is used to build the control value for the Server-Side Sort control.

    See RFC 2891 for more details.
    """

    componentType: ClassVar[namedtype.NamedTypes] = namedtype.NamedTypes(  # noqa: N815
        namedtype.NamedType("attributeType", univ.OctetString()),
        namedtype.OptionalNamedType(
            "orderingRule",
            univ.OctetString().subtype(
                explicitTag=tag.Tag(tag.tagClassContext, tag.tagFormatSimple, 0)
            ),
        ),
        namedtype.DefaultedNamedType(
            "reverseOrder",
            univ.Boolean(False).subtype(  # noqa: FBT003
                explicitTag=tag.Tag(tag.tagClassContext, tag.tagFormatSimple, 1)
            ),
        ),
    )


# SortKeyList is a sequence of SortKeys
class SortKeyList(univ.SequenceOf):
    """
    A sequence of SortKeys, used to build the control value for the Server-Side
    Sort control.

    See RFC 2891 for more details.
    """

    componentType: ClassVar[SortKey] = SortKey()  # noqa: N815


def build_sort_control_value(sort_fields: list[str]) -> bytes:
    """
    Build the BER-encoded control value for server-side sorting.

    Args:
        sort_fields: List of attribute names to sort by.

    Returns:
        BER-encoded control value.

    """
    if not sort_fields:
        return b""

    sort_key_list = SortKeyList()

    for field in sort_fields:
        descending = field.startswith("-")
        attr_name = field[1:] if descending else field

        sort_key = SortKey()
        sort_key.setComponentByName(
            "attributeType", univ.OctetString(attr_name.encode("utf-8"))
        )

        if descending:
            sort_key.setComponentByName(
                "reverseOrder",
                univ.Boolean(True).subtype(  # noqa: FBT003
                    explicitTag=tag.Tag(tag.tagClassContext, tag.tagFormatSimple, 1)
                ),
            )

        # If you needed orderingRule, e.g. caseIgnoreOrderingMatch:
        # sort_key.setComponentByName('orderingRule', univ.OctetString('caseIgnoreOrderingMatch'.encode('utf-8')))  # noqa: E501, ERA001

        sort_key_list.append(sort_key)

    return encoder.encode(sort_key_list)


class ServerSideSortControl(LDAPControl):
    """
    LDAP Control Extension for Server-Side Sorting (RFC 2891).

    This control allows the client to request that the server sort the results
    before returning them. The OID 1.2.840.113556.1.4.473 is used by both
    389 Directory Server and Active Directory.
    """

    control_type = "1.2.840.113556.1.4.473"

    def __init__(
        self,
        criticality: bool = False,
        sort_key_list: list[str] | None = None,
    ) -> None:
        """
        Initialize the Server-Side Sort control.

        Args:
            criticality: Whether the control is critical.
            sort_key_list: List of (attribute_name, reverse) tuples for sorting.
                          reverse=True means descending order.

        """
        if sort_key_list is None:
            sort_key_list = []
        # Build the control value according to RFC 2891
        # The control value is a BER-encoded sequence of sort keys
        control_value = build_sort_control_value(sort_key_list)
        super().__init__(self.control_type, criticality, control_value)


# -----------------------
# Decorators
# -----------------------


def atomic(key: str = "read") -> Callable:
    """
    Decorator to wrap methods that need to talk to an LDAP server.

    Args:
        key: Either "read" or "write". Determines which LDAP server to use.

    Returns:
        A decorator that manages LDAP connection context for the wrapped method.

    """

    def real_decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs) -> Callable:
            # add the LDAP server url to our logging context
            if self.has_connection():
                # Ensure we're not currently in a wrapped function
                return func(self, *args, **kwargs)
            self.connect(key)
            try:
                retval = func(self, *args, **kwargs)
            finally:
                # We do this in a finally: branch so that the ldap
                # connection and logger gets cleaned up no matter what
                # happens in `func()`.
                self.disconnect()
            return retval

        return wrapper

    return real_decorator


def substitute_pk(func: Callable) -> Callable:
    """
    Decorator to allow methods to use the kwarg "pk" as a shortcut for the
    primary key.

    Replaces the "pk" kwarg with the actual primary key field name before
    calling the method.

    Args:
        func: The function to wrap.

    Returns:
        The wrapped function with pk substitution.

    """

    @wraps(func)
    def wrapper(self, *args, **kwargs) -> Callable:
        kw = {}
        for key, value in kwargs.items():
            _key = key
            if key == "pk":
                _key = self.pk
            kw[_key] = value
        return func(self, *args, **kw)

    return wrapper


def needs_pk(func: Callable) -> Callable:
    """
    Decorator to ensure the primary key attribute is included in LDAP queries.

    Ensures that the primary key is present in the attribute list before
    executing the LDAP search.

    Args:
        func: The function to wrap.

    Returns:
        The wrapped function with primary key enforcement.

    """

    @wraps(func)
    def wrapper(self, *args, **kwargs) -> Callable:
        pk_attr = self.get_attribute(self.manager.pk)
        if pk_attr not in self._attributes:
            self._attributes.append(pk_attr)
        return func(self, *args, **kwargs)

    return wrapper


# -----------------------
# Helper Classes
# -----------------------


class Modlist:
    """
    Helper for constructing LDAP modlists for add, update, and delete operations.

    Args:
        manager: The LdapManager instance this modlist is associated with.

    """

    def __init__(self, manager: "LdapManager") -> None:
        self.manager = manager

    def _get_modlist(
        self,
        data: dict[str, Any],
        modtype: int = ldap.MOD_REPLACE,  # type: ignore[attr-defined]
    ) -> ModifyDeleteModList:  # type: ignore[attr-defined]
        """
        Build a modlist for LDAP operations.

        Args:
            data: Dictionary of attribute names and values.
            modtype: LDAP modification type (MOD_REPLACE, MOD_DELETE, MOD_ADD).

        Returns:
            A list of LDAP modifications suitable for python-ldap.

        """
        _modlist: ModifyDeleteModList = []
        for key, value in data.items():
            if modtype == ldap.MOD_DELETE:  # type: ignore[attr-defined]
                _modlist.append((ldap.MOD_DELETE, key, None))  # type: ignore[attr-defined]
            elif modtype == ldap.MOD_ADD:  # type: ignore[attr-defined]
                _modlist.append((key, value))
            else:
                _modlist.append((cast("int", modtype), key, value))
        return _modlist

    def add(self, obj: "Model") -> AddModlist:
        """
        Convert an LDAP DAO object to a modlist suitable for passing to `add_s`.

        Args:
            obj: The model instance to add.

        Returns:
            The modlist for the add operation.

        Raises:
            ImproperlyConfigured: If the object has no objectclasses defined.

        """
        data = obj.to_db()
        if hasattr(obj, "objectclass"):
            data[1]["objectclass"] = obj.objectclass  # type: ignore[index]
        else:
            msg = "Tried to add an object with no objectclasses defined."
            raise ImproperlyConfigured(msg)
        # We have to do these two casts because LdapManager.model and
        # Model._meta start out as None.  By the time we get here the metaclass
        # has filled in those two so we know they're not None, but mypy has no
        # way of knowing that
        model = cast("Model", self.manager.model)
        _meta = cast("Options", model._meta)
        _attribute_lookup = _meta.attribute_to_field_name_map
        _fields_map = _meta.fields_map
        # purge the empty fields
        new = {}
        for key, value in data[1].items():
            field = _fields_map[_attribute_lookup[key]]
            if not field.editable and key != "objectclass":
                continue
            if value != []:
                new[key] = value
        return modlist.addModlist(new)

    def update(
        self,
        new: "Model",
        old: "Model",
        force: bool = False,  # noqa: ARG002
    ) -> ModifyDeleteModList:
        """
        Build a modlist for updating an LDAP object, using MOD_DELETE or
        MOD_REPLACE as needed.

        Args:
            new: The new model instance data.
            old: The old model instance data.
            force: Whether to force the update even if unchanged.

        Returns:
            A list of LDAP modifications to apply to the object.

        """
        # We have to do these two casts because LdapManager.model and
        # Model._meta start out as None.  By the time we get here the metaclass
        # has filled in those two so we know they're not None, but mypy has no
        # way of knowing that
        model = cast("Model", self.manager.model)
        _meta = cast("Options", model._meta)
        _attribute_lookup = _meta.attribute_to_field_name_map
        _fields_map = _meta.fields_map
        # first build the changed attributes
        old_data = old.to_db()
        new_data = new.to_db()
        changes = {}
        for key, value in new_data[1].items():
            field = _fields_map[_attribute_lookup[key]]
            if not field.editable:
                continue

            if old_data[1][key] != value:
                changes[key] = value

        # Now build the ldap.MOD_DELETE and ldap.MOD_REPLACE modlists
        deletes: dict[str, Any] = {}
        replacements: dict[str, Any] = {}
        for key, value in changes.items():
            if value == [] or all(x is None for x in value):
                deletes[key] = None
            else:
                replacements[key] = value
        d_modlist = self._get_modlist(deletes, ldap.MOD_DELETE)  # type: ignore[attr-defined]
        r_modlist = self._get_modlist(replacements, ldap.MOD_REPLACE)  # type: ignore[attr-defined]
        return r_modlist + d_modlist


# ========================================
# The LDAP search filter QuerySet analog
# ========================================


class F:
    """
    QuerySet-like class for building LDAP search filters and queries.

    This class allows chaining of filter, order, and attribute selection methods
    to construct LDAP queries in a Django-like fashion.

    Args:
        manager: The LdapManager instance this query is associated with.
        f: An optional F instance to chain from.

    """

    class NoFilterSpecified(Exception):
        """Raised when no filter is specified for an LDAP search."""

    class UnknownSuffix(Exception):
        """Raised when an unknown filter suffix is used in a query."""

    class UnboundFilter(Exception):
        """Raised when a filter is not bound to a manager."""

    def __init__(
        self, manager: Optional["LdapManager"] = None, f: Optional["F"] = None
    ) -> None:
        self.manager: LdapManager | None = manager
        self.model: type[Model] | None = None
        self._meta: Options | None = None
        self.fields_map: dict[str, Any] | None = None
        self.attributes_map: dict[str, str] | None = None
        self.attribute_to_field_name_map: dict[str, str] | None = None
        self.attributes: list[str] | None = None
        self._attributes: list[str] | None = None
        self._order_by: list[str] | None = None
        self.chain: list[
            Any
        ] = []  # Changed from list[F] to list[Any] to handle filter objects
        self._exclude_chain: list[Any] = []  # Track exclude conditions separately
        self._exclude_groups: list[list[Any]] = []  # Track exclude conditions in groups
        if manager is not None:
            self.model = cast("type[Model]", manager.model)
            self._meta = cast("Options", self.model._meta)
            self.fields_map = self._meta.fields_map
            self.attributes_map = self._meta.attributes_map
            self.attribute_to_field_name_map = self._meta.attribute_to_field_name_map
            self.attributes = self._meta.attributes
            self._attributes = self.attributes
            self._order_by = self._meta.ordering
        if f is not None:
            self.chain = list(f.chain)
            self._exclude_chain = list(f._exclude_chain)
            self._exclude_groups = list(f._exclude_groups)
        else:
            self.chain = []
            self._exclude_chain = []
            self._exclude_groups = []

    def bind_manager(self, manager: "LdapManager") -> None:
        if manager is None:
            msg = "Cannot bind F to a None manager."
            raise F.UnboundFilter(msg)
        if self.manager is None:
            self.manager = manager
            self.model = cast("type[Model]", manager.model)
            self._meta = cast("Options", self.model._meta)
            self.fields_map = self._meta.fields_map
            self.attributes_map = self._meta.attributes_map
            self.attribute_to_field_name_map = self._meta.attribute_to_field_name_map
            self.attributes = self._meta.attributes
            self._attributes = self.attributes
            self._order_by = self._meta.ordering

    def _require_manager(self):
        if (
            self.manager is None
            or self.model is None
            or self._meta is None
            or self.fields_map is None
            or self.attributes_map is None
            or self.attribute_to_field_name_map is None
            or self.attributes is None
            or self._attributes is None
            or self._order_by is None
        ):
            msg = (
                "F instance is not bound to a manager. Pass it to a manager's "
                "filter() method or use F(manager)."
            )
            raise F.UnboundFilter(msg)

        # Ensure _attributes is not None for type checker
        if self._attributes is None:
            self._attributes = []

        # Ensure _exclude_chain is not None for type checker
        if self._exclude_chain is None:
            self._exclude_chain = []

        # Ensure _exclude_groups is not None for type checker
        if self._exclude_groups is None:
            self._exclude_groups = []

    def _execute_query(self) -> list["Model"]:
        """
        Execute the query and return the results as a list.

        Returns:
            A list of model instances matching the query.

        """
        self._require_manager()
        sort_control = self._create_sort_control()
        objects = cast("Model", self.model).from_db(
            cast("list[str]", self._attributes),
            cast("LdapManager", self.manager).search(
                str(self),
                cast("list[str]", self._attributes),
                sort_control=sort_control,
            ),
            many=True,
        )

        # If we have ordering but no sort control was created (server doesn't
        # support it), or if we have ordering and got a list of objects, apply
        # client-side sorting
        if self._order_by and (sort_control is None or isinstance(objects, list)):
            objects = self._sort_objects_client_side(cast("list[Model]", objects))

        return cast("list[Model]", objects)

    @property
    def _filter(self) -> "GroupAnd":  # noqa: PLR0912
        """
        Return a list of filters ready to be converted to a filter string.

        Returns:
            A GroupAnd filter object representing the current filter chain.

        Raises:
            NoFilterSpecified: If no filters are specified.

        """
        if len(self.chain) == 0 and len(self._exclude_groups) == 0:
            # No filters specified - return a filter that matches everything
            return Filter.attribute("objectClass").present()

        # Build the main filter from the chain
        if len(self.chain) == 0:
            main_filter = None
        elif len(self.chain) == 1:
            main_filter = self.chain[0]
        else:
            main_filter = Filter.AND(self.chain).simplify()

        # Build the exclude filter from the exclude groups
        if len(self._exclude_groups) == 0:
            exclude_filter = None
        elif len(self._exclude_groups) == 1:
            # Single exclude group
            group = self._exclude_groups[0]
            if len(group) == 1:
                exclude_filter = Filter.NOT(group[0])
            else:
                # Multiple conditions in single exclude call: combine with AND
                exclude_filter = Filter.NOT(Filter.AND(group).simplify())
        else:
            # Multiple exclude groups: combine each group with AND, then combine
            # groups with OR
            group_filters = []
            for group in self._exclude_groups:
                if len(group) == 1:
                    group_filters.append(Filter.NOT(group[0]))
                else:
                    # Multiple conditions in group: combine with AND
                    group_filters.append(Filter.NOT(Filter.AND(group).simplify()))
            # Combine groups with AND
            exclude_filter = Filter.AND(group_filters).simplify()

        # Combine main filter and exclude filter
        if main_filter is None and exclude_filter is None:
            msg = (
                "You need to at least specify one filter in order to do LDAP searches."
            )
            raise self.NoFilterSpecified(msg)
        if main_filter is None:
            return exclude_filter  # type: ignore[return-value]
        if exclude_filter is None:
            return main_filter  # type: ignore[return-value]
        # Combine with AND: (main_filter) AND NOT (exclude_conditions)
        return Filter.AND([main_filter, exclude_filter]).simplify()

    def _create_sort_control(self) -> ServerSideSortControl | None:
        """
        Create a server-side sort control for LDAP queries if supported by the
        server and ordering is specified.

        Returns:
            ServerSideSortControl if supported and ordering is specified,
            otherwise None.

        Raises:
            F.UnboundFilter: If the F instance is not bound to a manager.

        """
        self._require_manager()
        if not self._order_by:
            return None
        if self.manager is None:
            msg = "F instance is not bound to a manager."
            raise F.UnboundFilter(msg)
        if not self.manager._check_server_sorting_support():
            return None
        return ServerSideSortControl(sort_key_list=self._order_by)

    def _sort_objects_client_side(self, objects: list["Model"]) -> list["Model"]:
        """
        Sort a list of model instances client-side according to the specified ordering.

        Args:
            objects: The list of model instances to sort.

        Returns:
            The sorted list of model instances.

        """
        self._require_manager()
        order_by = cast("list[str]", self._order_by)
        if not order_by:
            return objects

        def get_sort_key(obj, key):
            """Get sort key value, handling None values."""
            value = getattr(obj, key)
            # Handle None values by treating them as less than any other value
            if value is None:
                return (0, None)  # (0, None) sorts before (1, actual_value)
            return (1, value)  # (1, actual_value) sorts after (0, None)

        if not any(k.startswith("-") for k in order_by):
            return sorted(
                objects, key=lambda obj: tuple(get_sort_key(obj, k) for k in order_by)
            )
        keys = list(order_by)
        keys.reverse()
        for k in keys:
            key = k
            reverse = False
            if key.startswith("-"):
                key = k[1:]
                reverse = True
            objects = sorted(
                objects,
                key=lambda obj: get_sort_key(obj, key),
                reverse=reverse,
            )
        return objects

    def __validate_positional_args(self, args: list["F"]) -> list["F"]:
        """
        Validate that all positional arguments are F instances.

        Args:
            args: List of arguments to validate.

        Returns:
            List of F instances.

        Raises:
            TypeError: If any argument is not an F instance.

        """
        if args:
            for arg in args:
                if not isinstance(arg, F):
                    msg = "F.filter() positional arguments must all be F() objects."
                    raise TypeError(msg)
        return list(args)

    def get_attribute(self, name: str) -> str:
        self._require_manager()
        return self.attributes_map[name]  # type: ignore[index]

    def wildcard(self, name: str, value: str) -> "F":
        """
        Convert a value with wildcards to an appropriate LDAP filter and apply it.

        Args:
            name: The name of the field to filter on.
            value: The value to filter with wildcards.

        Returns:
            A new chained F object with the wildcard filter applied.

        """
        value = value.strip()
        f = self
        if value:
            if value.startswith("*") and value.endswith("*"):
                qualifier = f"{name}__icontains"
            elif value.startswith("*"):
                qualifier = f"{name}__iendswith"
            elif value.endswith("*"):
                qualifier = f"{name}__istartswith"
            else:
                qualifier = f"{name}__iexact"
            d = {qualifier: re.sub(r"[*]", "", value)}
            f = self.filter(**d)
        return f

    def filter(self, *args, **kwargs) -> "F":  # noqa: PLR0912, PLR0915
        self._require_manager()
        manager = cast("LdapManager", self.manager)

        # Handle positional arguments (F objects)
        bound_args = []
        for arg in args:
            if isinstance(arg, F) and arg.manager is None:
                arg.bind_manager(manager)
            bound_args.append(arg)

        # Create a new F instance with the current chain
        new_f = F(manager, self)

        # Add positional F objects to the chain
        for arg in bound_args:
            if isinstance(arg, F):
                new_f.chain.extend(arg.chain)

        # Process keyword arguments to create filters
        for key, value in kwargs.items():
            if "__" in key:
                field_name, suffix = key.split("__", 1)
            else:
                field_name = key
                suffix = "iexact"

            # Validate field exists
            if field_name not in cast("dict[str, str]", self.attributes_map):
                msg = (
                    f'"{field_name}" is not a valid field on model '
                    f"{cast('type[Model]', self.model).__name__}"
                )
                raise cast("type[Model]", self.model).InvalidField(msg)

            # Get the LDAP attribute name
            attr_name = self.get_attribute(field_name)

            # Handle different filter suffixes
            if suffix == "iexact":
                if value is None:
                    # Filter for attributes that don't exist
                    filter_obj = Filter.NOT(Filter.attribute(attr_name).present())
                else:
                    filter_obj = Filter.attribute(attr_name).equal_to(value)
            elif suffix == "icontains":
                filter_obj = Filter.attribute(attr_name).contains(value)
            elif suffix == "istartswith":
                filter_obj = Filter.attribute(attr_name).starts_with(value)
            elif suffix == "iendswith":
                filter_obj = Filter.attribute(attr_name).ends_with(value)
            elif suffix == "exists":
                if value:
                    filter_obj = Filter.attribute(attr_name).present()
                else:
                    filter_obj = Filter.NOT(Filter.attribute(attr_name).present())
            elif suffix == "in":
                if not isinstance(value, list):
                    msg = 'When using the "__in" filter you must supply a list'
                    raise ValueError(msg)
                # Handle empty list case
                if not value:
                    # Empty list means no exclusions, so skip this filter
                    continue
                # OR together equal_to filters for each value
                filter_obj = Filter.OR(
                    [Filter.attribute(attr_name).equal_to(v) for v in value]
                )
            elif suffix in ["gt", "gte", "lt", "lte"]:
                # Integer comparisons
                self._validate_integer_field(field_name)
                attr_obj = Filter.attribute(attr_name)
                if suffix == "gt":
                    # For gt, use gte with value+1
                    if isinstance(value, int):
                        filter_obj = attr_obj.gte(value + 1)
                    else:
                        msg = f'Filter suffix "{suffix}" requires an integer value'
                        raise ValueError(msg)
                elif suffix == "gte":
                    filter_obj = attr_obj.gte(value)
                elif suffix == "lt":
                    # For lt, use lte with value-1
                    if isinstance(value, int):
                        filter_obj = attr_obj.lte(value - 1)
                    else:
                        msg = f'Filter suffix "{suffix}" requires an integer value'
                        raise ValueError(msg)
                elif suffix == "lte":
                    filter_obj = attr_obj.lte(value)
            else:
                msg = f'Unknown filter suffix: "{suffix}"'
                raise self.UnknownSuffix(msg)

            # Add the filter to the chain
            new_f.chain.append(filter_obj)

        return new_f

    def _validate_integer_field(self, field_name: str) -> None:
        """
        Validate that a field is an IntegerField or subclass.

        Args:
            field_name: The name of the field to validate.

        Raises:
            TypeError: If the field is not an IntegerField or subclass.

        """
        from .fields import IntegerField

        fields_map = cast("dict[str, Any]", self.fields_map)
        field = fields_map.get(field_name)
        if not field or not isinstance(field, IntegerField):
            msg = (
                f"Integer comparison methods (__gt, __gte, __lt, __lte) can only be "
                f'used on IntegerField or its subclasses. Field "{field_name}" is not '
                "an integer field."
            )
            raise TypeError(msg)

    def only(self, *names) -> "F":
        """
        Restrict the query to only the specified attributes.

        Args:
            *names: Field names to include in the query.

        Returns:
            The F object with restricted attributes.

        Raises:
            InvalidField: If any name is not a valid field for the model.

        """
        self._require_manager()
        self._attributes = [self.get_attribute(name) for name in names]
        return self

    @needs_pk
    def first(self) -> "Model":
        """
        Return the first result of the query, or raise DoesNotExist if none found.

        Returns:
            The first model instance matching the query.

        Raises:
            DoesNotExist: If no objects match the query.

        """
        self._require_manager()
        sizelimit = 1
        sort_control = self._create_sort_control()
        objects = cast("LdapManager", self.manager).search(
            str(self),
            cast("list[str]", self._attributes),
            sizelimit=sizelimit,
            sort_control=sort_control,
        )
        if len(objects) == 0:
            msg = (
                f"A {cast('type[Model]', self.model).__name__} object matching query "
                "does not exist."
            )
            raise cast("type[Model]", self.model).DoesNotExist(msg)
        objects = cast("type[Model]", self.model).from_db(
            cast("list[str]", self._attributes), objects, many=True
        )
        if isinstance(objects, list):
            return objects[0]
        return objects

    @needs_pk
    def get(self, *args, **kwargs) -> "Model":
        """
        Return the single result of the query, or raise
        DoesNotExist/MultipleObjectsReturned.  Accepts kwargs for filtering.

        Args:
            *args: Positional filter arguments.

        Keyword Args:
            **kwargs: Keyword filter arguments.

        Returns:
            The single model instance matching the query.

        Raises:
            LdapManager.DoesNotExist: If no object matches the query.
            LdapManager.MultipleObjectsReturned: If more than one object matches
                the query.

        """
        if kwargs:
            return self.filter(**kwargs).get(*args)
        # No kwargs: use the original logic
        self._require_manager()
        manager = cast("LdapManager", self.manager)
        model = cast("type[Model]", self.model)
        attributes = cast("list[str]", self._attributes)
        objects = manager.search(str(self), attributes)
        if len(objects) == 0:
            msg = f"A {model.__name__} object matching query does not exist."
            raise model.DoesNotExist(msg)
        if len(objects) > 1:
            msg = f"More than one {model.__name__} object matched query."
            raise model.MultipleObjectsReturned(msg)
        return cast("Model", model.from_db(attributes, objects))

    def get_or_none(self, *args, **kwargs) -> "Model | None":
        """
        Return the single result of the query, or None if not exactly one found.
        Accepts kwargs for filtering.
        """
        try:
            return self.get(*args, **kwargs)
        except (
            cast("type[Model]", self.model).DoesNotExist,
            cast("type[Model]", self.model).MultipleObjectsReturned,
        ):
            return None

    def first_or_none(self, *args, **kwargs) -> "Model | None":
        """
        Return the first result of the query, or None if no match.
        Accepts kwargs for filtering.
        """
        if kwargs:
            return self.filter(**kwargs).first_or_none(*args)
        try:
            return self.first(*args)
        except (cast("type[Model]", self.model).DoesNotExist, IndexError):
            return None

    def _get_single_result(self, *args):
        # Call the logic directly (no super())
        return self.get(*args)

    @needs_pk
    def update(self, **kwargs) -> None:
        """
        Update the object matching the query with the given attributes.

        Args:
            **kwargs: Field names and values to update.

        """
        self._require_manager()
        obj = self.get()
        manager = cast("LdapManager", self.manager)
        model = cast("type[Model]", self.model)
        attributes = cast("list[str]", self._attributes)
        attributes_list = cast("list[str]", self.attributes)
        # Create a new instance with the current data
        new = model.from_db(attributes, obj.to_db())
        for key, value in kwargs.items():
            if key in attributes_list:
                setattr(new, key, value)
        manager.modify(new, old=obj)  # type: ignore[arg-type]

    def exists(self) -> bool:
        """
        Return True if the query returns any results, False otherwise.

        Returns:
            True if any objects match the query, False otherwise.

        """
        self._require_manager()
        manager = cast("LdapManager", self.manager)
        attributes = cast("list[str]", self._attributes)
        objects = manager.search(str(self), attributes)
        return len(objects) > 0

    @needs_pk
    def all(self) -> "F":
        """
        Return the F object itself for compatibility with Django REST Framework.

        Returns:
            The F object itself, which is iterable and supports pagination.

        """
        return self

    def page(self, page_size: int = 100, cookie: str = "") -> "PagedResultSet":
        """
        Return a single page of results matching the query.

        This method performs a paged LDAP search and returns both the results
        and metadata needed for pagination.

        Args:
            page_size: Number of results per page.
            cookie: Paging cookie from the previous page (empty string for first page).

        Returns:
            A PagedResultSet containing the results and pagination metadata.

        """
        self._require_manager()
        sort_control = self._create_sort_control()

        results, next_cookie = cast("LdapManager", self.manager).search_page(
            str(self),
            cast("list[str]", self._attributes),
            page_size=page_size,
            cookie=cookie,
            sort_control=sort_control,
        )

        objects = cast("Model", self.model).from_db(
            cast("list[str]", self._attributes),
            results,
            many=True,
        )

        # If we have ordering but no sort control was created (server doesn't
        # support it), or if we have ordering and got a list of objects, apply
        # client-side sorting
        if self._order_by and (sort_control is None or isinstance(objects, list)):
            objects = self._sort_objects_client_side(cast("list[Model]", objects))

        return PagedResultSet(
            results=cast("list[Model]", objects),
            next_cookie=next_cookie,
            has_more=bool(next_cookie),
        )

    def count(self) -> int:
        """
        Return the number of objects for this model from LDAP.

        Returns:
            The count of all model instances from LDAP.

        """
        return len(self.all())

    def as_list(self) -> list["Model"]:
        """
        Return a list of all objects for this model from LDAP.

        Returns:
            A list of all model instances from LDAP.

        """
        return self._execute_query()

    def delete(self) -> None:
        """
        Delete the object matching the query.

        Raises:
            DoesNotExist: If no objects match the query.
            MultipleObjectsReturned: If more than one object matches the query.

        """
        self._require_manager()
        obj = self.get()
        cast("LdapManager", self.manager).delete_obj(obj)

    def order_by(self, *args: str) -> "F":
        """
        Set the ordering for the query results.

        Args:
            *args: Field names to order by (use '-' prefix for descending).

        Returns:
            The F object with ordering applied.

        Raises:
            InvalidField: If any field is not valid for the model.

        """
        self._require_manager()
        for key in args:
            _key = key.removeprefix("-")
            if self.attributes_map is None or _key not in self.attributes_map:
                name = cast("type[Model]", self.model).__name__
                msg = f'"{_key}" is not a valid field on model {name}'
                raise cast("type[Model]", self.model).InvalidField(msg)
        self._order_by = list(args)
        return self

    def values(self, *attrs: str) -> list[dict[str, Any]]:
        """
        Return a list of dictionaries representing the query results.

        Args:
            *attrs: Field names to include in the dictionaries.

        Returns:
            A list of dictionaries, one per object.

        Raises:
            NotImplementedError: If .only() was used with .values().

        """
        self._require_manager()
        if self._attributes != self.attributes:
            msg = "Don't use .only() with .values()"
            raise NotImplementedError(msg)

        # Determine which attributes to fetch and which field names to use as keys
        if not attrs:
            # If no attrs specified, use all attributes and field names
            ldap_attrs = self.attributes
            field_names = [
                cast("dict[str, str]", self.attribute_to_field_name_map)[attr]
                for attr in cast("list[str]", ldap_attrs)
            ]
        else:
            # If attrs specified, convert to LDAP attributes
            ldap_attrs = [self.get_attribute(attr) for attr in attrs]
            field_names = list(attrs)

        sort_control = self._create_sort_control()
        objects = cast("Model", self.model).from_db(
            cast("list[str]", ldap_attrs),
            cast("LdapManager", self.manager).search(
                str(self), cast("list[str]", ldap_attrs), sort_control=sort_control
            ),
            many=True,
        )

        # If we have ordering but no sort control was created (server doesn't
        # support it), or if we have ordering and got a list of objects, apply
        # client-side sorting
        if self._order_by and (sort_control is None or isinstance(objects, list)):
            objects = self._sort_objects_client_side(cast("list[Model]", objects))

        if isinstance(objects, list):
            return [
                {field_name: getattr(obj, field_name) for field_name in field_names}
                for obj in objects
            ]
        return [
            {field_name: getattr(objects, field_name) for field_name in field_names}
        ]

    def values_list(self, *attrs: str, **kwargs) -> list[tuple[Any, ...]]:
        """
        Return a list of tuples (or namedtuples) representing the query results.

        Args:
            *attrs: Field names to include in the tuples.
            **kwargs: 'flat' for single-value tuples, 'named' for namedtuples.

        Returns:
            A list of tuples or namedtuples, one per object.

        Raises:
            NotImplementedError: If .only() was used with .values_list().
            ValueError: If flat=True is used with more than one field.

        """
        self._require_manager()
        if self._attributes != self.attributes:
            msg = "Don't use .only() with .values_list()"
            raise NotImplementedError(msg)

        _attrs: list[str] = []
        if not attrs:
            _attrs = self.attributes  # type: ignore[assignment]
            attrs = tuple(
                cast("dict[str, str]", self.attribute_to_field_name_map)[attr]
                for attr in _attrs
            )
        else:
            _attrs = [self.get_attribute(attr) for attr in attrs]
        sort_control = self._create_sort_control()
        objects = cast("Model", self.model).from_db(
            _attrs,
            cast("LdapManager", self.manager).search(
                str(self), _attrs, sort_control=sort_control
            ),
            many=True,
        )

        # If we have ordering but no sort control was created (server doesn't
        # support it), or if we have ordering and got a list of objects, apply
        # client-side sorting
        if self._order_by and (sort_control is None or isinstance(objects, list)):
            objects = self._sort_objects_client_side(cast("list[Model]", objects))

        if kwargs.get("flat"):
            if len(attrs) > 1:
                msg = "Cannot use flat=True when asking for more than one field"
                raise ValueError(msg)
            if isinstance(objects, list):
                return [getattr(obj, attrs[0]) for obj in objects]  # type: ignore[return-value]
            return [getattr(objects, attrs[0])]  # type: ignore[index]
        if kwargs.get("named"):
            # Dynamic namedtuple creation: attrs is not a literal, but this
            # is valid for runtime use.
            Row = namedtuple("Row", tuple(attrs))  # type: ignore[misc]  # noqa: PYI024
            if isinstance(objects, list):
                return [
                    Row(**{attr: getattr(obj, attr) for attr in attrs})
                    for obj in objects
                ]
            return [Row(**{attr: getattr(objects, attr) for attr in attrs})]
        if isinstance(objects, list):
            return [tuple(getattr(obj, attr) for attr in attrs) for obj in objects]
        return [tuple(getattr(objects, attr) for attr in attrs)]

    def __or__(self, other: "F") -> "F":
        """
        Combine this filter with another using logical OR.

        Args:
            other: Another F object to combine with.

        Returns:
            A new F object representing the OR of both filters.

        """
        self._require_manager()
        other._require_manager()
        new_f = F(self.manager)
        # For OR, we need to create a single OR filter containing both filter chains
        if len(self.chain) == 1 and len(other.chain) == 1:
            # Simple case: single filter on each side
            new_f.chain = [Filter.OR([self.chain[0], other.chain[0]])]
        else:
            # Complex case: multiple filters on either side
            # Create AND filters for each side, then OR them together
            left_filter = self._filter
            right_filter = other._filter
            new_f.chain = [Filter.OR([left_filter, right_filter])]
        return new_f

    def __and__(self, other: "F") -> "F":
        """
        Combine this filter with another using logical AND.

        Args:
            other: Another F object to combine with.

        Returns:
            A new F object representing the AND of both filters.

        """
        self._require_manager()
        other._require_manager()
        new_f = F(self.manager)
        # For AND, we can just concatenate the filter chains
        # The _filter property will handle creating the proper AND filter
        new_f.chain = list(self.chain) + list(other.chain)
        return new_f

    def __str__(self) -> str:
        """
        Return the LDAP filter string for this query.

        Returns:
            The LDAP filter string.

        """
        self._require_manager()
        return self._filter.to_string()

    def __iter__(self) -> "FIterator":
        """
        Make F instances iterable, automatically executing the query.

        Returns:
            An iterator over the query results.

        """
        return FIterator(self._execute_query())

    def __len__(self) -> int:
        """
        Return the number of objects matching the query.

        Returns:
            The count of matching objects.

        """
        return len(self._execute_query())

    def __getitem__(self, key: int | slice) -> "Model | list[Model]":
        """
        Support indexing and slicing of query results.

        Args:
            key: Integer index or slice.

        Returns:
            The object at the given index or slice of objects.

        """
        if isinstance(key, slice):
            # Handle slicing
            if (
                key.start is None
                and key.step is None
                and key.stop is not None
                and (isinstance(key.stop, int) and key.stop >= 0)
            ):
                return self._fetch_with_sizelimit(key.stop)
            # Inefficient case: fetch all, then slice in Python
            objects = self._execute_query()
            return objects[key]
        # Single index: fetch all, then index
        objects = self._execute_query()
        return objects[key]

    def _fetch_with_sizelimit(self, limit: int) -> list["Model"]:
        """
        Fetch results with a size limit for efficient slicing.

        Args:
            limit: Maximum number of results to fetch.

        Returns:
            List of model instances up to the limit.

        """
        self._require_manager()
        sort_control = self._create_sort_control()
        objects = cast("Model", self.model).from_db(
            cast("list[str]", self._attributes),
            cast("LdapManager", self.manager).search(
                str(self),
                cast("list[str]", self._attributes),
                sizelimit=0,  # Fetch all, apply limit after sorting if needed
                sort_control=sort_control,
            ),
            many=True,
        )

        # If we have ordering but no sort control was created (server doesn't
        # support it), or if we have ordering and got a list of objects, apply
        # client-side sorting
        if self._order_by and (sort_control is None or isinstance(objects, list)):
            objects = self._sort_objects_client_side(cast("list[Model]", objects))

        # Apply the limit after sorting
        if limit is not None and limit >= 0:
            objects = cast("list[Model]", objects)[:limit]

        return cast("list[Model]", objects)

    def exclude(self, *args, **kwargs) -> "F":  # noqa: PLR0912, PLR0915
        """
        Return a new F object with exclude conditions applied.

        Exclude conditions are applied as NOT conditions to the final filter.
        Multiple exclude conditions are combined with AND logic.

        Args:
            *args: Positional filter arguments (F objects to exclude)
            **kwargs: Keyword filter arguments to exclude

        Returns:
            A new F object with exclude conditions applied.

        Note:
            Exclude conditions are applied after filter conditions.
            The final LDAP filter will be: (filter_conditions) AND NOT
            (exclude_conditions)

        """
        self._require_manager()
        manager = cast("LdapManager", self.manager)

        # Handle positional arguments (F objects)
        bound_args = []
        for arg in args:
            if isinstance(arg, F) and arg.manager is None:
                arg.bind_manager(manager)
            bound_args.append(arg)

        # Create a new F instance with the current chain and exclude chain
        new_f = F(manager, self)

        # Add positional F objects to the exclude groups
        for arg in bound_args:
            if isinstance(arg, F):
                # Each F object's chain becomes a separate exclude group
                if arg.chain:
                    new_f._exclude_groups.append(arg.chain)

        # Process keyword arguments to create exclude filters
        exclude_filters = []
        for key, value in kwargs.items():
            if "__" in key:
                field_name, suffix = key.split("__", 1)
            else:
                field_name = key
                suffix = "iexact"

            # Validate field exists
            if field_name not in cast("dict[str, str]", self.attributes_map):
                msg = (
                    f'"{field_name}" is not a valid field on model '
                    f"{cast('type[Model]', self.model).__name__}"
                )
                raise cast("type[Model]", self.model).InvalidField(msg)

            # Get the LDAP attribute name
            attr_name = self.get_attribute(field_name)

            # Handle different filter suffixes (same logic as filter, but for exclude)
            if suffix == "iexact":
                if value is None:
                    # Exclude attributes that don't exist (i.e., exclude users
                    # where attribute is NOT present) This creates a filter that
                    # matches users where the attribute is NOT present
                    filter_obj = Filter.attribute(attr_name).present()
                else:
                    filter_obj = Filter.attribute(attr_name).equal_to(value)
            elif suffix == "icontains":
                filter_obj = Filter.attribute(attr_name).contains(value)
            elif suffix == "istartswith":
                filter_obj = Filter.attribute(attr_name).starts_with(value)
            elif suffix == "iendswith":
                filter_obj = Filter.attribute(attr_name).ends_with(value)
            elif suffix == "exists":
                if value:
                    filter_obj = Filter.attribute(attr_name).present()
                else:
                    filter_obj = Filter.NOT(Filter.attribute(attr_name).present())
            elif suffix == "in":
                if not isinstance(value, list):
                    msg = 'When using the "__in" filter you must supply a list'
                    raise ValueError(msg)
                # Handle empty list case
                if not value:
                    # Empty list means no exclusions, so skip this filter
                    continue
                # OR together equal_to filters for each value
                filter_obj = Filter.OR(
                    [Filter.attribute(attr_name).equal_to(v) for v in value]
                )
            elif suffix in ["gt", "gte", "lt", "lte"]:
                # Integer comparisons
                self._validate_integer_field(field_name)
                attr_obj = Filter.attribute(attr_name)
                if suffix == "gt":
                    # For gt, use gte with value+1
                    if isinstance(value, int):
                        filter_obj = attr_obj.gte(value + 1)
                    else:
                        msg = f'Filter suffix "{suffix}" requires an integer value'
                        raise ValueError(msg)
                elif suffix == "gte":
                    filter_obj = attr_obj.gte(value)
                elif suffix == "lt":
                    # For lt, use lte with value-1
                    if isinstance(value, int):
                        filter_obj = attr_obj.lte(value - 1)
                    else:
                        msg = f'Filter suffix "{suffix}" requires an integer value'
                        raise ValueError(msg)
                elif suffix == "lte":
                    filter_obj = attr_obj.lte(value)
            else:
                msg = f'Unknown filter suffix: "{suffix}"'
                raise self.UnknownSuffix(msg)

            # Add the filter to the exclude filters list
            exclude_filters.append(filter_obj)

            # Add exclude filters as a group
        # Multiple conditions within a single exclude call are combined with AND
        # Skip empty groups
        if exclude_filters:
            new_f._exclude_groups.append(exclude_filters)

        return new_f


class FIterator:
    """
    Iterator for F objects.

    This class provides iteration over the results of an F query.
    """

    def __init__(self, objects: list["Model"]) -> None:
        """
        Initialize the iterator.

        Args:
            objects: List of model instances to iterate over.

        """
        self.objects = objects
        self.index = 0

    def __iter__(self) -> "FIterator":
        """
        Return self as an iterator.

        Returns:
            Self as an iterator.

        """
        return self

    def __next__(self) -> "Model":
        """
        Get the next model instance.

        Returns:
            The next model instance.

        Raises:
            StopIteration: When there are no more objects to iterate over.

        """
        if self.index >= len(self.objects):
            raise StopIteration
        obj = self.objects[self.index]
        self.index += 1
        return obj


class PagedResultSet:
    """
    Represents a single page of LDAP search results.

    This class encapsulates the results of a paged LDAP search along with
    metadata needed for pagination.
    """

    def __init__(self, results: list["Model"], next_cookie: str, has_more: bool):
        """
        Initialize the paged result set.

        Args:
            results: List of model instances for this page.
            next_cookie: Cookie for the next page (empty string if no more pages).
            has_more: Whether there are more pages available.

        """
        self.results = results
        self.next_cookie = next_cookie
        self.has_more = has_more

    def __iter__(self):
        """Iterate over the results."""
        return iter(self.results)

    def __len__(self) -> int:
        """Return the number of results in this page."""
        return len(self.results)

    def __getitem__(self, key):
        """Get a result by index."""
        return self.results[key]


# -----------------------
# LdapManager
# -----------------------


class LdapManager:
    """
    Manager class for direct interactions with LDAP servers.

    This class provides methods for connecting, searching, adding, modifying,
    and deleting LDAP objects, as well as utility methods for authentication and
    password management.  It is intended to be used as the main interface for
    LDAP-backed Django ORM models.

    This class handles connecting to the LDAP server, searching, adding,
    modifying, and deleting LDAP objects.  It also handles authentication and
    password management.

    This class is thread-safe -- it will use a different LDAP connection for
    each thread.  This is important because LDAP connections are not thread-safe.
    If you use the same connection in multiple threads, you will get errors.

    """

    #: Class-level cache for server-side sorting capability per server configuration
    _server_sorting_supported: ClassVar[dict[str, bool]] = {}

    def __init__(self) -> None:
        """
        Initialize the LdapManager instance and set up configuration attributes.
        """
        self.logger = logger
        self.pagesize: int = 100
        # These get set during contribute_to_class()
        # self.config is the part of settings.LDAP_SERVERS that we need for our Model
        self.config: dict[str, Any] | None = None
        self.model: type[Model] | None = None
        self.pk: str | None = None
        self.ldap_options: list[str] = []
        self.objectclass: str | None = None
        self.extra_objectclasses: list[str] = []
        # keys in this dictionary get manipulated by .connect() and .disconnect()
        self._ldap_objects: dict[threading.Thread, ldap.ldapobject.LDAPObject] = {}  # type: ignore[name-defined]

    def _get_pctrls(self, serverctrls):
        """
        Lookup an LDAP paged control object from the returned controls.

        Args:
            serverctrls: List of server controls returned by the LDAP server.

        Returns:
            List of paged results controls.

        """
        # Look through the returned controls and find the page controls.
        # This will also have our returned cookie which we need to make
        # the next search request.
        return [
            c
            for c in serverctrls
            if c.controlType == SimplePagedResultsControl.controlType
        ]

    def _paged_search(
        self,
        basedn: str,
        searchfilter: str,
        attrlist: list[str] | None = None,
        pagesize: int = 100,
        sizelimit: int = 0,
        scope: int = ldap.SCOPE_SUBTREE,  # type: ignore[attr-defined]
        sort_control: ServerSideSortControl | None = None,
    ) -> list[LDAPData]:
        """
        Perform a paged search against the LDAP server.

        Args:
            basedn: The base DN to search from.
            searchfilter: The LDAP search filter string.

        Keyword Args:
            attrlist: List of attributes to retrieve.
            pagesize: Number of results per page.
            sizelimit: Maximum number of results to return.
            scope: LDAP search scope.
            sort_control: Server-side sort control.

        Returns:
            List of LDAPData tuples (dn, attrs).

        """
        # Initialize the LDAP controls for paging. Note that we pass ''
        # for the cookie because on first iteration, it starts out empty.
        paging = SimplePagedResultsControl(True, size=pagesize, cookie="")  # noqa: FBT003
        controls = [paging]
        if sort_control:
            controls = [paging, sort_control]

        # Do searches until we run out of pages to get from the LDAP server.
        results: list[LDAPData] = []
        while True:
            # Send search request.
            msgid = self.connection.search_ext(
                basedn,
                scope,
                searchfilter,
                attrlist,
                serverctrls=controls,
                sizelimit=sizelimit,
            )
            rtype, rdata, rmsgid, serverctrls = self.connection.result3(msgid)
            # Each "rdata" is a tuple of the form (dn, attrs), where dn is
            # a string containing the DN (distinguished name) of the entry,
            # and attrs is a dictionary containing the attributes associated
            # with the entry. The keys of attrs are strings, and the associated
            # values are lists of strings.
            for dn, attrs in rdata:
                # AD returns an rdata at the end that is a reference that we
                # want to ignore
                if isinstance(attrs, dict):
                    results.append((dn, attrs))

            # Get cookie for the next request.
            paged_controls = self._get_pctrls(serverctrls)
            if not paged_controls:
                # We're doing a ldap.SCOPE_BASE search
                break

            # Push cookie back into the main controls.
            controls[0].cookie = paged_controls[0].cookie

            # If there is no cookie, we're done!
            if not paged_controls[0].cookie:
                break
        return results

    def contribute_to_class(self, cls, accessor_name) -> None:
        """
        Set up the manager for a model class, configuring attributes from model meta.

        Args:
            cls: The model class.
            accessor_name: The attribute name to assign the manager to.

        """
        self.pk = cls._meta.pk.name
        self.basedn = cls._meta.basedn
        self.objectclass = cls._meta.objectclass
        self.extra_objectclasses = cls._meta.extra_objectclasses
        self.ldap_options = cls._meta.ldap_options
        try:
            self.config = settings.LDAP_SERVERS[cls._meta.ldap_server]
        except AttributeError as e:
            msg = "settings.LDAP_SERVERS does not exist!"
            raise ImproperlyConfigured(msg) from e
        except KeyError as e:
            msg = (
                f"{cls.__name__}: settings.LDAP_SERVERS has no key "
                f"'{cls._meta.ldap_server}'"
            )
            raise ImproperlyConfigured(msg) from e

        if not self.basedn:
            try:
                self.basedn = self.config["basedn"]  # type: ignore[index]
            except KeyError as e:
                msg = (
                    f"{cls.__name__}: no Meta.basedn and settings.LDAP_SERVERS"
                    f"['{cls._meta.ldap_server}'] has no 'basedn' key"
                )
                raise ImproperlyConfigured(msg) from e
        self.model = cls
        cls._meta.base_manager = self
        setattr(cls, accessor_name, self)

    def __get_dn_key(self, meta: "Options") -> str | None:
        """
        Get the LDAP attribute name used as the DN key for the model.

        Args:
            meta: The model Options instance.

        Returns:
            The DN key attribute name.

        """
        _attribute_lookup = meta.attribute_to_field_name_map
        dn_key = self.pk
        for k, v in _attribute_lookup.items():
            if v == self.pk:
                dn_key = k
                break
        return dn_key

    def dn(self, obj: "Model") -> str | None:
        """
        Compute the distinguished name (DN) for a model instance.

        Args:
            obj: The model instance.

        Returns:
            The DN string, or None if not set.

        """
        if not obj._dn:
            dn_key = self.__get_dn_key(cast("Options", obj._meta))
            pk_value = getattr(obj, cast("str", self.pk))
            if pk_value:
                obj._dn = f"{dn_key}={getattr(obj, cast('str', self.pk))},{self.basedn}"
            else:
                # If our pk_value is None or '', we're in the middle of creating
                # a new record and haven't set it yet.
                obj._dn = None
        return obj._dn

    def get_dn(self, pk: str) -> str:
        """
        Given a value for an object primary key, return what the dn for that
        object would look like.

        Args:
            pk: the value for the primary key for our model

        Returns:
            A fully qualified dn.

        """
        meta = cast("Options", cast("Model", self.model)._meta)
        dn_key = self.__get_dn_key(meta)
        return f"{dn_key}={pk},{self.basedn}"

    def disconnect(self) -> None:
        """
        Disconnect the current thread's LDAP connection.
        """
        self.connection.unbind_s()
        self.remove_connection()

    def has_connection(self) -> bool:
        """
        Check if the current thread has an active LDAP connection.

        Returns:
            True if a connection exists, False otherwise.

        """
        return threading.current_thread() in self._ldap_objects

    def set_connection(self, obj: ldap.ldapobject.LDAPObject) -> None:  # type: ignore[name-defined]
        """
        Set the LDAP connection object for the current thread.

        Args:
            obj: The LDAPObject to set.

        """
        self._ldap_objects[threading.current_thread()] = obj

    def remove_connection(self) -> None:
        """
        Remove the LDAP connection object for the current thread.
        """
        del self._ldap_objects[threading.current_thread()]

    def _connect(  # noqa: PLR0912, PLR0915
        self, key: str, dn: str | None = None, password: str | None = None
    ) -> ldap.ldapobject.LDAPObject:  # type: ignore[name-defined]
        """
        Create and return a new LDAP connection object.

        Args:
            key: Configuration key for the LDAP server.
            dn: Optional bind DN.
            password: Optional password.

        Raises:
            ValueError: If the ``tls_verify`` value in the configuration is invalid.
            OSError: If the CA Certificate file is provided but does not exist
                or is not a file.
            OSError: If the SSL Certificate file is provided but does not exist
                or is not a file.
            OSError: If the SSL Key file is provided but does not exist or is
                not a file.

        Returns:
            A connected LDAPObject.

        """
        config = cast("dict[str, Any]", self.config)[key]
        if not dn:
            dn = config["user"]
            password = config["password"]
        ldap_object: ldap.ldapobject.LDAPObject = ldap.initialize(config["url"])  # type: ignore[name-defined]
        if config.get("follow_referrals", False):
            ldap_object.set_option(ldap.OPT_REFERRALS, 1)  # type: ignore[attr-defined]
        else:
            ldap_object.set_option(ldap.OPT_REFERRALS, 0)  # type: ignore[attr-defined]
        timeout = config.get("timeout", 15.0)
        ldap_object.set_option(ldap.OPT_NETWORK_TIMEOUT, float(timeout))  # type: ignore[attr-defined]
        sizelimit = config.get("sizelimit", None)
        if sizelimit:
            ldap_object.set_option(ldap.OPT_SIZELIMIT, int(sizelimit))  # type: ignore[attr-defined]
        tls_verify = config.get("tls_verify", "never")
        if tls_verify == "never":
            ldap_object.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)  # type: ignore[attr-defined]
        elif tls_verify == "always":
            ldap_object.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_DEMAND)  # type: ignore[attr-defined]
        else:
            msg = f"Invalid tls_verify value: {tls_verify}"
            raise ValueError(msg)
        if tls_ca_certfile := config.get("tls_ca_certfile", None):
            ca_certfile = Path(tls_ca_certfile)
            if not ca_certfile.exists():
                msg = "CA Certificate file does not exist: {tls_ca_certfile}"
                raise OSError(msg)
            if not ca_certfile.is_file():
                msg = "CA Certificate file is not a file: {tls_ca_certfile}"
                raise OSError(msg)
            ldap_object.set_option(ldap.OPT_X_TLS_CACERTFILE, tls_ca_certfile)  # type: ignore[attr-defined]
        if tls_certfile := config.get("tls_certfile", None):
            certfile = Path(tls_certfile)
            if not certfile.exists():
                msg = "TLS Certificate file does not exist: {tls_certfile}"
                raise OSError(msg)
            if not certfile.is_file():
                msg = "TLS Certificate file is not a file: {tls_certfile}"
                raise OSError(msg)
            ldap_object.set_option(ldap.OPT_X_TLS_CERTFILE, tls_certfile)  # type: ignore[attr-defined]
        if tls_keyfile := config.get("tls_keyfile", None):
            keyfile = Path(tls_keyfile)
            if not keyfile.exists():
                msg = "TLS Key file does not exist: {tls_keyfile}"
                raise OSError(msg)
            if not keyfile.is_file():
                msg = "TLS Key file is not a file: {tls_keyfile}"
                raise OSError(msg)
            ldap_object.set_option(ldap.OPT_X_TLS_KEYFILE, tls_keyfile)  # type: ignore[attr-defined]
        ldap_object.set_option(ldap.OPT_X_TLS_NEWCTX, 0)  # type: ignore[attr-defined]
        if config.get("use_starttls", True):
            ldap_object.start_tls_s()
        ldap_object.simple_bind_s(dn, password)
        return ldap_object

    def connect(
        self, key: str, dn: str | None = None, password: str | None = None
    ) -> None:
        """
        Set the per-thread LDAP connection object. Used by the @atomic decorator.

        Args:
            key: Configuration key for the LDAP server.
            dn: Optional bind DN.
            password: Optional password.

        """
        self._ldap_objects[threading.current_thread()] = self._connect(
            key, dn=dn, password=password
        )

    def new_connection(
        self, key: str = "read", dn: str | None = None, password: str | None = None
    ) -> ldap.ldapobject.LDAPObject:  # type: ignore[name-defined]
        """
        Create and return a new LDAP connection object.

        Args:
            key: Configuration key for the LDAP server.
            dn: Optional bind DN.
            password: Optional password.

        Returns:
            A connected LDAPObject.

        """
        return self._connect(key, dn=dn, password=password)

    @property
    def connection(self) -> ldap.ldapobject.LDAPObject:  # type: ignore[name-defined]
        """
        Get the current thread's LDAP connection object.

        Returns:
            The LDAPObject for the current thread.

        """
        return self._ldap_objects[threading.current_thread()]

    def _get_ssha_hash(self, password: str) -> bytes:
        """
        Generate an SSHA password hash for LDAP.

        Args:
            password: The password to hash.

        Returns:
            The SSHA hash as bytes.

        """
        salt = os.urandom(8)
        h = hashlib.sha1(password.encode("utf-8"))  # noqa: S324
        h.update(salt)
        return b"{SSHA}" + encode(h.digest() + salt)

    @atomic(key="read")
    def search(
        self,
        searchfilter: str,
        attributes: list[str],
        sizelimit: int = 0,
        basedn: str | None = None,
        scope: int = ldap.SCOPE_SUBTREE,  # type: ignore[attr-defined]
        sort_control: ServerSideSortControl | None = None,
    ) -> list[LDAPData]:
        """
        Search the LDAP server for objects matching the given filter.

        Args:
            searchfilter: The LDAP search filter string.
            attributes: List of attributes to retrieve.
            sizelimit: Maximum number of results to return.
            basedn: The base DN to search from.
            scope: LDAP search scope.
            sort_control: Server-side sort control.

        Returns:
            List of LDAPData tuples (dn, attrs).

        Raises:
            ValueError: If no basedn is provided or configured.

        """
        if basedn is None:
            basedn = self.basedn
        if not basedn:
            msg = (
                "basedn is required either as a parameter or in the model's Meta class"
            )
            raise ValueError(msg)
        if "paged_search" in self.ldap_options:
            return self._paged_search(
                basedn,
                searchfilter,
                attrlist=attributes,
                sizelimit=sizelimit,
                scope=scope,
                sort_control=sort_control,
            )
        # We have to filter out and references that AD puts in
        data = self.connection.search_s(
            basedn, scope, filterstr=searchfilter, attrlist=attributes
        )
        return [obj for obj in data if isinstance(obj[1], dict)]

    @atomic(key="read")
    def search_page(
        self,
        searchfilter: str,
        attributes: list[str],
        page_size: int = 100,
        cookie: str = "",
        sizelimit: int = 0,
        basedn: str | None = None,
        scope: int = ldap.SCOPE_SUBTREE,  # type: ignore[attr-defined]
        sort_control: ServerSideSortControl | None = None,
    ) -> tuple[list[LDAPData], str]:
        """
        Perform a single page of LDAP search.

        This method performs one page of LDAP search using SimplePagedResultsControl
        and returns both the results and the cookie for the next page.

        Args:
            searchfilter: The LDAP search filter string.
            attributes: List of attributes to retrieve.
            page_size: Number of results per page.
            cookie: The paging cookie from the previous page (empty string for
                first page).
            sizelimit: Maximum number of results to return.
            basedn: The base DN to search from.
            scope: LDAP search scope.
            sort_control: Server-side sort control.

        Returns:
            Tuple of (results, next_cookie) where:
            - results: List of LDAPData tuples (dn, attrs)
            - next_cookie: Cookie for the next page (empty string if no more pages)

        Raises:
            ValueError: If no basedn is provided or configured.

        """
        if basedn is None:
            basedn = self.basedn
        if not basedn:
            msg = (
                "basedn is required either as a parameter or in the model's Meta class"
            )
            raise ValueError(msg)

        # Initialize the LDAP controls for paging
        paging = SimplePagedResultsControl(True, size=page_size, cookie=cookie)  # noqa: FBT003
        controls = [paging]
        if sort_control:
            controls = [paging, sort_control]

        # Send search request
        msgid = self.connection.search_ext(
            basedn,
            scope,
            searchfilter,
            attributes,
            serverctrls=controls,
            sizelimit=sizelimit,
        )
        rtype, rdata, rmsgid, serverctrls = self.connection.result3(msgid)

        # Process results
        results: list[LDAPData] = []
        for dn, attrs in rdata:
            # AD returns an rdata at the end that is a reference that we
            # want to ignore
            if isinstance(attrs, dict):
                results.append((dn, attrs))

        # Get cookie for next request
        paged_controls = self._get_pctrls(serverctrls)
        next_cookie = ""
        if paged_controls and paged_controls[0].cookie:
            next_cookie = paged_controls[0].cookie

        return results, next_cookie

    @atomic(key="write")
    def add(self, obj: "Model") -> None:
        """
        Add a new object to LDAP.

        Args:
            obj: The model instance to add.

        """
        # This is a bit weird here because the objectclass CharListField gets
        # secretly added during class construction on Model
        obj.objectclass = []  # type: ignore[assignment]
        for objectclass in self.extra_objectclasses:
            obj.objectclass.append(objectclass.encode())  # type: ignore[attr-defined]
        if self.objectclass:
            obj.objectclass.append(self.objectclass.encode())  # type: ignore[attr-defined]
        _modlist = Modlist(self).add(obj)
        self.connection.add_s(self.dn(obj), _modlist)

    @atomic(key="write")
    @substitute_pk
    def delete(self, *args, **kwargs) -> None:
        """
        Delete an object that matches the given filters.

        Important:
            We only will delete a single object here to protect against
            accidentally deleting multiple objects by mistake.

        Args:
            *args: Positional filter arguments.
            **kwargs: Keyword filter arguments.

        Raises:
            DoesNotExist: If no objects match the query.
            MultipleObjectsReturned: If more than one object matches the query.

        """
        obj = self.filter(*args, **kwargs).only(self.pk).get()
        self.connection.delete_s(obj.dn)

    @atomic(key="write")
    def delete_obj(self, obj: "Model") -> None:
        """
        Delete a specified object from LDAP.

        Args:
            obj: The model instance to delete.

        """
        self.connection.delete_s(obj.dn)

    @atomic(key="write")
    def rename(self, old_dn: str, new_dn: str) -> None:
        """
        Rename an object's DN, keeping it within the same basedn.

        Args:
            old_dn: The current distinguished name.
            new_dn: The new distinguished name.

        """
        newrdn = new_dn.split(",")[0]
        old_basedn = ",".join(old_dn.split(",")[1:])
        new_basedn = ",".join(new_dn.split(",")[1:])
        newsuperior = None
        if old_basedn != new_basedn:
            newsuperior = new_basedn
        self.connection.rename_s(old_dn, newrdn, newsuperior)

    @atomic(key="write")
    def modify(self, obj: "Model", old: Optional["Model"] = None) -> None:
        """
        Modify an existing LDAP object, updating its attributes as needed.

        Args:
            obj: The model instance with updated data.
            old: The previous model instance data, if available.

        """
        # First check to see whether we updated our primary key.  If so, we need
        # to rename the object in LDAP, and its obj._dn.  The old obj._dn should
        # reference the old PK.  We'll .lower() them to deal with case for the
        # pk in the dn
        old_pk_value = cast("str", obj.dn).split(",")[0].split("=")[1].lower()
        new_pk_value = getattr(obj, cast("str", self.pk)).lower()
        if new_pk_value != old_pk_value:
            # We need to do a modrdn_s if we change pk, to cause the dn to be
            # updated also
            self.connection.modrdn_s(obj.dn, f"{self.pk}={new_pk_value}")
            # And update our object's _dn to the new one
            basedn = ",".join(cast("str", obj.dn).split(",")[1:])
            new_dn = f"{self.pk}={new_pk_value},{basedn}"
            obj._dn = new_dn
            # force reload old, if it was passed in so that we get the new pk
            # value and dn
            old = None

        # Now update the non-PK attributes
        if not old:
            old = self.get_by_dn(obj._dn)  # type: ignore[arg-type]
        _modlist = Modlist(self).update(obj, cast("Model", old))
        if _modlist:
            # Only issue the modify_s if we actually have changes
            self.connection.modify_s(obj.dn, _modlist)
        else:
            self.logger.debug("ldaporm.manager.modify.no-changes dn=%s", obj.dn)

    def only(self, *names: str) -> "F":
        """
        Return a QuerySet-like F object restricted to the given attribute names.

        Args:
            *names: Attribute names to include in the query.

        Returns:
            An F object restricted to the specified attributes.

        Raises:
            InvalidField: If any name is not a valid field for the model.

        """
        return self.__filter().only(*names)

    def __filter(self) -> "F":
        """
        Return a base F object for this manager, filtered by objectclass if set.

        Returns:
            An F object with the objectclass filter applied if applicable.

        """
        f = F(self)
        if self.objectclass:
            f = f.filter(objectclass=self.objectclass)
        return f

    @substitute_pk
    def wildcard(self, name: str, value: str) -> "F":
        """
        Return a QuerySet-like F object with a wildcard filter applied.

        Args:
            name: The field name to filter on.
            value: The value to filter with wildcards.

        Returns:
            An F object with the wildcard filter applied.

        """
        return self.__filter().wildcard(name, value)

    @substitute_pk
    def filter(self, *args, **kwargs) -> "F":
        """
        Return a QuerySet-like F object with the given filters applied.

        Args:
            *args: Positional filter arguments.
            **kwargs: Keyword filter arguments.

        Returns:
            An F object with the filters applied.

        """
        return self.__filter().filter(*args, **kwargs)

    @substitute_pk
    def exclude(self, *args, **kwargs) -> "F":
        """
        Return a QuerySet-like F object with negated filters applied.

        Args:
            *args: Positional filter arguments.
            **kwargs: Keyword filter arguments to negate.

        Returns:
            An F object with the negated filters applied.

        """
        return self.__filter().exclude(*args, **kwargs)

    def get_by_dn(self, dn: str) -> "Model":
        """
        Get an object specifically by its DN.  To do this we do a search with
        the basedn set to the dn of the object, with scope ``ldap.SCOPE_BASE``
        and then get all objects that match.  This will be either the object
        we're looking for, or nothing.

        Args:
            dn: The distinguished name to search for.

        Returns:
            The model instance corresponding to the DN.

        Raises:
            ValueError: If the DN is not in the model's basedn.
            DoesNotExist: If no object with this DN exists.
            MultipleObjectsReturned: If more than one object matches the DN.

        """
        dn = dn.lower()
        model = cast("type[Model]", self.model)
        options = cast("Options", model._meta)
        if options.basedn and not dn.endswith(options.basedn.lower()):
            msg = (
                f"The requested dn '{dn}' is not in our model's basedn "
                f"'{options.basedn}'"
            )
            raise ValueError(msg)
        try:
            objects = self.search(
                "(objectClass=*)",
                options.attributes,
                basedn=dn,
                scope=ldap.SCOPE_BASE,  # type: ignore[attr-defined]
            )
        except ldap.NO_SUCH_OBJECT:  # type: ignore[attr-defined]
            objects = []
        if len(objects) == 0:
            msg = f"A {model.__name__} object matching query does not exist."
            raise model.DoesNotExist(msg)
        if len(objects) > 1:
            msg = f"More than one {model.__name__} object matched query."
            raise model.MultipleObjectsReturned(msg)
        return cast("Model", model.from_db(options.attributes, objects))

    @substitute_pk
    def get(self, *args, **kwargs) -> "Model":
        """
        Return the single result of the query, or raise
        DoesNotExist/MultipleObjectsReturned.  Accepts kwargs for filtering.

        Args:
            *args: Positional filter arguments.

        Keyword Args:
            **kwargs: Keyword filter arguments.

        Returns:
            The single model instance matching the query.

        Raises:
            LdapManager.DoesNotExist: If no object matches the query.
            LdapManager.MultipleObjectsReturned: If more than one object matches
                the query.

        """
        if kwargs:
            return self.filter(**kwargs).get(*args)
        # No kwargs: use the original logic
        self._require_manager()
        manager = cast("LdapManager", self.manager)
        model = cast("type[Model]", self.model)
        attributes = cast("list[str]", self._attributes)
        objects = manager.search(str(self), attributes)
        if len(objects) == 0:
            msg = f"A {model.__name__} object matching query does not exist."
            raise model.DoesNotExist(msg)
        if len(objects) > 1:
            msg = f"More than one {model.__name__} object matched query."
            raise model.MultipleObjectsReturned(msg)
        return cast("Model", model.from_db(attributes, objects))

    def _get_single_result(self, *args) -> "Model":
        # Call the logic directly (no super())
        return self.get(*args)

    def all(self) -> "F":
        """
        Return the F object for compatibility with Django REST Framework.

        Returns:
            The F object, which is iterable and supports pagination.

        """
        return self.__filter()

    def values(self, *args: str) -> list[dict[str, Any]]:
        """
        Return a list of dictionaries representing all objects, with specified
        attributes.

        Args:
            *args: Attribute names to include in the dictionaries.

        Returns:
            A list of dictionaries, one per object.

        """
        return self.__filter().values(*args)

    def values_list(self, *args: str, **kwargs) -> list[tuple[Any, ...]]:
        """
        Return a list of tuples (or namedtuples) representing all objects.

        Args:
            *args: Attribute names to include in the tuples.
            **kwargs: 'flat' for single-value tuples, 'named' for namedtuples.

        Returns:
            A list of tuples or namedtuples, one per object.

        """
        return self.__filter().values_list(*args, **kwargs)

    def order_by(self, *args: str) -> "F":
        """
        Return a QuerySet-like F object with ordering applied.

        Args:
            *args: Attribute names to order by (use '-' prefix for descending).

        Returns:
            An F object with ordering applied.

        Raises:
            InvalidField: If any field is not valid for the model.

        """
        return self.__filter().order_by(*args)

    def page(self, page_size: int = 100, cookie: str = "") -> "PagedResultSet":
        """
        Return a single page of results matching the query.

        This method performs a paged LDAP search and returns both the results
        and metadata needed for pagination.

        Args:
            page_size: Number of results per page.
            cookie: Paging cookie from the previous page (empty string for first page).

        Returns:
            A PagedResultSet containing the results and pagination metadata.

        """
        return self.__filter().page(page_size=page_size, cookie=cookie)

    def reset_password(
        self, username: str, new_password: str, attributes: dict[str, Any] | None = None
    ) -> bool:
        """
        Reset the password for a user in LDAP.

        Args:
            username: The username of the user.
            new_password: The new password to set.
            attributes: Optional additional attributes to update.

        Returns:
            True if the password was reset successfully, False otherwise.

        """
        model = cast("type[Model]", self.model)
        password_attribute = getattr(
            cast("Options", model._meta), "password_attribute", "userPassword"
        )
        if not attributes:
            attributes = {}
        try:
            user = self.filter(uid=username).only("uid").get()
        except model.DoesNotExist:
            self.logger.warning("auth.no_such_user user=%s", username)
            return False

        pwhash = model.get_password_hash(new_password)
        # Update the password attribute in the attributes dict
        attributes = dict(attributes)  # make a copy to avoid mutating input
        attributes[password_attribute] = [pwhash]

        # Ensure all attribute values are lists of bytes
        for key, value in attributes.items():
            _value = value
            if not isinstance(value, list):
                _value = [value]
            attributes[key] = [
                v if isinstance(v, bytes) else str(v).encode("utf-8") for v in _value
            ]

        _modlist = Modlist(self)._get_modlist(attributes, ldap.MOD_REPLACE)  # type: ignore[attr-defined]

        self.connect("write")
        self.connection.modify_s(user.dn, _modlist)
        self.disconnect()
        service = getattr(model._meta, "ldap_server", "default")  # type: ignore[attr-defined]
        self.logger.info("%s.password_reset.success dn=%s", service, user.dn)
        return True

    def authenticate(self, username: str, password: str) -> bool:
        """
        Try to authenticate a username/password vs our LDAP server.

        If the user does not exist in LDAP, return False.
        If the user exists, but the bind fails, return False.
        Else, return True.

        Args:
            username: The username to authenticate.
            password: The password to authenticate with.

        Returns:
            True if authentication is successful, False otherwise.

        """
        model = cast("type[Model]", self.model)
        uid_attr = cast("Options", model._meta).userid_attribute
        try:
            user = self.filter(**{uid_attr: username}).only(uid_attr).get()
        except model.DoesNotExist:
            self.logger.warning("auth.no_such_user user=%s", username)
            return False
        try:
            self.connect("read", user.dn, password)
        except ldap.INVALID_CREDENTIALS:  # type: ignore[attr-defined]
            self.logger.warning("auth.invalid_credentials user=%s", username)
            return False
        self.disconnect()
        self.logger.info("auth.success user=%s", username)
        return True

    def create(self, **kwargs) -> "Model":
        """
        Create and add a new object to LDAP.

        Args:
            **kwargs: Field values for the new object.

        Returns:
            The newly created model instance.

        """
        obj = cast("type[Model]", self.model)(**kwargs)
        self.add(obj)
        return self.get(pk=getattr(obj, cast("str", self.pk)))

    def _check_server_sorting_support(self, key: str = "read") -> bool:
        """
        Check if the LDAP server supports server-side sorting by querying the Root DSE.

        Args:
            key: Configuration key for the LDAP server.

        Returns:
            True if server-side sorting is supported, False otherwise.

        """
        # Check cache first
        if key in self.__class__._server_sorting_supported:
            return self.__class__._server_sorting_supported[key]

        # Create a temporary connection to check server capabilities
        temp_connection = None
        try:
            temp_connection = self._connect(key)

            # Query the Root DSE for supported controls
            result = temp_connection.search_s(
                "",  # Root DSE
                ldap.SCOPE_BASE,  # type: ignore[attr-defined]
                "(objectClass=*)",
                ["supportedControl"],
            )

        except ldap.LDAPError as e:  # type: ignore[attr-defined]
            # Allow SERVER_DOWN and CONNECT_ERROR to propagate (test is inconclusive)
            if isinstance(e, (ldap.SERVER_DOWN, ldap.CONNECT_ERROR)):  # type: ignore[attr-defined]
                raise
            # If we can't check due to other LDAP-specific errors, assume no support
            # and log the error
            self.logger.warning(
                "Failed to check server-side sorting support: %s. "
                "Falling back to client-side sorting.",
                e,
            )
            self.__class__._server_sorting_supported[key] = False
            warnings.warn(
                f"Failed to check server-side sorting support: {e}. "
                "Falling back to client-side sorting.",
                stacklevel=2,
            )
            return False
        else:
            if not result:
                # No Root DSE found, assume no support
                self.__class__._server_sorting_supported[key] = False
                warnings.warn(
                    "Could not query Root DSE for supported controls. "
                    "Server-side sorting will be disabled.",
                    stacklevel=2,
                )
                return False

            # Extract supported controls from the result
            supported_controls = result[0][1].get("supportedControl", [])

            # Check if our server-side sorting OID is in the list
            sorting_oid = "1.2.840.113556.1.4.473"
            is_supported = any(
                control.decode("utf-8") == sorting_oid for control in supported_controls
            )

            # Cache the result at class level
            self.__class__._server_sorting_supported[key] = is_supported

            if not is_supported:
                warnings.warn(
                    "LDAP server does not support server-side sorting "
                    f"(OID: {sorting_oid}). Falling back to client-side sorting.",
                    stacklevel=2,
                )
            return is_supported
        finally:
            if temp_connection:
                with suppress(ldap.LDAPError):  # type: ignore[attr-defined]
                    temp_connection.unbind_s()

    def count(self) -> int:
        """
        Return the number of objects for this model from LDAP.
        """
        return self.__filter().count()

    def as_list(self) -> list["Model"]:
        """
        Return a list of all objects for this model from LDAP.
        """
        return self.__filter().as_list()

    def get_or_none(self, *args, **kwargs):
        """
        Return the single result of the query, or None if not exactly one found.
        """
        return self.__filter().get_or_none(*args, **kwargs)

    def first_or_none(self, *args, **kwargs):
        """
        Return the first result of the query, or None if no match.
        """
        return self.__filter().first_or_none(*args, **kwargs)
