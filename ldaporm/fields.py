from base64 import b64encode as encode

import collections.abc
import datetime
from functools import partialmethod, total_ordering
import hashlib
import os
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple, Type, TypeVar, Optional, Union
import warnings

import pytz

from django import forms
from django.conf import settings
from django.core import checks, exceptions, validators
from django.db.models.constants import LOOKUP_SEP
from django.db.models.fields import BLANK_CHOICE_DASH, NOT_PROVIDED, return_None
from django.utils import timezone
from django.utils.dateparse import (
    parse_date,
    parse_datetime
)
from django.utils.functional import cached_property
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _

from . import forms as ldap_forms
from .validators import validate_email_forward

if TYPE_CHECKING:
    from .models import Model


FieldValue = TypeVar("FieldValue")
Validator = Callable[[FieldValue], None]


@total_ordering
class Field:

    """
    This is enough of a django.db.models.fields.Field implementation to allow us
    to build Django ORM-like models and fool ModelForm into working for us.
    """

    empty_strings_allowed: bool = True
    empty_values: List[Any] = list(validators.EMPTY_VALUES)
    creation_counter: int = 0

    default_validators: List[Validator] = []  # Default set of validators
    default_error_messages: Dict[str, str] = {
        'invalid_choice': _('Value %(value)r is not a valid choice.'),
        'null': _('This field cannot be null.'),
        'blank': _('This field cannot be blank.'),
    }

    # These are here to fool ModelForm into thinking we're a Django ORM Field. We
    # don't actually use them.
    many_to_many = None
    many_to_one = None
    one_to_many = None
    one_to_one = None
    related_model = None

    # Field flags
    hidden: bool = False

    # Generic field type description, usually overridden by subclasses
    def _description(self) -> str:
        return _('Field of type: %(field_type)s') % {
            'field_type': self.__class__.__name__
        }
    description = property(_description)

    def __init__(
        self,
        verbose_name: str = None,
        name: str = None,
        primary_key: str = False,
        max_length: int = None,
        blank: bool = False,
        null: bool = False,
        default: FieldValue = NOT_PROVIDED,
        editable: bool = True,
        choices: bool = None,
        help_text: str = '',
        validators=(),
        error_messages: List[str] = None,
        db_column: str = None
    ) -> None:
        self.name = name
        self.verbose_name = verbose_name  # May be set by set_attributes_from_name
        self.primary_key = primary_key
        self.max_length = max_length
        self.blank, self.null = blank, null
        self.default = default
        self.editable = editable
        if isinstance(choices, collections.abc.Iterator):
            choices = list(choices)
        self.choices = choices or []
        self.help_text = help_text
        self.blank = True
        self.db_column = db_column

        self.model: Type["Model"] = None

        self.creation_counter = Field.creation_counter
        Field.creation_counter += 1

        self._validators = list(validators)  # Store for deconstruction later

        messages = {}
        for c in reversed(self.__class__.__mro__):
            messages.update(getattr(c, 'default_error_messages', {}))
        messages.update(error_messages or {})
        self.error_messages = messages

    def __repr__(self) -> str:
        """Display the module, class, and name of the field."""
        path = '%s.%s' % (self.__class__.__module__, self.__class__.__qualname__)
        name = getattr(self, 'name', None)
        if name is not None:
            return '<%s: %s>' % (path, name)
        return '<%s>' % path

    def __lt__(self, other: "Field") -> bool:
        """
        We need to implement this because django.forms.models.fields_from_model
        tries to sort all the fields on a model before interrogating them for
        which form field class they need.
        """
        if isinstance(other, Field):
            return self.creation_counter < other.creation_counter
        raise NotImplementedError

    def __eq__(self, other: "Field") -> bool:
        if isinstance(other, Field):
            return self.creation_counter == other.creation_counter
        return NotImplementedError

    def __hash__(self) -> int:
        return hash(self.creation_counter)

    def has_default(self) -> bool:
        """Return a boolean of whether this field has a default value."""
        return self.default is not NOT_PROVIDED

    def get_default(self) -> FieldValue:
        """Return the default value for this field."""
        return self._get_default()

    def check(self, **kwargs) -> List[Union[checks.Error, checks.Warning]]:
        return [
            *self._check_field_name(),
            *self._check_choices(),
            *self._check_null_allowed_for_primary_keys(),
            *self._check_validators(),
        ]

    def _check_field_name(self) -> List[checks.Error]:
        """
        Check if field name is valid, i.e. 1) does not end with an
        underscore, 2) does not contain "__" and 3) is not "pk".
        """
        if self.name.endswith('_'):
            return [
                checks.Error(
                    'Field names must not end with an underscore.',
                    obj=self,
                    id='fields.E001',
                )
            ]
        if LOOKUP_SEP in self.name:
            return [
                checks.Error(
                    'Field names must not contain "%s".' % (LOOKUP_SEP,),
                    obj=self,
                    id='fields.E002',
                )
            ]
        if self.name == 'pk':
            return [
                checks.Error(
                    "'pk' is a reserved word that cannot be used as a field name.",
                    obj=self,
                    id='fields.E003',
                )
            ]
        return []

    def _check_choices(self) -> List[checks.Error]:
        if not self.choices:
            return []

        def is_value(value):
            return isinstance(value, str)

        if is_value(self.choices):
            return [
                checks.Error(
                    "'choices' must be an iterable (e.g., a list or tuple).",
                    obj=self,
                    id='fields.E004',
                )
            ]

        # Expect [group_name, [value, display]]
        for choices_group in self.choices:
            try:
                group_name, group_choices = choices_group
            except ValueError:
                # Containing non-pairs
                break
            try:
                if not all(
                    is_value(value) and is_value(human_name)
                    for value, human_name in group_choices
                ):
                    break
            except (TypeError, ValueError):
                # No groups, choices in the form [value, display]
                value, human_name = group_name, group_choices
                if not is_value(value) or not is_value(human_name):
                    break

            # Special case: choices=['ab']
            if isinstance(choices_group, str):
                break
        else:
            return []

        return [
            checks.Error(
                "'choices' must be an iterable containing "
                "(actual value, human readable name) tuples.",
                obj=self,
                id='fields.E005',
            )
        ]

    def _check_null_allowed_for_primary_keys(self) -> List[checks.Error]:
        if (self.primary_key and self.null):
            return [
                checks.Error(
                    'Primary keys must not have null=True.',
                    hint=('Set null=False on the field, or '
                          'remove primary_key=True argument.'),
                    obj=self,
                    id='fields.E007',
                )
            ]
        return []

    def _check_validators(self) -> List[checks.Error]:
        errors = []
        for i, validator in enumerate(self.validators):
            if not callable(validator):
                errors.append(
                    checks.Error(
                        "All 'validators' must be callable.",
                        hint=(
                            "validators[{i}] ({repr}) isn't a function or "
                            "instance of a validator class.".format(
                                i=i, repr=repr(validator),
                            )
                        ),
                        obj=self,
                        id='fields.E008',
                    )
                )
        return errors

    @property
    def ldap_attribute(self) -> str:
        return self.db_column or self.name

    @cached_property
    def _get_default(self) -> FieldValue:
        if self.has_default():
            if callable(self.default):
                return self.default
            return lambda: self.default

        if not self.empty_strings_allowed or self.null:
            return return_None
        return str  # return empty string

    def to_python(self, value: FieldValue) -> FieldValue:
        return value

    @cached_property
    def validators(self) -> List[Validator]:
        return [*self.default_validators, *self._validators]

    def run_validators(self, value: FieldValue) -> None:
        if value in self.empty_values:
            return

        errors = []
        for v in self.validators:
            try:
                v(value)
            except exceptions.ValidationError as e:
                if hasattr(e, 'code') and e.code in self.error_messages:
                    e.message = self.error_messages[e.code]
                errors.extend(e.error_list)

        if errors:
            raise exceptions.ValidationError(errors)

    def validate(self, value: FieldValue, model_instance: "Model") -> None:
        """
        Validate value and raise ValidationError if necessary. Subclasses
        should override this to provide validation logic.
        """
        if not self.editable:
            # Skip validation for non-editable fields.
            return

        if self.choices and value not in self.empty_values:
            for option_key, option_value in self.choices:
                if isinstance(option_value, (list, tuple)):
                    # This is an optgroup, so look inside the group for
                    # options.
                    for optgroup_key, optgroup_value in option_value:  # pylint: disable=unused-variable
                        if value == optgroup_key:
                            return
                elif value == option_key:
                    return
            raise exceptions.ValidationError(
                self.error_messages['invalid_choice'],
                code='invalid_choice',
                params={'value': value},
            )

        if value is None and not self.null:
            raise exceptions.ValidationError(self.error_messages['null'], code='null')

        if not self.blank and value in self.empty_values:
            raise exceptions.ValidationError(self.error_messages['blank'], code='blank')

    def pre_save(self, model_instance: "Model", add: bool) -> FieldValue:
        """Return field's value just before saving."""
        return getattr(model_instance, self.attname)

    def clean(self, value: FieldValue, model_instance: "Model") -> FieldValue:
        """
        Convert the value's type and run validation. Validation errors
        from to_python() and validate() are propagated. Return the correct
        value if no error is raised.
        """
        value = self.to_python(value)
        self.validate(value, model_instance)
        self.run_validators(value)
        return value

    def set_attributes_from_name(self, name: str) -> None:
        self.name = self.name or name
        self.attname = self.name
        if self.verbose_name is None and self.name:
            self.verbose_name = self.name.replace('_', ' ')

    def get_choices(
        self,
        include_blank: bool = True,
        blank_choice: str = None,
        limit_choices_to: Any = None
    ):
        """
        Return choices with a default blank choices included, for use as
        <select> choices for this field.
        """
        if not blank_choice:
            blank_choice = BLANK_CHOICE_DASH
        if self.choices:
            choices = list(self.choices)
            if include_blank:
                blank_defined = any(choice in ('', None) for choice, _ in self.flatchoices)
                if not blank_defined:
                    choices = blank_choice + choices
            return choices
        return blank_choice

    def limit_choices_to(self):
        raise NotImplementedError

    def _get_flatchoices(self) -> List[Tuple[str, Any]]:
        """Flattened version of choices tuple."""
        flat = []
        for choice, value in self.choices:
            if isinstance(value, (list, tuple)):
                flat.extend(value)
            else:
                flat.append((choice, value))
        return flat
    flatchoices = property(_get_flatchoices)

    def formfield(
        self,
        form_class: Type[forms.Field] = None,
        choices_form_class: Type[forms.Field] = None,
        **kwargs
    ) -> forms.Field:
        """Return a django.forms.Field instance for this field."""
        defaults = {'required': not self.blank,
                    'label': capfirst(self.verbose_name),
                    'help_text': self.help_text}
        if self.has_default():
            if callable(self.default):
                defaults['initial'] = self.default
                defaults['show_hidden_initial'] = True
            else:
                defaults['initial'] = self.get_default()
        if self.choices:
            # Fields with choices get special treatment.
            include_blank = (self.blank or
                             not (self.has_default() or 'initial' in kwargs))
            defaults['choices'] = self.get_choices(include_blank=include_blank)
            defaults['coerce'] = self.to_python
            if self.null:
                defaults['empty_value'] = None
            if choices_form_class is not None:
                form_class = choices_form_class
            else:
                form_class = forms.TypedChoiceField
            # Many of the subclass-specific formfield arguments (min_value,
            # max_value) don't apply for choice fields, so be sure to only pass
            # the values that TypedChoiceField will understand.
            for k in list(kwargs):
                if k not in ('coerce', 'empty_value', 'choices', 'required',
                             'widget', 'label', 'initial', 'help_text',
                             'error_messages', 'show_hidden_initial', 'disabled'):
                    del kwargs[k]
        defaults.update(kwargs)
        if form_class is None:
            form_class = forms.CharField
        return form_class(**defaults)

    def value_from_object(self, obj: "Model") -> FieldValue:
        return getattr(obj, self.name)

    def from_db_value(self, value: List[bytes]) -> List[str]:
        """
        Take data for one attribute from LDAP and convert it to our internal
        python format.

        ``value`` will always be a list of byte strings.

        Subclasses should implement the actual logic for this, but
        first call ``super().from_db_value(value)`` to convert the byte
        strings in the list to unicode strings.

        :rtype: varies
        """
        return [b.decode('utf-8') for b in value]

    def to_db_value(self, value: List[FieldValue]) -> Dict[str, List[bytes]]:
        # Subclasses should implement this and do proper casting of the value
        # from our internal data type to the appropriate value to stuff into LDAP
        # and then call super().to_db_value(value)
        if value is None:
            value = []
        if not isinstance(value, list):
            if value not in self.empty_values:
                value = [value]
            else:
                value = []
        # LDAP doesn't like unicode strings; it wants bytes.
        cleaned = []
        for item in value:
            if isinstance(item, str):
                item = item.encode('utf-8')
            cleaned.append(item)
        return {self.ldap_attribute: cleaned}

    def value_to_string(self, obj: "Model") -> str:
        return str(self.value_from_object(obj))

    def save_form_data(self, obj: "Model", value: FieldValue) -> None:
        """
        This is what django.forms.models.ModelForm calls to save data to our
        LdapModel instance.
        """
        setattr(obj, self.name, value)

    def contribute_to_class(self, cls, name: str) -> None:
        """
        Register the field with the model class it belongs to.
        """
        self.set_attributes_from_name(name)
        self.model = cls
        self.check()
        cls._meta.add_field(self)
        if self.choices:
            setattr(cls, 'get_{}_display'.format(self.name), partialmethod(cls._get_FIELD_display, field=self))


