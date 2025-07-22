"""
LDAP ORM model base classes and metaclass.

This module provides the base Model class and LdapModelBase metaclass for creating
LDAP-backed Django-like ORM models. It handles model creation, field initialization,
and provides methods for converting between LDAP data and Python objects.
"""

import hashlib
import inspect
import os
from base64 import b64encode as encode
from typing import Any, Union, cast

from django.core.exceptions import FieldDoesNotExist, ValidationError

try:
    from django.utils.encoding import force_text  # type: ignore[attr-defined]
except ImportError:
    from django.utils.encoding import force_str as force_text
from django.db.models.signals import class_prepared, post_init, pre_init

from ldaporm.fields import Field
from ldaporm.managers import LdapManager
from ldaporm.typing import LDAPData

from .options import Options


class LdapModelBase(type):
    """
    Metaclass for LDAP ORM models.

    This metaclass handles the creation of LDAP model classes, including field
    initialization, manager setup, and meta class configuration. It simulates
    Django's model creation process to ensure compatibility with Django forms
    and other Django ORM features.

    """

    def __new__(cls, name, bases, attrs, **kwargs):
        """
        Create a new LDAP model class.

        Args:
            name: The name of the class being created.
            bases: Base classes for the new class.
            attrs: Attributes and methods for the new class.
            **kwargs: Additional keyword arguments.

        Returns:
            The newly created model class.

        """
        super_new = super().__new__
        parents = [b for b in bases if isinstance(b, LdapModelBase)]
        if not parents:
            return super_new(cls, name, bases, attrs)

        # Create the class.
        module = attrs.pop("__module__")
        new_attrs = {"__module__": module}
        classcell = attrs.pop("__classcell__", None)
        if classcell is not None:
            new_attrs["__classcell__"] = classcell
        new_class = super_new(cls, name, bases, new_attrs, **kwargs)
        attr_meta = attrs.pop("Meta", None)
        meta = attr_meta or getattr(new_class, "Meta", None)

        # Add our Meta class.  This simluates the Django ORM Meta class
        # enough that ModelForm will work for us, among other things
        new_class.add_to_class("_meta", Options(meta))

        # Add all attributes to the class.  This is where the fields get
        # initialized
        for obj_name, obj in attrs.items():
            new_class.add_to_class(obj_name, obj)

        new_class._meta.concrete_model = new_class  # type: ignore[attr-defined]
        new_class._prepare()

        return new_class

    def add_to_class(cls, name: str, value: Any) -> None:
        """
        Add an attribute to the class, calling contribute_to_class if available.

        Args:
            name: The name of the attribute to add.
            value: The value to assign to the attribute.

        """
        # We should call the contribute_to_class method only if it's bound
        if not inspect.isclass(value) and hasattr(value, "contribute_to_class"):
            value.contribute_to_class(cls, name)
        else:
            setattr(cls, name, value)

    def _prepare(cls) -> None:
        """
        Create some methods once self._meta has been populated.

        Importantly, this is where the Manager class gets added.
        """
        opts = cls._meta  # type: ignore[attr-defined]
        opts._prepare(cls)

        # Give the class a docstring -- its definition.
        if cls.__doc__ is None:
            cls.__doc__ = "{}({})".format(
                cls.__name__,
                ", ".join(f.name for f in opts.fields),
            )

        if any(f.name == "objects" for f in opts.fields):
            msg = (
                f"Model {cls.__name__} must specify a custom Manager, because it has a "
                "field named 'objects'."
            )
            raise ValueError(msg)
        manager = opts.manager_class()
        cls.add_to_class("objects", manager)
        class_prepared.send(sender=cls)


class classproperty(property):  # noqa: N801
    """
    A property that can be accessed as a class attribute.

    This is a copy of the classproperty decorator from Django.
    """

    def __get__(self, obj, objtype=None):
        return self.fget(objtype)


