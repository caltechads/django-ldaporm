from bisect import bisect

from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.utils.functional import cached_property
from django.utils.text import camel_case_to_spaces, format_lazy
from django.utils.translation import override

from .managers import LdapManager
from .fields import CharListField


DEFAULT_NAMES = (
    'ldap_server', 'ldap_options', 'manager_class', 'basedn', 'objectclass',
    'extra_objectclasses', 'verbose_name', 'verbose_name_plural', 'ordering',
    'permissions', 'default_permissions',
)


class Options:

    def __init__(self, meta):
        # LDAP related
        self.ldap_server = 'default'
        self.ldap_options = []
        self.manager_class = LdapManager
        self.basedn = None
        self.objectclass = None
        self.extra_objectclasses = []

        # other
        self.verbose_name = None
        self.verbose_name_plural = None
        self.ordering = []
        self.default_permissions = ('add', 'change', 'delete', 'view')
        self.permissions = []

        # these are set up by the LdapModelBase metaclass
        self.model_name = None
        self.object_name = None
        self.meta = meta
        self.pk = None
        self.concrete_model = None
        self.base_manager = None
        self.local_fields = []

        # self.get_latest_by = None

        # these need to be here to fool ModelForm
        self.local_many_to_many = []
        self.private_fields = []
        self.many_to_many = []

    @property
    def label(self):
        return self.object_name
        # return '%s.%s' % (self.app_label, self.object_name)

    @property
    def label_lower(self):
        return self.model_name
        # return '%s.%s' % (self.app_label, self.model_name)

    @property
    def verbose_name_raw(self):
        """Return the untranslated verbose name."""
        with override(None):
            return str(self.verbose_name)

    def contribute_to_class(self, cls, name):
        cls._meta = self
        self.model = cls
        # First, construct the default values for these options.
        self.object_name = cls.__name__
        self.model_name = self.object_name.lower()
        self.verbose_name = camel_case_to_spaces(self.object_name)

        # Next, apply any overridden values from 'class Meta'.
        if self.meta:
            meta_attrs = self.meta.__dict__.copy()
            for name in self.meta.__dict__:
                # NOTE: We can't modify a dictionary's contents while looping
                # over it, so we loop over the *original* dictionary instead.
                if name.startswith('_'):
                    del meta_attrs[name]
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

    def _prepare(self, model):
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

    def add_field(self, field):
        self.local_fields.insert(bisect(self.local_fields, field), field)
        self.setup_pk(field)

    def setup_pk(self, field):
        if not self.pk and field.primary_key:
            self.pk = field
            field.serialize = False

    def __repr__(self):
        return '<Options for %s>' % self.object_name

    @cached_property
    def fields(self):
        return self._get_fields()

    @property
    def concrete_fields(self):
        # this is here to fool ModelForm
        return self.fields

    def get_fields(self, include_parents=True, include_hidden=False):
        return self._get_fields()

    def _get_fields(self):
        return self.local_fields

    @cached_property
    def fields_map(self):
        res = {}
        fields = self._get_fields()
        for field in fields:
            res[field.name] = field
        return res

    @cached_property
    def attributes_map(self):
        res = {}
        fields = self._get_fields()
        for field in fields:
            res[field.name] = field.ldap_attribute
        return res

    @cached_property
    def attribute_to_field_name_map(self):
        return {f.ldap_attribute: f.name for f in self._get_fields()}

    @cached_property
    def attributes(self):
        return [f.ldap_attribute for f in self._get_fields()]

    def get_field(self, field_name):
        """
        Return a field instance given the name of a forward or reverse field.
        """
        try:
            # Retrieve field instance by name from cached or just-computed
            # field map.
            return self.fields_map[field_name]
        except KeyError:
            raise FieldDoesNotExist("%s has no field named '%s'" % (self.object_name, field_name))