class BooleanField(Field):

    """
    This is a boolean field which stores data internally as bool() but stores
    the strings 'true' and 'false' in LDAP.
    """

    empty_strings_allowed: bool = False

    default_error_messages: Dict[str, str] = {
        'invalid': _("'%(value)s' value must be either True or False."),
        'invalid_nullable': _("'%(value)s' value must be either True, False, or None."),
    }

    description: str = _("Boolean (Either True or False)")

    LDAP_TRUE: str = 'true'
    LDAP_FALSE: str = 'false'

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.blank = True

    def to_python(self, value: Union[None, bool, str]) -> Optional[bool]:
        if self.null and value in self.empty_values:
            return None
        if value in (True, False):
            # if value is 1 or 0 than it's equal to True or False, but we want
            # to return a true bool for semantic reasons.
            return bool(value)
        if value in ('t', 'True', '1'):
            return True
        if value in ('f', 'False', '0'):
            return False
        raise exceptions.ValidationError(
            self.error_messages['invalid_nullable' if self.null else 'invalid'],
            code='invalid',
            params={'value': value},
        )

    def from_db_value(self, value: List[bytes]) -> Optional[bool]:
        value = super().from_db_value(value)
        if value == []:
            return None
        if value[0].lower() == self.LDAP_TRUE:
            return True
        if value[0].lower() == self.LDAP_FALSE:
            return False
        if value == [self.LDAP_TRUE]:
            return True
        if value == [self.LDAP_FALSE]:
            return False
        raise ValueError('Field "{}" (BooleanField) on model {} got got unexpected data from LDAP: {}'.format(
            self.name,
            self.model._meta.object_name,
            value
        ))

    def to_db_value(self, value: Optional[bool]) -> Dict[str, List[bytes]]:
        if value is not None:
            if value:
                value = self.LDAP_TRUE
            else:
                value = self.LDAP_FALSE
        return super().to_db_value(value)

    def formfield(
        self,
        form_class: Type[forms.Field] = None,
        choices_form_class: Type[forms.Field] = None,
        **kwargs
    ) -> forms.Field:
        if self.choices:
            include_blank = not (self.has_default() or 'initial' in kwargs)
            defaults = {'choices': self.get_choices(include_blank=include_blank)}
        else:
            form_class = forms.NullBooleanField if self.null else forms.BooleanField
            # In HTML checkboxes, 'required' means "must be checked" which is
            # different from the choices case ("must select some value").
            # required=False allows unchecked checkboxes.
            defaults = {'form_class': form_class, 'required': False}
        return super().formfield(**{**defaults, **kwargs})


