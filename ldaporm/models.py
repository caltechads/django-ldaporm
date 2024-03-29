from base64 import b64encode as encode
import hashlib
import inspect
import os
from typing import Any, Dict, List, Optional, Sequence, Union, cast

from django.core.exceptions import ValidationError, FieldDoesNotExist
try:
    from django.utils.encoding import force_text
except ImportError:
    from django.utils.encoding import force_str as force_text  # type: ignore
from django.db.models.signals import (
    class_prepared,
    post_init,
    pre_init
)
from ldaporm.fields import Field
from ldaporm.managers import LdapManager
from ldaporm.typing import LDAPData

from .options import Options


class LdapModelBase(type):

    def __new__(cls, name, bases, attrs, **kwargs):
        super_new = super().__new__
        parents = [b for b in bases if isinstance(b, LdapModelBase)]
        if not parents:
            return super_new(cls, name, bases, attrs)

        # Create the class.
        module = attrs.pop('__module__')
        new_attrs = {'__module__': module}
        classcell = attrs.pop('__classcell__', None)
        if classcell is not None:
            new_attrs['__classcell__'] = classcell
        new_class = super_new(cls, name, bases, new_attrs, **kwargs)
        attr_meta = attrs.pop('Meta', None)
        meta = attr_meta or getattr(new_class, 'Meta', None)

        # Add our Meta class.  This simluates the Django ORM Meta class
        # enough that ModelForm will work for us, among other things
        new_class.add_to_class('_meta', Options(meta))

        # Add all attributes to the class.  This is where the fields get
        # initialized
        for obj_name, obj in attrs.items():
            new_class.add_to_class(obj_name, obj)

        new_class._meta.concrete_model = new_class
        new_class._prepare()

        return new_class

    def add_to_class(cls, name: str, value: Any) -> None:
        # We should call the contribute_to_class method only if it's bound
        if not inspect.isclass(value) and hasattr(value, 'contribute_to_class'):
            value.contribute_to_class(cls, name)
        else:
            setattr(cls, name, value)

    def _prepare(cls) -> None:
        """
        Create some methods once self._meta has been populated.

        Importantly, this is where the Manager class gets added.
        """
        opts = cls._meta   # type: ignore
        opts._prepare(cls)

        # Give the class a docstring -- its definition.
        if cls.__doc__ is None:
            cls.__doc__ = "%s(%s)" % (cls.__name__, ", ".join(f.name for f in opts.fields))

        if any(f.name == 'objects' for f in opts.fields):
            raise ValueError(
                "Model %s must specify a custom Manager, because it has a "
                "field named 'objects'." % cls.__name__
            )
        manager = opts.manager_class()
        cls.add_to_class('objects', manager)  # pylint: disable=no-value-for-parameter
        class_prepared.send(sender=cls)