class Model(metaclass=LdapModelBase):
    """
    Base class for LDAP ORM models.

    This class provides the core functionality for LDAP-backed models, including
    field handling, data conversion, validation, and CRUD operations. It mimics
    Django's Model class interface to ensure compatibility with Django forms
    and other Django ORM features.

    """

    class DoesNotExist(Exception):
        """Raised when a model instance is not found in LDAP."""

    class InvalidField(Exception):
        """Raised when an invalid field is referenced."""

    class MultipleObjectsReturned(Exception):
        """
        Raised when a query returns more than one object when only one was
        expected.
        """

    #: The model's metadata and configuration options.
    _meta: Options | None = None
    #: The default manager for this model.
    objects: LdapManager | None = None

    def __init__(self, *args, **kwargs) -> None:
        """
        Initialize a new model instance.

        Args:
            *args: Positional arguments for field values.
            **kwargs: Keyword arguments for field values and special attributes.

        Raises:
            IndexError: If the number of positional arguments exceeds the number
                of fields.
            TypeError: If an invalid keyword argument is provided.

        """
        cls = self.__class__
        opts = cast("Options", self._meta)
        _setattr = setattr
        self._dn: str | None = None

        pre_init.send(sender=cls, args=args, kwargs=kwargs)

        if len(args) > len(opts.fields):
            # Daft, but matches old exception sans the err msg.
            msg = "Number of args exceeds number of fields"
            raise IndexError(msg)

        if not kwargs:
            fields_iter = iter(opts.fields)
            for val, field in zip(args, fields_iter, strict=False):
                _setattr(self, cast("str", field.name), val)
        else:
            # Slower, kwargs-ready version.
            fields_iter = iter(opts.fields)
            for val, field in zip(args, fields_iter, strict=False):
                _setattr(self, cast("str", field.name), val)
                kwargs.pop(cast("str", field.name), None)

        # Now we're left with the unprocessed fields that *must* come from
        # keywords, or default.

        for field in fields_iter:
            if kwargs:
                try:
                    val = kwargs.pop(cast("str", field.name))
                except KeyError:
                    # This is done with an exception rather than the
                    # default argument on pop because we don't want
                    # get_default() to be evaluated, and then not used.
                    # Refs #12057.
                    val = field.get_default()
            else:
                val = field.get_default()
            _setattr(self, cast("str", field.name), val)

        if kwargs and "_dn" in kwargs:
            _setattr(self, "_dn", kwargs["_dn"])
            kwargs.pop("_dn")

        if kwargs:
            for kwarg in kwargs:
                msg = f"'{kwarg}' is an invalid keyword argument for this function"
                raise TypeError(msg)
        super().__init__()
        post_init.send(sender=cls, instance=self)

    @classmethod
    def from_db(
        cls,
        attributes: list[str],
        objects: LDAPData | list[LDAPData],
        many: bool = False,
    ) -> Union["Model", list["Model"]]:
        """
        Create model instances from raw LDAP data.

        Args:
            attributes: List of LDAP attribute names to process.
            objects: Raw LDAP data objects (dn, attrs) tuples.
            many: Whether to return multiple objects or a single object.

        Returns:
            A single model instance or sequence of model instances.

        Raises:
            RuntimeError: If many=False but multiple objects are provided.
            FieldDoesNotExist: If an LDAP attribute has no corresponding model field.

        """
        if not isinstance(objects, list):
            objects = [cast("LDAPData", objects)]
        if not many and len(objects) > 1:
            msg = (
                f"Called {cast('Options', cls._meta).object_name}.from_db() "
                "with many=False but len(objects) > 1"
            )
            raise RuntimeError(msg)
        _attr_lookup = cast("Options", cls._meta).attribute_to_field_name_map
        _field_lookup = cast("Options", cls._meta).fields_map
        for attr in attributes:
            if attr not in _attr_lookup:
                msg = (
                    f"No field on model {cast('Options', cls._meta).object_name} "
                    f'corresponding to LDAP attribute "{attr}"'
                )
                raise FieldDoesNotExist(msg)
        rows = []
        for obj in objects:
            if not isinstance(obj[1], dict):
                continue
            # Case sensitivity does not matter in LDAP, but it does when we're
            # looking up keys in our dict here.  Deal with the case for when we
            # have a different case on our field name than what LDAP returns
            obj_attr_lookup = {k.lower(): k for k in obj[1]}
            kwargs: dict[str, Any] = {}
            kwargs["_dn"] = obj[0]

            # Create a set of loaded field names for efficient lookup
            loaded_fields = set()

            for attr in attributes:
                name = _attr_lookup[attr]
                try:
                    value: Any = obj[1][obj_attr_lookup[attr.lower()]]
                except KeyError:
                    # if the object in LDAP doesn't have that data, the
                    # attribute won't be present in the response
                    continue
                kwargs[name] = _field_lookup[name].from_db_value(value)
                loaded_fields.add(name)

            # Create instance with only loaded fields
            instance = cls._create_from_db(kwargs, loaded_fields)
            rows.append(instance)
        if not many:
            return rows[0]
        return rows

    @classmethod
    def _create_from_db(
        cls, kwargs: dict[str, Any], loaded_fields: set[str]
    ) -> "Model":
        """
        Create a model instance from database data with only specified fields loaded.

        This method creates an instance without initializing unloaded fields with
        default values, which is important for .only() queries.

        Args:
            kwargs: Keyword arguments for field values and special attributes.
            loaded_fields: Set of field names that were actually loaded from LDAP.

        Returns:
            A model instance with only the specified fields loaded.

        """
        instance = cls.__new__(cls)
        instance._dn = kwargs.pop("_dn", None)

        # Set only the loaded fields
        for field_name, value in kwargs.items():
            setattr(instance, field_name, value)

        # Initialize unloaded fields to None to indicate they weren't loaded
        opts = cast("Options", cls._meta)
        for field in opts.fields:
            if field.name and field.name not in loaded_fields:
                setattr(instance, field.name, None)

        # Send post_init signal
        post_init.send(sender=cls, instance=instance)

        return instance

    @classproperty
    def _default_manager(cls) -> "LdapManager":
        """
        Get the default manager for this model.

        Returns:
            The default LdapManager instance.

        """
        return cast("LdapManager", cls.objects)

    @classmethod
    def get_password_hash(cls, password: str) -> bytes:
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

    def to_db(self) -> LDAPData:
        """
        Convert the model instance to LDAP data format.

        Returns a 2-tuple similar to what we would get from python-ldap's
        :py:meth:`ldap.ldapobject.SimpleLDAPObject.search_s`:

        .. code-block:: python

            (DN, {'attr1': ['value'], 'attr2': ['value2'], ...})

        This data structure differs from python-ldap in that we don't prune
        attributes that have no value attached to them. Those attributes will
        have value ``[]``.

        We do this so that when :py:class:`ldaporm.managers.Modlist.modify` gets
        called, it can determine easily which attributes need to be deleted from
        the object in LDAP.

        Returns:
            A tuple of (dn, attrs) representing the model in LDAP format.

        """
        attrs = {}
        for field in cast("Options", self._meta).fields:
            attrs.update(field.to_db_value(field.value_from_object(self)))
        return (cast("str", self.dn), attrs)

    def __repr__(self) -> str:
        """
        Return a string representation of the model instance.

        Returns:
            A string representation including the class name.

        """
        return f"<{self.__class__.__name__}: {self}>"

    def __str__(self) -> str:
        """
        Return a string representation of the model instance.

        Returns:
            A string representation including the class name and DN.

        """
        return f"{self.__class__.__name__} object ({self.dn})"

    def __eq__(self, other: object) -> bool:
        """
        Compare this model instance with another.

        Equal means:

        - The same class
        - The same DN
        - The same primary key value

        Args:
            other: The object to compare with.

        Returns:
            True if the objects are equal, False otherwise.

        """
        if not isinstance(other, Model):
            return False
        if (
            cast("Options", self._meta).concrete_model
            != cast("Options", other._meta).concrete_model
        ):
            return False
        my_pk = self.pk
        if my_pk is None:
            return self is other
        return my_pk == other.pk

    def __hash__(self) -> int:
        """
        Return a hash value for this model instance.

        Returns:
            The hash of the DN.

        """
        return hash(self.dn)

    def _get_pk_val(self, meta: Options | None = None) -> Any:
        """
        Get the primary key value for this model instance.

        Args:
            meta: Optional Options instance. If None, uses self._meta.

        Returns:
            The primary key value.

        """
        _meta: Options = meta or cast("Options", self._meta)
        field = cast("Field", _meta.pk)
        return getattr(self, cast("str", field.name))

    def _set_pk_val(self, value: Any) -> None:
        """
        Set the primary key value for this model instance.

        Args:
            value: The new primary key value.

        """
        _meta = cast("Options", self._meta)
        field = cast("Field", _meta.pk)
        return setattr(self, cast("str", field.name), value)

    #: The primary key property for this model instance.
    pk = property(_get_pk_val, _set_pk_val)

    def _get_FIELD_display(self, field: Field) -> str:  # noqa: N802
        """
        Get the display value for a field with choices.

        Args:
            field: The field to get the display value for.

        Returns:
            The display value for the field.

        """
        value = getattr(self, cast("str", field.name))
        return force_text(dict(field.flatchoices).get(value, value), strings_only=True)

    @property
    def dn(self) -> str | None:
        """
        Get the distinguished name (DN) for this model instance.

        Returns:
            The DN string, or None if not set.

        """
        if self._dn:
            return self._dn
        _meta = cast("Options", self._meta)
        manager = cast("LdapManager", _meta.base_manager)
        return manager.dn(self)

    def save(self, commit: bool = True) -> None:  # noqa: ARG002
        """
        Save the model instance to LDAP.

        Args:
            commit: Whether to commit the changes (unused, kept for Django
                compatibility).

        """
        _meta = cast("Options", self._meta)
        manager = cast("LdapManager", _meta.base_manager)
        try:
            manager.get_by_dn(cast("str", self.dn))
        except self.DoesNotExist:
            manager.add(self)
        else:
            manager.modify(self)

    def delete(self) -> None:
        """
        Delete the model instance from LDAP.
        """
        _meta = cast("Options", self._meta)
        manager = cast("LdapManager", _meta.base_manager)
        manager.delete_obj(self)

    def clean(self) -> None:
        """
        Hook for doing any extra model-wide validation after we've cleaned
        field via :py:meth:`clean_fields`. Any ``ValidationError`` raised
        by this method will not be associated with a particular field; it will
        have a special-case association with the field defined by NON_FIELD_ERRORS.
        """

    def full_clean(
        self,
        exclude: list[str] | None = None,
        validate_unique: bool = True,  # noqa: ARG002
    ) -> None:
        """
        Perform full validation on the model instance.

        Args:
            exclude: List of field names to exclude from validation.
            validate_unique: Whether to validate uniqueness (unused, kept for
                Django compatibility).

        Raises:
            ValidationError: If validation fails.

        """
        errors: dict[str, Any] = {}
        exclude = [] if exclude is None else list(exclude)

        try:
            self.clean_fields(exclude=exclude)
        except ValidationError as e:
            errors = e.update_error_dict(errors)

        # Form.clean() is run even if other validation fails, so do the
        # same with Model.clean() for consistency.
        try:
            self.clean()
        except ValidationError as e:
            errors = e.update_error_dict(errors)

        if errors:
            raise ValidationError(errors)

    def clean_fields(self, exclude: list[str] | None = None) -> None:
        """
        Clean and validate individual fields.

        Args:
            exclude: List of field names to exclude from validation.

        Raises:
            ValidationError: If field validation fails.

        """
        _meta = cast("Options", self._meta)
        if exclude is None:
            exclude = []

        errors: dict[str, Any] = {}
        for f in _meta.fields:
            if f.name in exclude:
                continue
            raw_value = getattr(self, cast("str", f.name))
            if f.blank and raw_value == f.empty_values:
                continue
            try:
                setattr(self, cast("str", f.name), f.clean(raw_value, self))
            except ValidationError as e:
                errors[cast("str", f.name)] = e.error_list

        if errors:
            raise ValidationError(errors)

    def validate_unique(self, exclude: list[str] | None = None) -> None:
        """
        Validate that the model instance is unique.

        Args:
            exclude: List of field names to exclude from uniqueness validation.

        Note:
            This method is a placeholder for Django compatibility and does not
            perform actual uniqueness validation.

        """
