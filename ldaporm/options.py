from bisect import bisect
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Type, cast

from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.utils.functional import cached_property
from django.utils.text import camel_case_to_spaces, format_lazy
from django.utils.translation import override

from .managers import LdapManager
from .fields import CharListField

if TYPE_CHECKING:
    from .models import Model  # type: ignore  # noqa:F401
    from .fields import Field

DEFAULT_NAMES = (
    'ldap_server', 'ldap_options', 'manager_class', 'basedn', 'objectclass',
    'extra_objectclasses', 'verbose_name', 'verbose_name_plural', 'ordering',
    'permissions', 'default_permissions', 'password_attribute', 'userid_attribute'
)


class Options:

    def __init__(self, meta) -> None:
        # LDAP related
        self.ldap_server: str = 'default'
        self.ldap_options: List[str] = []
        self.manager_class: Type["LdapManager"] = LdapManager
        self.basedn: Optional[str] = None
        self.objectclass: Optional[str] = None
        self.extra_objectclasses: List[str] = []
        self.userid_attribute: str = 'uid'
        self.password_attribute: Optional[str] = None

        # other
        self.verbose_name: Optional[str] = None
        self.verbose_name_plural: Optional[str] = None
        self.ordering: List[str] = []
        self.default_permissions: Tuple[str, ...] = ('add', 'change', 'delete', 'view')
        self.permissions: List[str] = []

        # these are set up by the LdapModelBase metaclass
        self.model_name: Optional[str] = None
        self.object_name: Optional[str] = None
        self.meta = meta
        self.pk: Optional["Field"] = None
        self.concrete_model: Optional["Model"] = None
        self.base_manager: Optional["LdapManager"] = None
        self.local_fields: List["Field"] = []

        # self.get_latest_by = None

        # these need to be here to fool ModelForm
        self.local_many_to_many: List["Field"] = []
        self.private_fields: List["Field"] = []
        self.many_to_many: List["Field"] = []

    @property
    def label(self) -> str:
        return cast(str, self.object_name)

    @property
    def label_lower(self) -> str:
        return cast(str, self.model_name)

    @property
    def verbose_name_raw(self) -> str:
        """Return the untranslated verbose name."""
        with override(None):
            return str(self.verbose_name)

    def contribute_to_class(self, cls: Type["Model"], name: str) -> None:
        cls._meta = self
        self.model = cls
        # First, construct the default values for these options.
        self.object_name = cls.__name__
        self.model_name = self.object_name.lower()
        self.verbose_name = camel_case_to_spaces(self.object_name)

        # Next, apply any overridden values from 'class Meta'.
        if self.meta:
            meta_attrs = self.meta.__dict__.copy()
            for attr in self.meta.__dict__:
                # NOTE: We can't modify a dictionary's contents while looping
                # over it, so we loop over the *original* dictionary instead.
                if attr.startswith('_'):
                    del meta_attrs[attr]
            for attr_name in DEFAULT_NAMES:
                if attr_name in meta_attrs:
                    setattr(self, attr_name, meta_attrs.pop(attr_name))
                elif hasattr(self.meta, attr_name):
                    setattr(self, attr_name, getattr(self.meta, attr_name))

            # verbose_name_plural is a special case because it uses a 's'
            # by default.
            if self.verbose_name_plural is None:
                self.verbose_name_plural = format_lazy('{}s', self.verbose_name)

            # Any leftover attributes must be invalid.
            if meta_attrs != {}:
                raise TypeError("'class Meta' got invalid attribute(s): %s" % ','.join(meta_attrs))
        else:
            self.verbose_name_plural = format_lazy('{}s', self.verbose_name)
        del self.meta

    def _prepare(self, model: Type["Model"]) -> None:
        if self.pk is None:
            raise ImproperlyConfigured("'{}' model doesn't have a primary key".format(self.object_name))
        # Always make sure we have objectclass in our model, so we can filter by it
        # don't call self.attributes here, because that gets cached
        for f in self._get_fields():
            if f.ldap_attribute == 'objectclass':
                raise ImproperlyConfigured(
                    "The objectclass field is defined automatically; don't manaully define it "
                    "on the '{}' model".format(self.object_name)
                )
        objectclass = CharListField('objectclass', editable=False, max_length=255)
        model.add_to_class('objectclass', objectclass)

    def add_field(self, field: "Field") -> None:
        self.local_fields.insert(bisect(self.local_fields, field), field)
        self.setup_pk(field)

    def setup_pk(self, field: "Field") -> None:
        if not self.pk and field.primary_key:
            self.pk = field

    def __repr__(self) -> str:
        return '<Options for %s>' % self.object_name

    @cached_property
    def fields(self) -> List["Field"]:
        return self._get_fields()

    @property
    def concrete_fields(self) -> List["Field"]:
        # this is here to fool ModelForm
        return self.fields

    def get_fields(self, include_parents: bool = True, include_hidden: bool = False) -> List["Field"]:
        return self._get_fields()

    def _get_fields(self) -> List["Field"]:
        return self.local_fields

    @cached_property
    def fields_map(self) -> Dict[str, "Field"]:
        res = {}
        fields = self._get_fields()
        for field in fields:
            res[cast(str, field.name)] = field
        return res

    @cached_property
    def attributes_map(self) -> Dict[str, str]:
        res = {}
        fields = self._get_fields()
        for field in fields:
            res[cast(str, field.name)] = field.ldap_attribute
        return res

    @cached_property
    def attribute_to_field_name_map(self) -> Dict[str, str]:
        return {f.ldap_attribute: cast(str, f.name) for f in self._get_fields()}

    @cached_property
    def attributes(self) -> List[str]:
        return [f.ldap_attribute for f in self._get_fields()]

    def get_field(self, field_name: str) -> "Field":
        """
        Return a field instance given the name of a forward or reverse field.
        """
        try:
            # Retrieve field instance by name from cached or just-computed
            # field map.
            return self.fields_map[field_name]
        except KeyError:
            raise FieldDoesNotExist("%s has no field named '%s'" % (self.object_name, field_name))