class AllCapsBooleanField(BooleanField):

    LDAP_TRUE: str = 'TRUE'
    LDAP_FALSE: str = 'FALSE'


class CharField(Field):

    description: str = _("String (up to %(max_length)s)")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.validators.append(validators.MaxLengthValidator(self.max_length))

    def to_python(self, value: Optional[str]) -> Optional[str]:
        if isinstance(value, str) or value is None:
            return value
        return str(value)

    def from_db_value(self, value: List[str]) -> str:
        value = super().from_db_value(value)
        if value == []:
            return None
        return value[0]

    def formfield(
        self,
        form_class: Type[forms.Field] = None,
        choices_form_class: Type[forms.Field] = None,
        **kwargs
    ) -> forms.Field:
        # Passing max_length to forms.CharField means that the value's length
        # will be validated twice. This is considered acceptable since we want
        # the value in the form field (to pass into widget for example).
        defaults = {'max_length': self.max_length}
        if self.null:
            defaults['empty_value'] = None
        defaults.update(kwargs)
        return super().formfield(**defaults)


class DateField(Field):

    empty_strings_allowed: bool = False
    default_error_messages: Dict[str, str] = {
        'invalid': _("'%(value)s' value has an invalid date format. It must be "
                     "in YYYY-MM-DD format."),
        'invalid_date': _("'%(value)s' value has the correct format (YYYY-MM-DD) "
                          "but it is an invalid date."),
    }
    description: str = _("Date (without time)")

    LDAP_DATETIME_FORMAT: str = "%Y%m%d"

    def __init__(
        self,
        verbose_name: str = None,
        name: str = None,
        auto_now: bool = False,
        auto_now_add: bool = False,
        **kwargs
    ):
        self.auto_now, self.auto_now_add = auto_now, auto_now_add
        if auto_now or auto_now_add:
            kwargs['editable'] = False
            kwargs['blank'] = True
        super().__init__(verbose_name, name, **kwargs)

    def check(self, **kwargs) -> List[Union[checks.Error, checks.Warning]]:
        return [
            *super().check(),
            *self._check_fix_default_value(),
        ]

    def _check_fix_default_value(self) -> List[checks.Error]:
        """
        Warn that using an actual date or datetime value is probably wrong;
        it's only evaluated on server startup.
        """
        if not self.has_default():
            return []

        now = timezone.now()
        if not timezone.is_naive(now):
            now = timezone.make_naive(now, timezone.utc)
        value = self.default
        if isinstance(value, datetime.datetime):
            if not timezone.is_naive(value):
                value = timezone.make_naive(value, timezone.utc)
            value = value.date()
        elif isinstance(value, datetime.date):
            # Nothing to do, as dates don't have tz information
            pass
        else:
            # No explicit date / datetime value -- no checks necessary
            return []
        offset = datetime.timedelta(days=1)
        lower = (now - offset).date()
        upper = (now + offset).date()
        if lower <= value <= upper:
            return [
                checks.Warning(
                    'Fixed default value provided.',
                    hint='It seems you set a fixed date / time / datetime '
                         'value as default for this field. This may not be '
                         'what you want. If you want to have the current date '
                         'as default, use `django.utils.timezone.now`',
                    obj=self,
                    id='fields.W161',
                )
            ]

        return []

    def to_python(self, value: Optional[Union[str, datetime.date, datetime.datetime]]) -> Optional[datetime.date]:
        if value is None:
            return value
        if isinstance(value, datetime.datetime):
            if settings.USE_TZ and timezone.is_aware(value):
                # Convert aware datetimes to the default time zone
                # before casting them to dates (#17742).
                default_timezone = timezone.get_default_timezone()
                value = timezone.make_naive(value, default_timezone)
            return value.date()
        if isinstance(value, datetime.date):
            return value

        try:
            parsed = parse_date(value)
            if parsed is not None:
                return parsed
        except ValueError:
            raise exceptions.ValidationError(
                self.error_messages['invalid_date'],
                code='invalid_date',
                params={'value': value},
            )

        raise exceptions.ValidationError(
            self.error_messages['invalid'],
            code='invalid',
            params={'value': value},
        )

    def pre_save(self, model_instance: "Model", add: bool) -> Optional[datetime.date]:
        if self.auto_now or (self.auto_now_add and add):
            value = datetime.date.today()
            setattr(model_instance, self.attname, value)
            return value
        return super().pre_save(model_instance, add)

    def contribute_to_class(self, cls, name: str, **kwargs) -> None:
        super().contribute_to_class(cls, name, **kwargs)
        if not self.null:
            setattr(
                cls, 'get_next_by_%s' % self.name,
                partialmethod(cls._get_next_or_previous_by_FIELD, field=self, is_next=True)
            )
            setattr(
                cls, 'get_previous_by_%s' % self.name,
                partialmethod(cls._get_next_or_previous_by_FIELD, field=self, is_next=False)
            )

    def from_db_value(self, value: List[bytes]) -> Optional[datetime.date]:
        value = super().from_db_value(value)
        if not value:
            return None
        value = value[0]
        ts = datetime.datetime.strptime(value, self.LDAP_DATETIME_FORMAT)
        return datetime.date(year=ts.year, month=ts.month, day=ts.day)

    def to_db_value(self, value: Optional[datetime.date]) -> Dict[str, List[bytes]]:
        if value:
            value = value.strftime(self.LDAP_DATETIME_FORMAT)
        return super().to_db_value(value)

    def value_to_string(self, obj: "Model") -> str:
        val = self.value_from_object(obj)
        return '' if val is None else val.isoformat()

    def formfield(
        self,
        form_class: Type[forms.Field] = None,
        choices_form_class: Type[forms.Field] = None,
        **kwargs
    ) -> forms.Field:
        return super().formfield(**{
            'form_class': forms.DateField,
            **kwargs,
        })