class Model(metaclass=LdapModelBase):

    class DoesNotExist(Exception):
        pass

    class InvalidField(Exception):
        pass

    class MultipleObjectsReturned(Exception):
        pass

    _meta: Optional[Options] = None
    objects: Optional[LdapManager] = None

    def __init__(self, *args, **kwargs) -> None:
        cls = self.__class__
        opts = cast(Options, self._meta)
        _setattr = setattr
        self._dn: Optional[str] = None

        pre_init.send(sender=cls, args=args, kwargs=kwargs)

        if len(args) > len(opts.fields):
            # Daft, but matches old exception sans the err msg.
            raise IndexError("Number of args exceeds number of fields")

        if not kwargs:
            fields_iter = iter(opts.fields)
            for val, field in zip(args, fields_iter):
                _setattr(self, cast(str, field.name), val)
        else:
            # Slower, kwargs-ready version.
            fields_iter = iter(opts.fields)
            for val, field in zip(args, fields_iter):
                _setattr(self, cast(str, field.name), val)
                kwargs.pop(cast(str, field.name), None)

        # Now we're left with the unprocessed fields that *must* come from
        # keywords, or default.

        for field in fields_iter:
            if kwargs:
                try:
                    val = kwargs.pop(cast(str, field.name))
                except KeyError:
                    # This is done with an exception rather than the
                    # default argument on pop because we don't want
                    # get_default() to be evaluated, and then not used.
                    # Refs #12057.
                    val = field.get_default()
            else:
                val = field.get_default()
            _setattr(self, cast(str, field.name), val)

        if kwargs and '_dn' in kwargs:
            _setattr(self, '_dn', kwargs['_dn'])
            kwargs.pop('_dn')

        if kwargs:
            for kwarg in kwargs:
                raise TypeError("'%s' is an invalid keyword argument for this function" % kwarg)
        super().__init__()
        post_init.send(sender=cls, instance=self)

    @classmethod
    def from_db(
        cls,
        attributes: List[str],
        objects: Union[LDAPData, Sequence[LDAPData]],
        many: bool = False
    ) -> Union["Model", Sequence["Model"]]:
        """
        ``objects`` is a list of raw LDAP data objects
        ``attributes`` is a
        we need to convert from the raw ldap value to the value our field stores internally

        """
        if not isinstance(objects, list):
            objects = [cast(LDAPData, objects)]
        if not many and len(objects) > 1:
            raise RuntimeError('Called {}.from_db() with many=False but len(objects) > 1'.format(
                cast(Options, cls._meta).object_name)
            )
        _attr_lookup = cast(Options, cls._meta).attribute_to_field_name_map
        _field_lookup = cast(Options, cls._meta).fields_map
        for attr in attributes:
            if attr not in _attr_lookup:
                raise FieldDoesNotExist(
                    'No field on model {} corresponding to LDAP attribute "{}"'.format(
                        cast(Options, cls._meta).object_name, attr
                    )
                )
        rows = []
        for obj in objects:
            if not isinstance(obj[1], dict):
                continue
            # Case sensitivity does not matter in LDAP, but it does when we're looking up keys in our dict here.  Deal
            # with the case for when we have a different case on our field name than what LDAP returns
            obj_attr_lookup = {k.lower(): k for k in obj[1]}
            kwargs = {}
            kwargs['_dn'] = obj[0]
            for attr in attributes:
                name = _attr_lookup[attr]
                try:
                    value: Any = obj[1][obj_attr_lookup[attr.lower()]]
                except KeyError:
                    # if the object in LDAP doesn't have that data, the
                    # attribute won't be present in the response
                    continue
                kwargs[name] = _field_lookup[name].from_db_value(value)
            rows.append(cls(**kwargs))
        if not many:
            return rows[0]
        return rows

    @classmethod
    def _default_manager(cls) -> "LdapManager":
        return cast("LdapManager", cls.objects)

    @classmethod
    def get_password_hash(cls, password: str) -> bytes:
        salt = os.urandom(8)
        h = hashlib.sha1(password.encode('utf-8'))
        h.update(salt)
        pwhash = "{SSHA}".encode('utf-8') + encode(h.digest() + salt)
        return pwhash

    def to_db(self) -> LDAPData:
        """
        ``to_db`` produces 2-tuple similar to what we would get from
        python-ldap's .search_s().::

            ( __DN__, {'attr1': ['value'], 'attr2': ['value2'], ...} )

        This data structure differs from python-ldap in that we don't prune
        attributes that have no value attached to them.  Those attributes will
        have value `[]`.

        We do this so that when ldaporm.managers.Modlist.modify() gets
        called, it can determine easily which attributes need to be deleted from
        the object in LDAP.
        """
        attrs = {}
        for field in cast(Options, self._meta).fields:
            attrs.update(field.to_db_value(field.value_from_object(self)))
        return (cast(str, self.dn), attrs)

    def __repr__(self) -> str:
        return '<%s: %s>' % (self.__class__.__name__, self)

    def __str__(self) -> str:
        return '%s object (%s)' % (self.__class__.__name__, self.dn)

    def __eq__(self, other) -> bool:
        if not isinstance(other, Model):
            return False
        if cast(Options, self._meta).concrete_model != cast(Options, other._meta).concrete_model:
            return False
        my_pk = self.pk
        if my_pk is None:
            return self is other
        return my_pk == other.pk

    def __hash__(self) -> int:
        return hash(self.dn)

    def _get_pk_val(self, meta: Options = None) -> Any:
        _meta: Options = meta or cast(Options, self._meta)
        field = cast(Field, _meta.pk)
        return getattr(self, cast(str, field.name))

    def _set_pk_val(self, value: Any) -> None:
        _meta = cast(Options, self._meta)
        field = cast(Field, _meta.pk)
        return setattr(self, cast(str, field.name), value)

    pk = property(_get_pk_val, _set_pk_val)

    def _get_FIELD_display(self, field: Field) -> str:
        value = getattr(self, cast(str, field.name))
        return force_text(dict(field.flatchoices).get(value, value), strings_only=True)

    @property
    def dn(self) -> Optional[str]:
        if self._dn:
            return self._dn
        _meta = cast(Options, self._meta)
        manager = cast(LdapManager, _meta.base_manager)
        return manager.dn(self)

    def save(self, commit: bool = True) -> None:
        _meta = cast(Options, self._meta)
        manager = cast(LdapManager, _meta.base_manager)
        try:
            manager.get_by_dn(cast(str, self.dn))
        except self.DoesNotExist:
            manager.add(self)
        else:
            manager.modify(self)

    def delete(self) -> None:
        _meta = cast(Options, self._meta)
        manager = cast(LdapManager, _meta.base_manager)
        manager.delete_obj(self)

    def clean(self) -> None:
        """
        Hook for doing any extra model-wide validation after clean() has been
        called on every field by self.clean_fields. Any ValidationError raised
        by this method will not be associated with a particular field; it will
        have a special-case association with the field defined by NON_FIELD_ERRORS.
        """
        pass

    def full_clean(self, exclude: List[str] = None, validate_unique: bool = True) -> None:
        """
        validate_unique is here to fool ModelForm into thinking we're a Django ORM Model
        """
        errors: Dict[str, Any] = {}
        if exclude is None:
            exclude = []
        else:
            exclude = list(exclude)

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

    def clean_fields(self, exclude: List[str] = None) -> None:
        _meta = cast(Options, self._meta)
        if exclude is None:
            exclude = []

        errors: Dict[str, Any] = {}
        for f in _meta.fields:
            if f.name in exclude:
                continue
            raw_value = getattr(self, cast(str, f.name))
            if f.blank and raw_value == f.empty_values:
                continue
            try:
                setattr(self, cast(str, f.name), f.clean(raw_value, self))
            except ValidationError as e:
                errors[cast(str, f.name)] = e.error_list

        if errors:
            raise ValidationError(errors)

    def validate_unique(self, exclude: List[str] = None) -> None:
        pass
