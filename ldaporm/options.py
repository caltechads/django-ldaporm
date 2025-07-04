"""
LDAP ORM model options and metadata.

This module provides the Options class for managing LDAP model metadata, including
field mappings, LDAP server configuration, and model attributes.
"""

from bisect import bisect
from typing import TYPE_CHECKING, cast

from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.utils.functional import cached_property
from django.utils.text import camel_case_to_spaces, format_lazy
from django.utils.translation import override

from .fields import CharListField
from .managers import LdapManager

if TYPE_CHECKING:
    from .fields import Field
    from .models import Model

#: The default attributes for the Options class.
DEFAULT_NAMES = (
    "ldap_server",
    "ldap_options",
    "manager_class",
    "basedn",
    "objectclass",
    "extra_objectclasses",
    "verbose_name",
    "verbose_name_plural",
    "ordering",
    "permissions",
    "default_permissions",
    "password_attribute",
    "userid_attribute",
)


class Options:
    """
    Options class for LDAP model metadata and configuration.

    This class manages all the metadata for an LDAP model, including field
    mappings, LDAP server configuration, and model attributes. It provides
    Django-like model options interface for LDAP ORM models.

    This gets instantiated by parsing the ``Meta`` class for the model, and is
    available as ``model._meta`` on the model class.

    If you are subclassing another model, the ``Meta`` classes will be merged in
    MRO (Method Resolution Order) for the subclass.  This means that the
    ``Meta`` class for the subclass will have all the options from the parent
    class, plus any options that are defined or overridden in the subclass.

    Args:
        meta: The Meta class from the model definition.

    """

    def __init__(self, meta) -> None:
        # LDAP related
        #: The key into ``settings.LDAP_SERVERS`` setting that this model uses.
        self.ldap_server: str = "default"
        #: A list of options to pass to the LDAP server.  The only current option is
        #: ``paged_search`` which will enable paged searches.
        self.ldap_options: list[str] = []
        #: The default manager class to use for this model.  This is really only
        #: for internal use
        self.manager_class: type[LdapManager] = LdapManager
        #: The base DN for this model.
        self.basedn: str | None = None
        #: The objectclass for this model.  This will be automatically added to any
        #: search filters to eliminate objects that are not of this type.
        self.objectclass: str | None = None
        #: Extra objectclasses to add to this model when we are creating new records
        #: only. :py:attr:`objectclass` is always added to the object.
        self.extra_objectclasses: list[str] = []
        #: The attribute to use for the userid.  This is used to identify the user
        #: when we are searching for them.  If this is not a user model, this
        #: will be ignored.
        self.userid_attribute: str = "uid"
        #: The attribute to use for the password.  This is used to store the
        #: password for the user.  If this is not a user model, this will be
        #: ignored.
        self.password_attribute: str | None = None

        # other
        #: The verbose name for this model.
        self.verbose_name: str | None = None
        #: The verbose name plural for this model.
        self.verbose_name_plural: str | None = None
        #: The default ordering for this model.  This is a list of field names to order
        #: by.  The fields can be prefixed with ``-`` to order in descending order.
        self.ordering: list[str] = []
        #: The default permissions for this model.  This is a tuple of the
        #: permissions that are applied to the model by default.  This is here
        #: really just to fool Django's ModelForm.
        self.default_permissions: tuple[str, ...] = ("add", "change", "delete", "view")
        #: The permissions for this model.  This is a list of the permissions
        #: that are applied to the model.  This is here really just to fool
        #: Django's ModelForm.
        self.permissions: list[str] = []

        #: This is set up by the :py:class:`~ldaporm.models.LdapModelBase``
        #: metaclass.  It is not intended to be set by the user.
        self.model_name: str | None = None
        #: This is set up by the :py:class:`~ldaporm.models.LdapModelBase``
        #: metaclass.  It is not intended to be set by the user.
        self.object_name: str | None = None
        #: This is set up by the :py:class:`~ldaporm.models.LdapModelBase``
        #: metaclass.  It is not intended to be set by the user.
        self.meta = meta
        #: This is set up by the :py:class:`~ldaporm.models.LdapModelBase``
        #: metaclass.  It is not intended to be set by the user.  It will be
        #: set to the Field with ``primary_key=True`` on the model.
        self.pk: Field | None = None
        #: This is set up by the :py:class:`~ldaporm.models.LdapModelBase``
        #: metaclass.  It is not intended to be set by the user.
        self.concrete_model: Model | None = None
        #: This is set up by the :py:class:`~ldaporm.models.LdapModelBase``
        #: metaclass.  It is not intended to be set by the user.
        self.base_manager: LdapManager | None = None
        #: This is set up by the :py:class:`~ldaporm.models.LdapModelBase``
        #: metaclass.  It is not intended to be set by the user.
        self.local_fields: list[Field] = []

        #: Unused.  This is here really just to fool Django's ModelForm.
        self.local_many_to_many: list[Field] = []
        #: Unused.  This is here really just to fool Django's ModelForm.
        self.private_fields: list[Field] = []
        #: Unused.  This is here really just to fool Django's ModelForm.
        self.many_to_many: list[Field] = []

    @property
    def label(self) -> str:
        """
        Get the model label (object name).

        Returns:
            The model's object name.

        """
        return cast("str", self.object_name)

    @property
    def label_lower(self) -> str:
        """
        Get the lowercase model label.

        Returns:
            The lowercase model name.

        """
        return cast("str", self.model_name)

    @property
    def verbose_name_raw(self) -> str:
        """
        Return the untranslated verbose name.

        Returns:
            The untranslated verbose name.

        """
        with override(None):
            return str(self.verbose_name)

    def contribute_to_class(self, cls: type["Model"], name: str) -> None:  # noqa: ARG002
        """
        Used by the :py:class:`~ldaporm.models.LdapModelBase`` metaclass to
        add this :py:class:`Options` instance to a model class.

        Args:
            cls: The model class to contribute to.
            name: The name of the options attribute.

        """
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
                if attr.startswith("_"):
                    del meta_attrs[attr]
            for attr_name in DEFAULT_NAMES:
                if attr_name in meta_attrs:
                    setattr(self, attr_name, meta_attrs.pop(attr_name))
                elif hasattr(self.meta, attr_name):
                    setattr(self, attr_name, getattr(self.meta, attr_name))

            # verbose_name_plural is a special case because it uses a 's'
            # by default.
            if self.verbose_name_plural is None:
                # format_lazy returns _StrPromise but we need str
                self.verbose_name_plural = format_lazy("{}s", self.verbose_name)  # type: ignore[assignment]

            # Any leftover attributes must be invalid.
            if meta_attrs != {}:
                msg = "'class Meta' got invalid attribute(s): {}".format(
                    ",".join(meta_attrs)
                )
                raise TypeError(msg)
        else:
            # format_lazy returns _StrPromise but we need str
            self.verbose_name_plural = format_lazy("{}s", self.verbose_name)  # type: ignore[assignment]
        del self.meta

    def _prepare(self, model: type["Model"]) -> None:
        """
        Used by the :py:class:`~ldaporm.models.LdapModelBase`` metaclass to
        prepare the model after all fields have been added.

        Args:
            model: The model class to prepare.

        Raises:
            ImproperlyConfigured: If the model doesn't have a primary key or
                has a manually defined objectclass field.

        """
        if self.pk is None:
            msg = f"'{self.object_name}' model doesn't have a primary key"
            raise ImproperlyConfigured(msg)
        # Always make sure we have objectclass in our model, so we can filter by it
        # don't call self.attributes here, because that gets cached
        for f in self._get_fields():
            if f.ldap_attribute == "objectclass":
                msg = (
                    "The objectclass field is defined automatically; don't "
                    f"manually define it on the '{self.object_name}' model"
                )
                raise ImproperlyConfigured(msg)
        objectclass = CharListField("objectclass", editable=False, max_length=255)
        model.add_to_class("objectclass", objectclass)

    def add_field(self, field: "Field") -> None:
        """
        Used by the :py:class:`~ldaporm.models.LdapModelBase`` metaclass to
        add a field to the model.

        Args:
            field: The field to add.

        """
        self.local_fields.insert(bisect(self.local_fields, field), field)
        self.setup_pk(field)

    def setup_pk(self, field: "Field") -> None:
        """
        Used by the :py:class:`~ldaporm.models.LdapModelBase`` metaclass to
        set up the primary key field.

        Args:
            field: The field to check for primary key status.

        """
        if not self.pk and field.primary_key:
            self.pk = field

    def __repr__(self) -> str:
        """
        Return a string representation of the Options instance.

        Returns:
            A string representation including the object name.

        """
        return f"<Options for {self.object_name}>"

    @cached_property
    def fields(self) -> list["Field"]:
        """
        Get all fields for this model.

        Returns:
            A list of all fields.

        """
        return self._get_fields()

    @property
    def concrete_fields(self) -> list["Field"]:
        """
        Get concrete fields for this model (alias for fields).

        This is here to fool Django's :py:class:`~django.forms.ModelForm`.

        Returns:
            A list of all fields.

        """
        return self.fields

    def get_fields(
        self,
        include_parents: bool = True,  # noqa: ARG002
        include_hidden: bool = False,  # noqa: ARG002
    ) -> list["Field"]:
        """
        Get fields for this model.  This is here to fool Django's
        :py:class:`~django.forms.ModelForm`.

        Args:
            include_parents: Whether to include parent fields (unused).
            include_hidden: Whether to include hidden fields (unused).

        Returns:
            A list of all fields.

        """
        return self._get_fields()

    def _get_fields(self) -> list["Field"]:
        """
        Get the local fields for this model.

        Returns:
            A list of local fields.

        """
        return self.local_fields

    @cached_property
    def fields_map(self) -> dict[str, "Field"]:
        """
        Get a mapping of field names to field instances.  This is used by
        the :py:class:`~ldaporm.manager.LdapManager`` to get the field
        instances for a model.

        Returns:
            A dictionary mapping field names to field instances.

        """
        res = {}
        fields = self._get_fields()
        for field in fields:
            res[cast("str", field.name)] = field
        return res

    @cached_property
    def attributes_map(self) -> dict[str, str]:
        """
        Get a mapping of field names to LDAP attribute names.  This is used by
        the :py:class:`~ldaporm.manager.LdapManager`` to map LDAP attribute names
        to :py:class:`~ldaporm.fields.Field` instances for a model.

        Returns:
            A dictionary mapping field names to LDAP attribute names.

        """
        res = {}
        fields = self._get_fields()
        for field in fields:
            res[cast("str", field.name)] = field.ldap_attribute
        return res

    @cached_property
    def attribute_to_field_name_map(self) -> dict[str, str]:
        """
        Get a mapping of LDAP attribute names to field names.  This is used by
        the :py:class:`~ldaporm.manager.LdapManager`` to map LDAP attribute names
        to python field names for a model.

        Returns:
            A dictionary mapping LDAP attribute names to field names.

        """
        return {f.ldap_attribute: cast("str", f.name) for f in self._get_fields()}

    @cached_property
    def attributes(self) -> list[str]:
        """
        Get a list of LDAP attribute names for all fields.  This is used by
        the :py:class:`~ldaporm.manager.LdapManager`` to get the LDAP attribute
        names for a model.

        Returns:
            A list of LDAP attribute names.

        """
        return [f.ldap_attribute for f in self._get_fields()]

    def get_field(self, field_name: str) -> "Field":
        """
        Return a field instance given the name of a forward or reverse field.

        Args:
            field_name: The name of the field to retrieve.

        Returns:
            The field instance.

        Raises:
            FieldDoesNotExist: If no field with the given name exists.

        """
        try:
            # Retrieve field instance by name from cached or just-computed
            # field map.
            return self.fields_map[field_name]
        except KeyError as e:
            msg = f"{self.object_name} has no field named '{field_name}'"
            raise FieldDoesNotExist(msg) from e