class DateTimeField(DateField):

    LDAP_DATETIME_FORMATS: List[str] = [
        "%Y%m%d%H%M%SZ",
        "%Y%m%d%H%M%S+0000"
    ]
    LDAP_DATETIME_FORMAT: str = "%Y%m%d%H%M%S+0000"

    empty_strings_allowed: bool = False
    default_error_messages: Dict[str, str] = {
        'invalid': _("'%(value)s' value has an invalid format. It must be in "
                     "YYYY-MM-DD HH:MM[:ss[.uuuuuu]][TZ] format."),
        'invalid_date': _("'%(value)s' value has the correct format "
                          "(YYYY-MM-DD) but it is an invalid date."),
        'invalid_datetime': _("'%(value)s' value has the correct format "
                              "(YYYY-MM-DD HH:MM[:ss[.uuuuuu]][TZ]) "
                              "but it is an invalid date/time."),
        'invalid_ldap_datetime': _("LDAP datetime '%(value)s' value is not in a supported format"),
    }
    description: str = _("Date (with time)")

    def _check_fix_default_value(self) -> List[checks.Warning]:
        """
        Warn that using an actual date or datetime value is probably wrong;
        it's only evaluated on server startup.
        """
        if not self.has_default():
            return []

        now = timezone.now()
        if not timezone.is_naive(now):
            now = timezone.make_naive(now, timezone.utc)
        value = self.default
        if isinstance(value, datetime.datetime):
            second_offset = datetime.timedelta(seconds=10)
            lower = now - second_offset
            upper = now + second_offset
            if timezone.is_aware(value):
                value = timezone.make_naive(value, timezone.utc)
        elif isinstance(value, datetime.date):
            second_offset = datetime.timedelta(seconds=10)
            lower = now - second_offset
            lower = datetime.datetime(lower.year, lower.month, lower.day)
            upper = now + second_offset
            upper = datetime.datetime(upper.year, upper.month, upper.day)
            value = datetime.datetime(value.year, value.month, value.day)
        else:
            # No explicit date / datetime value -- no checks necessary
            return []
        if lower <= value <= upper:
            return [
                checks.Warning(
                    'Fixed default value provided.',
                    hint='It seems you set a fixed date / time / datetime '
                         'value as default for this field. This may not be '
                         'what you want. If you want to have the current date '
                         'as default, use `django.utils.timezone.now`',
                    obj=self,
                    id='fields.W161',
                )
            ]

        return []

    def to_python(self, value: Optional[Union[str, datetime.datetime, datetime.date]]) -> Optional[datetime.datetime]:
        if value is None:
            return value
        if isinstance(value, datetime.datetime):
            return value
        if isinstance(value, datetime.date):
            value = datetime.datetime(value.year, value.month, value.day)
            if settings.USE_TZ:
                # For backwards compatibility, interpret naive datetimes in
                # local time. This won't work during DST change, but we can't
                # do much about it, so we let the exceptions percolate up the
                # call stack.
                warnings.warn("DateTimeField %s.%s received a naive datetime "
                              "(%s) while time zone support is active." %
                              (self.model.__name__, self.name, value),
                              RuntimeWarning)
                default_timezone = timezone.get_default_timezone()
                value = timezone.make_aware(value, default_timezone)
            return value

        try:
            parsed = parse_datetime(value)
            if parsed is not None:
                return parsed
        except ValueError:
            raise exceptions.ValidationError(
                self.error_messages['invalid_datetime'],
                code='invalid_datetime',
                params={'value': value},
            )

        try:
            parsed = parse_date(value)
            if parsed is not None:
                return datetime.datetime(parsed.year, parsed.month, parsed.day)
        except ValueError:
            raise exceptions.ValidationError(
                self.error_messages['invalid_date'],
                code='invalid_date',
                params={'value': value},
            )

        raise exceptions.ValidationError(
            self.error_messages['invalid'],
            code='invalid',
            params={'value': value},
        )

    def from_db_value(self, value: List[bytes]) -> Optional[datetime.datetime]:
        value = Field.from_db_value(self, value)
        if not value:
            return None
        value = value[0]
        for fmt in self.LDAP_DATETIME_FORMATS:
            try:
                value = datetime.datetime.strptime(value, fmt)
            except ValueError:
                pass
            else:
                break
        if not isinstance(value, datetime.datetime):
            raise exceptions.ValidationError(
                self.error_messages['invalid_ldap_datetime'],
                code='invalid_ldap_datetime',
                params={'value': value},
            )
        value = pytz.utc.localize(value)
        return value

    def to_db_value(self, value: Optional[datetime.datetime]) -> Dict[str, List[bytes]]:
        if value:
            utc = pytz.utc
            value = value.astimezone(utc)
            value = value.strftime(self.LDAP_DATETIME_FORMAT)
        return Field.to_db_value(self, value)

    def pre_save(self, model_instance: "Model", add: bool) -> FieldValue:
        if self.auto_now or (self.auto_now_add and add):
            value = timezone.now()
            setattr(model_instance, self.attname, value)
            return value
        return super().pre_save(model_instance, add)

    def formfield(self, **kwargs) -> forms.Field:
        return super().formfield(**{
            'form_class': forms.DateTimeField,
            **kwargs,
        })


