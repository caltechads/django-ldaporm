from base64 import b64encode as encode
import collections.abc
import datetime
from functools import partialmethod, total_ordering
import hashlib
import operator
import os
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
from django.utils.encoding import smart_text
from django.utils.functional import cached_property
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _

from . import forms as ldap_forms
from .validators import validate_email_forward


@total_ordering
class Field:

    """
    This is enough of a django.db.models.fields.Field implementation to allow us
    to build Django ORM-like models and fool ModelForm into working for us.
    """

    empty_strings_allowed = True
    empty_values = list(validators.EMPTY_VALUES)
    creation_counter = 0

    default_validators = []  # Default set of validators
    default_error_messages = {
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
    hidden = False

    # Generic field type description, usually overridden by subclasses
    def _description(self):
        return _('Field of type: %(field_type)s') % {
            'field_type': self.__class__.__name__
        }
    description = property(_description)

    def __init__(self, verbose_name=None, name=None, primary_key=False,
                 max_length=None, blank=False, null=False,
                 default=NOT_PROVIDED, editable=True, choices=None,
                 help_text='', validators=(), error_messages=None,
                 db_column=None):
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

        self.model = None

        self.creation_counter = Field.creation_counter
        Field.creation_counter += 1

        self._validators = list(validators)  # Store for deconstruction later

        messages = {}
        for c in reversed(self.__class__.__mro__):
            messages.update(getattr(c, 'default_error_messages', {}))
        messages.update(error_messages or {})
        self.error_messages = messages

    def __repr__(self):
        """Display the module, class, and name of the field."""
        path = '%s.%s' % (self.__class__.__module__, self.__class__.__qualname__)
        name = getattr(self, 'name', None)
        if name is not None:
            return '<%s: %s>' % (path, name)
        return '<%s>' % path

    def __lt__(self, other):
        """
        We need to implement this because django.forms.models.fields_from_model
        tries to sort all the fields on a model before interrogating them for
        which form field class they need.
        """
        if isinstance(other, Field):
            return self.creation_counter < other.creation_counter
        raise NotImplementedError

    def __eq__(self, other):
        if isinstance(other, Field):
            return self.creation_counter == other.creation_counter
        return NotImplementedError

    def __hash__(self):
        return hash(self.creation_counter)

    def has_default(self):
        """Return a boolean of whether this field has a default value."""
        return self.default is not NOT_PROVIDED

    def get_default(self):
        """Return the default value for this field."""
        return self._get_default()

    def check(self, **kwargs):
        return [
            *self._check_field_name(),
            *self._check_choices(),
            *self._check_null_allowed_for_primary_keys(),
            *self._check_validators(),
        ]

    def _check_field_name(self):
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
        elif LOOKUP_SEP in self.name:
            return [
                checks.Error(
                    'Field names must not contain "%s".' % (LOOKUP_SEP,),
                    obj=self,
                    id='fields.E002',
                )
            ]
        elif self.name == 'pk':
            return [
                checks.Error(
                    "'pk' is a reserved word that cannot be used as a field name.",
                    obj=self,
                    id='fields.E003',
                )
            ]
        else:
            return []

    def _check_choices(self):
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

    def _check_null_allowed_for_primary_keys(self):
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
        else:
            return []

    def _check_validators(self):
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
    def ldap_attribute(self):
        return self.db_column or self.name

    @cached_property
    def _get_default(self):
        if self.has_default():
            if callable(self.default):
                return self.default
            return lambda: self.default

        if not self.empty_strings_allowed or self.null:
            return return_None
        return str  # return empty string

    def to_python(self, value):
        return value

    @cached_property
    def validators(self):
        return [*self.default_validators, *self._validators]  # NOQA

    def run_validators(self, value):
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

    def validate(self, value, model_instance):
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
                    for optgroup_key, optgroup_value in option_value:
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

    def clean(self, value, model_instance):
        """
        Convert the value's type and run validation. Validation errors
        from to_python() and validate() are propagated. Return the correct
        value if no error is raised.
        """
        value = self.to_python(value)
        self.validate(value, model_instance)
        self.run_validators(value)
        return value

    def set_attributes_from_name(self, name):
        self.name = self.name or name
        if self.verbose_name is None and self.name:
            self.verbose_name = self.name.replace('_', ' ')

    def get_choices(self, include_blank=True, blank_choice=BLANK_CHOICE_DASH, limit_choices_to=None):
        """
        Return choices with a default blank choices included, for use
        as <select> choices for this field.
        """
        if self.choices:
            choices = list(self.choices)
            if include_blank:
                blank_defined = any(choice in ('', None) for choice, _ in self.flatchoices)
                if not blank_defined:
                    choices = blank_choice + choices
            return choices
        rel_model = self.remote_field.model
        limit_choices_to = limit_choices_to or self.get_limit_choices_to()
        choice_func = operator.attrgetter('pk')
        return (blank_choice if include_blank else []) + [
            (choice_func(x), smart_text(x))
            for x in rel_model._default_manager.complex_filter(limit_choices_to)
        ]

    def limit_choices_to(self):
        raise NotImplementedError

    def _get_flatchoices(self):
        """Flattened version of choices tuple."""
        flat = []
        for choice, value in self.choices:
            if isinstance(value, (list, tuple)):
                flat.extend(value)
            else:
                flat.append((choice, value))
        return flat
    flatchoices = property(_get_flatchoices)

    def formfield(self, form_class=None, choices_form_class=None, **kwargs):
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

    def value_from_object(self, obj):
        return getattr(obj, self.name)

    def from_db_value(self, value):
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

    def to_db_value(self, value):
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

    def value_to_string(self, obj):
        return str(self.value_from_object(obj))

    def save_form_data(self, obj, value):
        """
        This is what django.forms.models.ModelForm calls to save data to our
        LdapModel instance.
        """
        setattr(obj, self.name, value)

    def contribute_to_class(self, cls, name):
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

    empty_strings_allowed = False

    default_error_messages = {
        'invalid': _("'%(value)s' value must be either True or False."),
        'invalid_nullable': _("'%(value)s' value must be either True, False, or None."),
    }

    description = _("Boolean (Either True or False)")

    LDAP_TRUE = 'true'
    LDAP_FALSE = 'false'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.blank = True

    def to_python(self, value):
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

    def from_db_value(self, value):
        value = super().from_db_value(value)
        if value == []:
            return None
        if value[0].lower() == self.LDAP_TRUE:
            return True
        if value[0].lower() == self.LDAP_FALSE:
            return False
        if value == [self.LDAP_TRUE]:
            return True
        elif value == [self.LDAP_FALSE]:
            return False
        else:
            raise ValueError('Field "{}" (BooleanField) on model {} got got unexpected data from LDAP: {}'.format(
                self.name,
                self.model._meta.object_name,
                value
            ))

    def to_db_value(self, value):
        if value is not None:
            if value:
                value = self.LDAP_TRUE
            else:
                value = self.LDAP_FALSE
        return super().to_db_value(value)

    def formfield(self, **kwargs):
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

    LDAP_TRUE = 'TRUE'
    LDAP_FALSE = 'FALSE'


class CharField(Field):

    description = _("String (up to %(max_length)s)")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.validators.append(validators.MaxLengthValidator(self.max_length))

    def to_python(self, value):
        if isinstance(value, str) or value is None:
            return value
        return str(value)

    def from_db_value(self, value):
        value = super().from_db_value(value)
        if value == []:
            return None
        return value[0]

    def formfield(self, **kwargs):
        # Passing max_length to forms.CharField means that the value's length
        # will be validated twice. This is considered acceptable since we want
        # the value in the form field (to pass into widget for example).
        defaults = {'max_length': self.max_length}
        if self.null:
            defaults['empty_value'] = None
        defaults.update(kwargs)
        return super().formfield(**defaults)


class DateField(Field):

    empty_strings_allowed = False
    default_error_messages = {
        'invalid': _("'%(value)s' value has an invalid date format. It must be "
                     "in YYYY-MM-DD format."),
        'invalid_date': _("'%(value)s' value has the correct format (YYYY-MM-DD) "
                          "but it is an invalid date."),
    }
    description = _("Date (without time)")

    LDAP_DATETIME_FORMAT = "%Y%m%d"

    def __init__(self, verbose_name=None, name=None, auto_now=False,
                 auto_now_add=False, **kwargs):
        self.auto_now, self.auto_now_add = auto_now, auto_now_add
        if auto_now or auto_now_add:
            kwargs['editable'] = False
            kwargs['blank'] = True
        super().__init__(verbose_name, name, **kwargs)

    def check(self, **kwargs):
        return [
            *super().check(),
            *self._check_fix_default_value(),
        ]

    def _check_fix_default_value(self):
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

    def to_python(self, value):
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

    def pre_save(self, model_instance, add):
        if self.auto_now or (self.auto_now_add and add):
            value = datetime.date.today()
            setattr(model_instance, self.attname, value)
            return value
        else:
            return super().pre_save(model_instance, add)

    def contribute_to_class(self, cls, name, **kwargs):
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

    def from_db_value(self, value):
        value = super().from_db_value(value)
        if value is []:
            return None
        value = value[0]
        ts = datetime.datetime.strptime(value, self.LDAP_DATETIME_FORMAT)
        return datetime.date(year=ts.year, month=ts.month, day=ts.day)

    def to_db_value(self, value):
        if value:
            value = value.strftime(self.LDAP_DATETIME_FORMAT)
        return super().to_db_value(value)

    def value_to_string(self, obj):
        val = self.value_from_object(obj)
        return '' if val is None else val.isoformat()

    def formfield(self, **kwargs):
        return super().formfield(**{
            'form_class': forms.DateField,
            **kwargs,
        })


class DateTimeField(DateField):

    LDAP_DATETIME_FORMATS = [
        "%Y%m%d%H%M%SZ",
        "%Y%m%d%H%M%S+0000"
    ]
    LDAP_DATETIME_FORMAT = "%Y%m%d%H%M%S+0000"

    empty_strings_allowed = False
    default_error_messages = {
        'invalid': _("'%(value)s' value has an invalid format. It must be in "
                     "YYYY-MM-DD HH:MM[:ss[.uuuuuu]][TZ] format."),
        'invalid_date': _("'%(value)s' value has the correct format "
                          "(YYYY-MM-DD) but it is an invalid date."),
        'invalid_datetime': _("'%(value)s' value has the correct format "
                              "(YYYY-MM-DD HH:MM[:ss[.uuuuuu]][TZ]) "
                              "but it is an invalid date/time."),
        'invalid_ldap_datetime': _("LDAP datetime '%(value)s' value is not in a supported format"),
    }
    description = _("Date (with time)")

    def _check_fix_default_value(self):
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

    def to_python(self, value):
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

    def from_db_value(self, value):
        value = Field.from_db_value(self, value)
        if value is []:
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

    def to_db_value(self, value):
        if value:
            utc = pytz.utc
            value = value.astimezone(utc)
            value = value.strftime(self.LDAP_DATETIME_FORMAT)
        return Field.to_db_value(self, value)

    def pre_save(self, model_instance, add):
        if self.auto_now or (self.auto_now_add and add):
            value = timezone.now()
            setattr(model_instance, self.attname, value)
            return value
        else:
            return super().pre_save(model_instance, add)

    def formfield(self, **kwargs):
        return super().formfield(**{
            'form_class': forms.DateTimeField,
            **kwargs,
        })


class EmailField(CharField):
    default_validators = [validators.validate_email]
    description = _("Email address")

    def __init__(self, *args, **kwargs):
        # max_length=254 to be compliant with RFCs 3696 and 5321
        kwargs.setdefault('max_length', 254)
        super().__init__(*args, **kwargs)

    def formfield(self, **kwargs):
        # As with CharField, this will cause email validation to be performed
        # twice.
        return super().formfield(**{
            'form_class': forms.EmailField,
            **kwargs,
        })


class EmailForwardField(CharField):
    default_validators = [validate_email_forward]
    description = _("Email address")

    # def __init__(self, *args, **kwargs):
    #     # max_length=254 to be compliant with RFCs 3696 and 5321
    #     kwargs.setdefault('max_length', 254)
    #     super().__init__(*args, **kwargs)

    # def formfield(self, **kwargs):
    #     # As with CharField, this will cause email validation to be performed
    #     # twice.
    #     return super().formfield(**{
    #         'form_class': forms.CharField,
    #         **kwargs,
    #     })


class IntegerField(Field):
    empty_strings_allowed = False
    default_error_messages = {
        'invalid': _("'%(value)s' value must be an integer."),
    }
    description = _("Integer")

    def check(self, **kwargs):
        return [
            *super().check(),
            *self._check_max_length_warning(),
        ]

    def _check_max_length_warning(self):
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

    def from_db_value(self, value):
        value = super().from_db_value(value)
        if value is []:
            return None
        return self.to_python(value[0])

    def to_db_value(self, value):
        if value:
            value = str(value)
        return super().to_db_value(value)

    def to_python(self, value):
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

    def formfield(self, **kwargs):
        return super().formfield(**{
            'form_class': forms.IntegerField,
            **kwargs,
        })


class CharListField(CharField):
    description = _("List of strings (each up to %(max_length)s)")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.empty_values += ('[]', )
        self.validators.append(validators.MaxLengthValidator(self.max_length))

    def get_default(self):
        if self.default is None:
            return list()
        else:
            self._get_default()

    def from_db_value(self, value):
        return Field.from_db_value(self, value)

    def to_python(self, value):
        if not value:
            return []
        elif isinstance(value, list):
            return value
        return value.splitlines()

    def formfield(self, **kwargs):
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

    def hash_password(self, password):
        return password

    def to_db_value(self, value):
        hashed_password = self.hash_password(value)
        return super().to_db_value(hashed_password)


class LDAPPasswordField(PasswordField):

    def hash_password(self, password):
        salt = os.urandom(8)
        h = hashlib.sha1(password)
        h.update(salt)
        pwhash = "{SSHA}" + encode(h.digest() + salt)
        return pwhash


class ADPasswordField(PasswordField):

    def hash_password(self, password):
        encoded_pass = "\"{}\"".format(password).encode("utf-16-le")
        return encoded_pass
