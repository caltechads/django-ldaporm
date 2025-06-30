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
from base64 import b64encode as encode
from collections import namedtuple
from collections.abc import Callable, Sequence
from distutils.version import StrictVersion
from functools import wraps
from typing import TYPE_CHECKING, Any, Optional, cast

import ldap
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from ldap import modlist
from ldap.controls import SimplePagedResultsControl
from ldap_filter import Filter

from .typing import AddModlist, LDAPData, ModifyDeleteModList

if TYPE_CHECKING:
    from ldap_filter.filter import GroupAnd

    from .models import Model
    from .options import Options

LDAP24API = StrictVersion(ldap.__version__) >= StrictVersion("2.4")
logger = logging.getLogger("django-ldaporm")


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

    def __init__(self, manager: "LdapManager", f: Optional["F"] = None) -> None:
        self.manager = manager
        self.model = cast("type[Model]", manager.model)
        self._meta = cast("Options", self.model._meta)
        self.fields_map = self._meta.fields_map
        self.attributes_map = self._meta.attributes_map
        self.attribute_to_field_name_map = self._meta.attribute_to_field_name_map
        self.attributes = self._meta.attributes
        self._attributes = self.attributes
        self._order_by = self._meta.ordering
        if f:
            self.chain: list[F] = f.chain
        else:
            self.chain = []

    @property
    def _filter(self) -> "GroupAnd":
        """
        Return a list of filters ready to be converted to a filter string.

        Returns:
            A GroupAnd filter object representing the current filter chain.

        Raises:
            NoFilterSpecified: If no filters are specified.

        """
        if len(self.chain) == 0:
            msg = (
                "You need to at least specify one filter in order to do LDAP searches."
            )
            raise self.NoFilterSpecified(msg)
        if len(self.chain) == 1:
            return self.chain[0]  # type: ignore[return-value]
        return Filter.AND(self.chain).simplify()

    def __sort(self, objects: Sequence["Model"]) -> Sequence["Model"]:
        """
        Sort a sequence of model instances based on the current ordering.

        Args:
            objects: The sequence of Model instances to sort.

        Returns:
            The sorted sequence of Model instances.

        """
        if not self._order_by:
            return objects
        if not any(k.startswith("-") for k in self._order_by):
            # if none of the keys are reversed, just sort directly
            return sorted(
                objects, key=lambda obj: tuple(getattr(obj, k) for k in self._order_by)
            )
        # At least one key was reversed. now we have to do it the hard way,
        # with sequential sorts, starting from the last sort key and working
        # our way back to the first
        keys = list(self._order_by)
        keys.reverse()
        for k in keys:
            key = k
            reverse = False
            if key.startswith("-"):
                key = k[1:]
                reverse = True
            data = sorted(
                objects,
                key=lambda obj: getattr(obj, key),  # pylint: disable=cell-var-from-loop
                reverse=reverse,
            )
        return data

    def __validate_positional_args(self, args: Sequence["F"]) -> list["F"]:
        """
        Validate that all positional arguments are F instances.

        Args:
            args: Sequence of arguments to validate.

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
        """
        Get the LDAP attribute name for a given model field name.

        Args:
            name: The model field name.

        Returns:
            The corresponding LDAP attribute name.

        Raises:
            InvalidField: If the field name is not valid for the model.

        """
        try:
            return self.attributes_map[name]
        except KeyError as e:
            msg = f'"{name}" is not a valid field on model {self.model.__name__}'
            raise self.model.InvalidField(msg) from e

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

    def filter(self, *args: "F", **kwargs) -> "F":  # noqa: PLR0912
        """
        Apply filters to the query using Django-like filter suffixes.

        Args:
            *args: Positional F objects to chain.
            **kwargs: Field lookups and values.

        Returns:
            A new F object with the filters applied.

        Raises:
            ValueError: If an __in filter is not given a list.
            UnknownSuffix: If an unknown filter suffix is used.

        """
        steps = self.__validate_positional_args(args)
        for key, value in kwargs.items():
            _value = value
            if isinstance(_value, str):
                _value = _value.strip()
            if key.endswith("__istartswith"):
                steps.append(
                    Filter.attribute(self.get_attribute(key[:-13])).starts_with(_value)  # type: ignore[arg-type]
                )  # type: ignore[arg-type]
            elif key.endswith("__iendswith"):
                steps.append(
                    Filter.attribute(self.get_attribute(key[:-11])).ends_with(_value)  # type: ignore[arg-type]
                )  # type: ignore[arg-type]
            elif key.endswith("__icontains"):
                steps.append(
                    Filter.attribute(self.get_attribute(key[:-11])).contains(_value)  # type: ignore[arg-type]
                )  # type: ignore[arg-type]
            elif key.endswith("__in"):
                if not isinstance(value, list):
                    msg = 'When using the "__in" filter you must supply a list'
                    raise ValueError(msg)
                in_steps = [
                    Filter.attribute(self.get_attribute(key[:-4])).equal_to(_v)
                    for _v in _value
                ]
                steps.append(Filter.OR(in_steps))  # type: ignore[arg-type]
            elif key.endswith("__exists"):
                # This one doesn't exist as a Django field lookup
                steps.append(Filter.attribute(self.get_attribute(key[:-8])).present())  # type: ignore[arg-type]
            elif key.endswith("__iexact") or "__" not in key:
                # no suffix means do an __exact
                _key = key
                if "__" in key:
                    _key = key[:-8]
                if _value is None:
                    # If value is None, we search for the absence of that
                    # attribute
                    steps.append(Filter.NOT(Filter.attribute(self.get_attribute(_key))))  # type: ignore[arg-type]
                else:
                    steps.append(
                        Filter.attribute(self.get_attribute(_key)).equal_to(_value)  # type: ignore[arg-type]
                    )  # type: ignore[arg-type]
            else:
                msg = f'The search filter "{key}" uses an unknown filter suffix'
                raise F.UnknownSuffix(msg)
        self.chain.append(Filter.AND(steps))  # type: ignore[arg-type]
        return self

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
        sizelimit = 0
        if not self._order_by:
            # We can just take the default LDAP ordering, so just take the first
            # result in whatever order the LDAP server keeps it in.
            sizelimit = 1
        objects = self.manager.search(str(self), self._attributes, sizelimit=sizelimit)
        if len(objects) == 0:
            msg = f"A {self.model.__name__} object matching query does not exist."
            raise self.model.DoesNotExist(msg)
        objects = self.model.from_db(self._attributes, objects)
        if not self._order_by:
            return objects[0]  # type: ignore[attr-defined]
        return self.__sort(objects)[0]  # type: ignore[arg-type]

    @needs_pk
    def get(self) -> "Model":
        """
        Return the single result of the query, or raise if not exactly one found.

        Returns:
            The model instance matching the query.

        Raises:
            DoesNotExist: If no objects match the query.
            MultipleObjectsReturned: If more than one object matches the query.

        """
        objects = self.manager.search(str(self), self._attributes)
        if len(objects) == 0:
            msg = f"A {self.model.__name__} object matching query does not exist."
            raise self.model.DoesNotExist(msg)
        if len(objects) > 1:
            msg = f"More than one {self.model.__name__} object matched query."
            raise self.model.MultipleObjectsReturned(msg)
        return cast("Model", self.model.from_db(self._attributes, objects))

    @needs_pk
    def update(self, **kwargs) -> None:
        """
        Update the object matching the query with the given attributes.

        Args:
            **kwargs: Field names and values to update.

        """
        obj = self.get()
        # TODO: obj.dump() does not exist;
        new = self.model.from_db(self._attributes, obj.dump())
        for key, value in kwargs.items():
            if key in self.attributes:
                setattr(new, key, value)
        self.manager.modify(new, old=obj)  # type: ignore[arg-type]

    def exists(self) -> bool:
        """
        Return True if the query returns any results, False otherwise.

        Returns:
            True if any objects match the query, False otherwise.

        """
        objects = self.manager.search(str(self), self._attributes)
        return len(objects) > 0

    @needs_pk
    def all(self) -> Sequence["Model"]:
        """
        Return all results matching the query, sorted if order_by is set.

        Returns:
            A sequence of model instances matching the query.

        """
        objects = self.model.from_db(
            self._attributes,
            self.manager.search(str(self), self._attributes),
            many=True,
        )
        return self.__sort(cast("Sequence[Model]", objects))

    def delete(self) -> None:
        """
        Delete the object matching the query.

        Raises:
            DoesNotExist: If no objects match the query.
            MultipleObjectsReturned: If more than one object matches the query.

        """
        obj = self.get()
        self.manager.connection.delete_s(obj.dn)

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
        for key in args:
            _key = key.removeprefix("-")
            if _key not in self.attributes_map:
                msg = f'"{_key}" is not a valid field on model {self.model.__name__}'
                raise self.model.InvalidField(msg)
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
        if self._attributes != self.attributes:
            msg = "Don't use .only() with .values()"
            raise NotImplementedError(msg)
        _attrs = []
        if not attrs:
            _attrs = self.attributes
        objects = self.model.from_db(
            _attrs, self.manager.search(str(self), _attrs), many=True
        )
        objects = self.__sort(cast("Sequence[Model]", objects))
        return [
            {
                self.attribute_to_field_name_map[attr]: getattr(obj, attr)
                for attr in _attrs
            }
            for obj in objects
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
        if self._attributes != self.attributes:
            msg = "Don't use .only() with .values_list()"
            raise NotImplementedError(msg)

        _attrs: list[str] = []
        if not attrs:
            _attrs = self.attributes
            attrs = tuple(self.attribute_to_field_name_map[attr] for attr in _attrs)
        else:
            _attrs = [self.get_attribute(attr) for attr in attrs]
        objects = self.model.from_db(
            _attrs, self.manager.search(str(self), _attrs), many=True
        )
        objects = self.__sort(cast("Sequence[Model]", objects))
        if kwargs.get("flat"):
            if len(attrs) > 1:
                msg = "Cannot use flat=True when asking for more than one field"
                raise ValueError(msg)
            return [getattr(obj, attrs[0]) for obj in objects]  # type: ignore[return-value]
        if kwargs.get("named"):
            rows: list[Any] = []
            for obj in objects:
                # Dynamic namedtuple creation: attrs is not a literal, but this
                # is valid for runtime use.
                Row = namedtuple("Row", tuple(attrs))  # type: ignore[misc]  # noqa: PYI024
                # the keys here should be field names, not attribute names
                rows.append(Row(**{attr: getattr(obj, attr) for attr in attrs}))
            return rows
        return [tuple(getattr(obj, attr) for attr in attrs) for obj in objects]

    def __or__(self, other: "F") -> "F":
        """
        Combine this filter with another using logical OR.

        Args:
            other: Another F object to combine with.

        Returns:
            A new F object representing the OR of both filters.

        """
        self.chain = Filter.OR([self._filter, other._filter])  # type: ignore[assignment]
        return F(self.manager, f=self)

    def __and__(self, other: "F") -> "F":
        """
        Combine this filter with another using logical AND.

        Args:
            other: Another F object to combine with.

        Returns:
            A new F object representing the AND of both filters.

        """
        self.chain = Filter.AND([self._filter, other._filter])  # type: ignore[assignment]
        return F(self.manager, f=self)

    def __str__(self) -> str:
        """
        Return the LDAP filter string for this query.

        Returns:
            The LDAP filter string.

        """
        return self._filter.to_string()


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
    """

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
        self._ldap_objects: dict[threading.Thread, ldap.ldapobject.LDAPObject] = {}  # type: ignore[attr-defined]

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
    ) -> list[LDAPData]:
        """
        Perform a paged search against the LDAP server.

        Args:
            basedn: The base DN to search from.
            searchfilter: The LDAP search filter string.
            attrlist: List of attributes to retrieve.
            pagesize: Number of results per page.
            sizelimit: Maximum number of results to return.
            scope: LDAP search scope.

        Returns:
            List of LDAPData tuples (dn, attrs).

        """
        # Initialize the LDAP controls for paging. Note that we pass ''
        # for the cookie because on first iteration, it starts out empty.
        controls = SimplePagedResultsControl(True, size=pagesize, cookie="")  # noqa: FBT003

        # Do searches until we run out of pages to get from the LDAP server.
        results: list[LDAPData] = []
        while True:
            # Send search request.
            msgid = self.connection.search_ext(
                basedn,
                scope,
                searchfilter,
                attrlist,
                serverctrls=[controls],
                sizelimit=sizelimit,
            )
            rtype, rdata, rmsgid, serverctrls = self.connection.result3(msgid)  # pylint: disable=unused-variable
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
            controls.cookie = paged_controls[0].cookie

            # If there is no cookie, we're done!
            if not paged_controls[0].cookie:
                break
        return results

    def contribute_to_class(self, cls, accessor_name):
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

    def set_connection(self, obj: ldap.ldapobject.LDAPObject) -> None:  # type: ignore[attr-defined]
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

    def _connect(
        self, key: str, dn: str | None = None, password: str | None = None
    ) -> ldap.ldapobject.LDAPObject:  # type: ignore[attr-defined]
        """
        Create and return a new LDAP connection object.

        Args:
            key: Configuration key for the LDAP server.
            dn: Optional bind DN.
            password: Optional password.

        Returns:
            A connected LDAPObject.

        """
        config = cast("dict[str, Any]", self.config)[key]
        if not dn:
            dn = config["user"]
            password = config["password"]
        ldap_object: ldap.ldapobject.LDAPObject = ldap.initialize(config["url"])  # type: ignore[attr-defined]
        ldap_object.set_option(ldap.OPT_REFERRALS, 0)  # type: ignore[attr-defined]
        ldap_object.set_option(ldap.OPT_NETWORK_TIMEOUT, 15.0)  # type: ignore[attr-defined]
        ldap_object.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)  # type: ignore[attr-defined]
        ldap_object.set_option(ldap.OPT_X_TLS_NEWCTX, 0)  # type: ignore[attr-defined]
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
    ) -> ldap.ldapobject.LDAPObject:  # type: ignore[attr-defined]
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
    def connection(self) -> ldap.ldapobject.LDAPObject:  # type: ignore[attr-defined]
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
    ) -> list[LDAPData]:
        """
        Perform an LDAP search with the given filter and attributes.

        Args:
            searchfilter: The LDAP search filter string.
            attributes: List of attribute names to retrieve.
            sizelimit: Maximum number of results to return (0 for no limit).
            basedn: Optional base DN to search from. If None, uses the model's basedn.
            scope: LDAP search scope.

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
            )
        # We have to filter out and references that AD puts in
        data = self.connection.search_s(
            basedn, scope, filterstr=searchfilter, attrlist=attributes
        )
        return [obj for obj in data if isinstance(obj[1], dict)]

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

        """
        return F(self).only(*names)

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
        Return a single object matching the given filters.

        Args:
            *args: Positional filter arguments.
            **kwargs: Keyword filter arguments.

        Returns:
            The model instance matching the filters.

        """
        return self.__filter().filter(*args, **kwargs).get()

    def all(self) -> Sequence["Model"]:
        """
        Return all objects for this model from LDAP, after applying any filters.

        Note:
            Unlike the Django QuerySet version of this, this actually
            runs the query against LDAP and returns the result.  The Django
            version returns an iterator, I think.

        Returns:
            A sequence of all model instances from LDAP matching the filters.

        """
        return self.__filter().all()

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

        """
        return self.__filter().order_by(*args)

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
        password_attribute = cast("Options", model._meta).password_attribute
        if not password_attribute:
            return False
        if not attributes:
            attributes = {}
        try:
            user = self.filter(uid=username).only("uid").get()
        except model.DoesNotExist:
            self.logger.warning("auth.no_such_user user=%s", username)
            return False

        pwhash = model.get_password_hash(new_password)
        attr = {password_attribute: [pwhash]}
        cast("dict[str, Any]", attributes).update(attr)

        _modlist = Modlist(self)._get_modlist(attr, ldap.MOD_REPLACE)  # type: ignore[attr-defined]

        self.connect("write")
        self.connection.modify_s(user.dn, _modlist)
        self.disconnect()
        service = getattr(model._meta, "ldap_server", "ldap")  # type: ignore[attr-defined]
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