class EmailField(CharField):
    default_validators: List[Validator] = [validators.validate_email]
    description: str = _("Email address")

    def __init__(self, *args, **kwargs):
        # max_length=254 to be compliant with RFCs 3696 and 5321
        kwargs.setdefault('max_length', 254)
        super().__init__(*args, **kwargs)

    def formfield(self, **kwargs) -> forms.Field:
        # As with CharField, this will cause email validation to be performed
        # twice.
        return super().formfield(**{
            'form_class': forms.EmailField,
            **kwargs,
        })


class EmailForwardField(CharField):
    default_validators: List[Validator] = [validate_email_forward]
    description: str = _("Email address")


class IntegerField(Field):
    empty_strings_allowed: bool = False
    default_error_messages: Dict[str, str] = {
        'invalid': _("'%(value)s' value must be an integer."),
    }
    description: str = _("Integer")

    def check(self, **kwargs) -> List[Union[checks.Error, checks.Warning]]:
        return [
            *super().check(),
            *self._check_max_length_warning(),
        ]

    def _check_max_length_warning(self) -> List[checks.Warning]:
        if self.max_length is not None:
            return [
                checks.Warning(
                    "'max_length' is ignored when used with IntegerField",
                    hint="Remove 'max_length' from field",
                    obj=self,
                    id='fields.W122',
                )
            ]
        return []

    def from_db_value(self, value: List[bytes]) -> int:
        value = super().from_db_value(value)
        if not value:
            return None
        return self.to_python(value[0])

    def to_db_value(self, value: Optional[int]) -> Dict[str, List[bytes]]:
        if value:
            value = str(value)
        return super().to_db_value(value)

    def to_python(self, value: str) -> int:
        if value is None:
            return value
        try:
            return int(value)
        except (TypeError, ValueError):
            raise exceptions.ValidationError(
                self.error_messages['invalid'],
                code='invalid',
                params={'value': value},
            )

    def formfield(self, **kwargs) -> forms.Field:
        return super().formfield(**{
            'form_class': forms.IntegerField,
            **kwargs,
        })


class CharListField(CharField):
    description: str = _("List of strings (each up to %(max_length)s)")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.empty_values += ('[]', )
        self.validators.append(validators.MaxLengthValidator(self.max_length))

    def get_default(self) -> List[str]:
        if self.default is None:
            return []
        return self._get_default()

    def to_python(self, value: Optional[List[str]]) -> List[str]:
        if not value:
            return []
        if isinstance(value, list):
            return value
        return value.splitlines()

    def formfield(self, **kwargs) -> forms.Field:
        # Passing max_length to forms.CharField means that the value's length
        # will be validated twice. This is considered acceptable since we want
        # the value in the form field (to pass into widget for example).
        defaults = {
            'max_length': self.max_length,
            'form_class': ldap_forms.CharListField,
        }
        if self.null:
            defaults['empty_value'] = []
        defaults.update(kwargs)
        return super().formfield(**defaults)


class PasswordField(CharField):

    def hash_password(self, password: str) -> bytes:
        return password.encode('utf-8')

    def to_db_value(self, value: str) -> Dict[str, List[bytes]]:
        hashed_password = self.hash_password(value)
        return super().to_db_value(hashed_password)


class LDAPPasswordField(PasswordField):

    def hash_password(self, password: str) -> bytes:
        salt = os.urandom(8)
        h = hashlib.sha1(password.encode('utf-8'))
        h.update(salt)
        pwhash = "{SSHA}".encode('utf-8') + encode(h.digest() + salt)
        return pwhash


class ADPasswordField(PasswordField):

    def hash_password(self, password: str) -> bytes:
        return "\"{}\"".format(password).encode("utf-16-le")
