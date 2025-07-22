"""
LDAP ORM Field implementations.

This module provides Django ORM-like field classes for LDAP data modeling.
Each field type handles the conversion between Python data types and LDAP
attribute formats, providing a familiar interface for Django developers.
"""

import collections.abc
import datetime
import hashlib
import os
import warnings
from base64 import b64encode as encode
from collections.abc import Callable, Sequence
from functools import partialmethod, total_ordering
from typing import (
    TYPE_CHECKING,
    Any,
    cast,
)

import pytz
from django import forms
from django.conf import settings
from django.core import checks, exceptions
from django.core import validators as dj_validators
from django.db.models.constants import LOOKUP_SEP
from django.db.models.fields import (
    BLANK_CHOICE_DASH,
    NOT_PROVIDED,
    return_None,  # type: ignore[attr-defined]
)
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.functional import cached_property
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _

from . import forms as ldap_forms
from .validators import validate_email_forward

if TYPE_CHECKING:
    from .models import Model


#: Type alias for field validators
Validator = Callable[[Any], None]


@total_ordering
class Field:
    """
    Base field class for LDAP ORM models.

    This class provides enough of a Django ORM Field implementation to allow
    building Django ORM-like models and fool ModelForm into working with LDAP data.
    It handles the conversion between Python data types and LDAP attribute formats.

    Args:
        verbose_name: The human-readable name of the field.
        name: The name of the field
        primary_key: If True, this field is the primary key for the model.
        max_length: The maximum length of the field.
        blank: If True, the field is allowed to be blank in forms.
        null: If True, the field is allowed to be empty in the LDAP server.
        default: The default value for the field.
        editable: If False, the field will not be editable in the admin.
        choices: A list of choices for the field.
        help_text: Help text for the field.
        validators: A list of validators for the field.
        error_messages: A dictionary of error messages for the field.
        db_column: The attribute name in the LDAP schema.


    """

    #: Are empty strings allowed to be stored in this field?
    empty_strings_allowed: bool = True
    #: A list of values that should be considered as empty.
    empty_values: list[Any] = list(dj_validators.EMPTY_VALUES)  # noqa: RUF012
    #: Counter for field creation order, used for sorting fields.
    creation_counter: int = 0

    #: Default set of validators for the field.
    default_validators: list[
        Validator
    ] = []  # Default set of validators  # noqa: RUF012
    #: Default error messages for the field.
    default_error_messages: dict[str, str] = {  # type: ignore[assignment]  # noqa: RUF012
        "invalid_choice": _("Value %(value)r is not a valid choice."),  # type: ignore[dict-item]
        "null": _("This field cannot be null."),  # type: ignore[dict-item]
        "blank": _("This field cannot be blank."),  # type: ignore[dict-item]
    }

    # These are here to fool ModelForm into thinking we're a Django ORM Field. We
    # don't actually use them.
    #: Placeholder for Django ORM compatibility.
    many_to_many: Any = None
    #: Placeholder for Django ORM compatibility.
    many_to_one: Any = None
    #: Placeholder for Django ORM compatibility.
    one_to_many: Any = None
    #: Placeholder for Django ORM compatibility.
    one_to_one: Any = None
    #: Placeholder for Django ORM compatibility.
    related_model: Any = None

    #: Whether the field should be hidden in forms.
    hidden: bool = False

    def _description(self) -> str:
        """
        Get a generic description of the field type.

        Returns:
            A string description of the field type.

        """
        return _("Field of type: %(field_type)s") % {
            "field_type": self.__class__.__name__
        }

    #: Property that returns a description of the field type.
    description = property(_description)

    def __init__(  # noqa: PLR0913
        self,
        verbose_name: str | None = None,
        name: str | None = None,
        primary_key: bool = False,
        max_length: int | None = None,
        blank: bool = False,
        null: bool = False,
        default: Any = NOT_PROVIDED,
        editable: bool = True,
        choices: list[Any] | None = None,
        help_text: str = "",
        validators: Sequence[Validator] = (),
        error_messages: dict[str, str] | None = None,
        db_column: str | None = None,
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
        self.choices: list[Any] = choices or []
        self.help_text = help_text
        self.db_column = db_column

        self.model: type[Model] | None = None

        self.creation_counter = Field.creation_counter
        Field.creation_counter += 1

        self._validators = list(validators)  # Store for deconstruction later

        messages: dict[str, str] = {}
        for c in reversed(self.__class__.__mro__):
            messages.update(getattr(c, "default_error_messages", {}))
        messages.update(error_messages or {})
        self.error_messages = messages

    def __repr__(self) -> str:
        """
        Display the module, class, and name of the field.

        Returns:
            A string representation of the field.

        """
        path = f"{self.__class__.__module__}.{self.__class__.__qualname__}"
        name = getattr(self, "name", None)
        if name is not None:
            return f"<{path}: {name}>"
        return f"<{path}>"

    def __lt__(self, other: "Field") -> bool:
        """
        Compare fields by creation counter for sorting.

        This is needed because django.forms.models.fields_from_model tries to sort
        all the fields on a model before interrogating them for which form field
        class they need.

        Args:
            other: The other field to compare to.

        Returns:
            True if this field is less than the other field, False otherwise.

        Raises:
            NotImplementedError: If the other object is not a Field.

        """
        if isinstance(other, Field):
            return self.creation_counter < other.creation_counter
        raise NotImplementedError

    def __eq__(self, other: object) -> bool:
        """
        Check equality based on creation counter.

        Equality is based on the creation_counter of the field. If the other
        object has the same value for creation_counter, it is considered equal.

        Args:
            other: The other object to compare to.

        Returns:
            True if the other object is a Field and has the same creation_counter.

        Raises:
            NotImplementedError: If the other object is not a Field.

        """
        if isinstance(other, Field):
            return self.creation_counter == other.creation_counter
        raise NotImplementedError

    def __hash__(self) -> int:
        """
        Get hash based on creation counter.

        Returns:
            The hash of the field based on its creation counter.

        """
        return hash(self.creation_counter)

    def has_default(self) -> bool:
        """
        Check if this field has a default value.

        Returns:
            True if the field has a default value, False otherwise.

        """
        return self.default is not NOT_PROVIDED

    def get_default(self) -> Any:
        """
        Get the default value for this field.

        Returns:
            The default value for the field.

        """
        return self._get_default()

    def check(self, **_) -> list[checks.Error | checks.Warning]:
        """
        Run field validation checks.

        Returns:
            A list of validation errors and warnings.

        """
        return [
            *self._check_field_name(),
            *self._check_choices(),
            *self._check_null_allowed_for_primary_keys(),
            *self._check_validators(),
        ]

    def _check_field_name(self) -> list[checks.Error]:
        """
        Check if field name is valid.

        Validates that the field name:

        1. Does not end with an underscore
        2. Does not contain "__"
        3. Is not "pk"

        Returns:
            A list of validation errors for the field name.

        """
        if cast("str", self.name).endswith("_"):
            return [
                checks.Error(
                    "Field names must not end with an underscore.",
                    obj=self,
                    id="fields.E001",
                )
            ]
        if LOOKUP_SEP in cast("str", self.name):
            return [
                checks.Error(
                    f'Field names must not contain "{LOOKUP_SEP}".',
                    obj=self,
                    id="fields.E002",
                )
            ]
        if self.name == "pk":
            return [
                checks.Error(
                    "'pk' is a reserved word that cannot be used as a field name.",
                    obj=self,
                    id="fields.E003",
                )
            ]
        return []

    def _check_choices(self) -> list[checks.Error]:
        """
        Check if choices are properly formatted.

        Returns:
            A list of validation errors for the choices.

        """
        if not self.choices:
            return []

        def is_value(value):
            return isinstance(value, str)

        if is_value(self.choices):
            return [
                checks.Error(
                    "'choices' must be an iterable (e.g., a list or tuple).",
                    obj=self,
                    id="fields.E004",
                )
            ]

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
                "'choices' must be an iterable containing (actual value, human "
                "readable name) tuples.",
                obj=self,
                id="fields.E005",
            )
        ]

    def _check_null_allowed_for_primary_keys(self) -> list[checks.Error]:
        """
        Check that primary keys don't allow null values.

        Returns:
            A list of validation errors for primary key null settings.

        """
        if self.primary_key and self.null:
            return [
                checks.Error(
                    "Primary keys must not have null=True.",
                    hint=(
                        "Set null=False on the field, or remove primary_key=True "
                        "argument."
                    ),
                    obj=self,
                    id="fields.E007",
                )
            ]
        return []

    def _check_validators(self) -> list[checks.Error]:
        """
        Check that all validators are callable.

        Returns:
            A list of validation errors for invalid validators.

        """
        errors: list[checks.Error] = []
        for i, validator in enumerate(self.validators):
            if not callable(validator):
                errors.append(
                    checks.Error(
                        "All 'validators' must be callable.",
                        hint=(
                            f"validators[{i}] ({validator!r}) isn't a function or "
                            "instance of a validator class."
                        ),
                        obj=self,
                        id="fields.E008",
                    )
                )
        return errors

    @property
    def ldap_attribute(self) -> str:
        """
        Get the LDAP attribute name for this field.

        Returns:
            The LDAP attribute name (db_column if set, otherwise field name).

        """
        return cast("str", self.db_column or self.name)

    @cached_property
    def _get_default(self) -> Callable[[], Any]:
        """
        Get a callable that returns the default value.

        Returns:
            A callable that returns the default value when called.

        """
        if self.has_default():
            if callable(self.default):
                return self.default
            return lambda: self.default

        if not self.empty_strings_allowed or self.null:
            return return_None
        return str  # return empty string

    def to_python(self, value: Any) -> Any:
        """
        Convert the value to Python format.

        Args:
            value: The value to convert.

        Returns:
            The converted value.

        """
        return value

    @cached_property
    def validators(self) -> list[Validator]:
        """
        Get all validators for this field.

        Returns:
            A list of all validators (default + custom).

        """
        return [*self.default_validators, *self._validators]

    def run_validators(self, value: Any) -> None:
        """
        Run all validators on the given value.

        Args:
            value: The value to validate.

        Raises:
            ValidationError: If any validator fails.

        """
        if value in self.empty_values:
            return

        errors = []
        for v in self.validators:
            try:
                v(value)
            except exceptions.ValidationError as e:  # noqa: PERF203
                if hasattr(e, "code") and e.code in self.error_messages:
                    e.message = self.error_messages[e.code]
                errors.extend(e.error_list)

        if errors:
            raise exceptions.ValidationError(errors)

    def validate(self, value: Any, model_instance: "Model") -> None:  # noqa: ARG002
        """
        Validate the value and raise ValidationError if necessary.

        Subclasses should override this to provide validation logic.

        Args:
            value: The value to validate.
            model_instance: The model instance being validated.

        Raises:
            ValidationError: If validation fails.

        """
        if not self.editable:
            # Skip validation for non-editable fields.
            return

        if self.choices and value not in self.empty_values:
            for option_key, option_value in self.choices:
                if isinstance(option_value, (list, tuple)):
                    # This is an optgroup, so look inside the group for
                    # options.
                    for optgroup_key, _ in option_value:
                        if value == optgroup_key:
                            return
                elif value == option_key:
                    return
            raise exceptions.ValidationError(
                self.error_messages["invalid_choice"],
                code="invalid_choice",
                params={"value": value},
            )

        if value is None and not self.null:
            raise exceptions.ValidationError(self.error_messages["null"], code="null")

        if not self.blank and value in self.empty_values:
            raise exceptions.ValidationError(self.error_messages["blank"], code="blank")

    def pre_save(self, model_instance: "Model", add: bool) -> Any:  # noqa: ARG002
        """
        Get the field's value just before saving.

        Args:
            model_instance: The model instance being saved.
            add: Whether this is a new instance being added.

        Returns:
            The field's value before saving.

        """
        return getattr(model_instance, self.attname)

    def clean(self, value: Any, model_instance: "Model") -> Any:
        """
        Convert the value's type and run validation.

        Validation errors from to_python() and validate() are propagated.
        Return the correct value if no error is raised.

        Args:
            value: The value to clean.
            model_instance: The model instance being cleaned.

        Returns:
            The cleaned value.

        Raises:
            ValidationError: If validation fails.

        """
        value = self.to_python(value)
        self.validate(value, model_instance)
        self.run_validators(value)
        return value

    def set_attributes_from_name(self, name: str) -> None:
        """
        Set field attributes from the field name.

        Args:
            name: The name of the field.

        """
        self.name = self.name or name
        self.attname = self.name
        if self.verbose_name is None and self.name:
            self.verbose_name = self.name.replace("_", " ")

    def get_choices(
        self,
        include_blank: bool = True,
        blank_choice: list[tuple[str, str]] | None = None,
        limit_choices_to: Any = None,  # noqa: ARG002
    ):
        """
        Get choices with a default blank choice included.

        Args:
            include_blank: Whether to include a blank choice.
            blank_choice: The blank choice to include.
            limit_choices_to: Unused parameter for compatibility.

        Returns:
            A list of choices for use in select widgets.

        """
        if not blank_choice:
            blank_choice = BLANK_CHOICE_DASH
        if self.choices:
            choices = list(self.choices)
            if include_blank:
                blank_defined = any(
                    choice in ("", None) for choice, _ in self.flatchoices
                )
                if not blank_defined:
                    choices = blank_choice + choices  # type: ignore[operator]
            return choices
        return blank_choice

    def limit_choices_to(self):
        """
        Limit choices to a subset.

        Raises:
            NotImplementedError: This method is not implemented.

        """
        raise NotImplementedError

    def _get_flatchoices(self) -> list[tuple[str, str]]:
        """
        Get a flattened version of choices tuple.

        Returns:
            A flattened list of (value, display) tuples.

        """
        flat: list[tuple[str, str]] = []
        for choice, value in self.choices:
            if isinstance(value, (list, tuple)):
                flat.extend(value)
            else:
                flat.append((choice, value))
        return flat

    #: Property that returns flattened choices.
    flatchoices = property(_get_flatchoices)

    def formfield(
        self,
        form_class: type[forms.Field] | None = None,
        choices_form_class: type[forms.Field] | None = None,
        **kwargs,
    ) -> forms.Field:
        """
        Return a Django form field instance for this field.

        Args:
            form_class: The form field class to use.
            choices_form_class: The form field class to use for choices.
            **kwargs: Additional keyword arguments for the form field.

        Returns:
            A Django form field instance.

        """
        defaults: dict[str, Any] = {
            "required": not self.blank,
            "label": capfirst(self.verbose_name),
            "help_text": self.help_text,
        }
        if self.has_default():
            if callable(self.default):
                defaults["initial"] = self.default
                defaults["show_hidden_initial"] = True
            else:
                defaults["initial"] = self.get_default()
        if self.choices:
            # Fields with choices get special treatment.
            include_blank = self.blank or not (
                self.has_default() or "initial" in kwargs
            )
            defaults["choices"] = self.get_choices(include_blank=include_blank)
            defaults["coerce"] = self.to_python
            if self.null:
                defaults["empty_value"] = None
            form_class = (
                choices_form_class
                if choices_form_class is not None
                else forms.TypedChoiceField
            )
            # Many of the subclass-specific formfield arguments (min_value,
            # max_value) don't apply for choice fields, so be sure to only pass
            # the values that TypedChoiceField will understand.
            for k in list(kwargs):
                if k not in (
                    "coerce",
                    "empty_value",
                    "choices",
                    "required",
                    "widget",
                    "label",
                    "initial",
                    "help_text",
                    "error_messages",
                    "show_hidden_initial",
                    "disabled",
                ):
                    del kwargs[k]
        defaults.update(kwargs)
        if form_class is None:
            form_class = forms.CharField
        return form_class(**defaults)

    def value_from_object(self, obj: "Model") -> Any:
        """
        Get the field's value from a model object.

        Args:
            obj: The model object.

        Returns:
            The field's value from the object.

        """
        return getattr(obj, cast("str", self.name))

    def from_db_value(self, value: list[bytes]) -> list[str] | None:
        """
        Convert LDAP data to Python format.

        Take data for one attribute from LDAP and convert it to our internal
        Python format. The value will always be a list of byte strings.

        Subclasses should implement the actual logic for this, but first call
        super().from_db_value(value) to convert the byte strings in the list
        to unicode strings.

        Args:
            value: A list of byte strings from LDAP.

        Returns:
            A list of decoded strings or None if empty.

        """
        return [b.decode("utf-8") for b in value]

    def to_db_value(self, value: Any) -> dict[str, list[bytes]]:
        """
        Convert Python value to LDAP format.

        Subclasses should implement this and do proper casting of the value
        from our internal data type to the appropriate value to stuff into LDAP,
        and then call super().to_db_value(value).

        Args:
            value: The Python value to convert.

        Returns:
            A dictionary mapping LDAP attribute name to list of bytes.

        """
        # Subclasses should implement this and do proper casting of the value
        # from our internal data type to the appropriate value to stuff into LDAP
        # and then call super().to_db_value(value)
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value] if value not in self.empty_values else []
        # LDAP doesn't like unicode strings; it wants bytes.
        cleaned = []
        for item in value:
            _item = item
            if isinstance(item, str):
                _item = item.encode("utf-8")
            cleaned.append(_item)
        return {self.ldap_attribute: cleaned}

    def value_to_string(self, obj: "Model") -> str:
        """
        Convert the field's value to a string.

        Args:
            obj: The model object.

        Returns:
            A string representation of the field's value.

        """
        return str(self.value_from_object(obj))

    def save_form_data(self, obj: "Model", value: Any) -> None:
        """
        Save form data to the model instance.

        This is what django.forms.models.ModelForm calls to save data to our
        LdapModel instance.

        Args:
            obj: The model object to save data to.
            value: The value to save.

        """
        setattr(obj, cast("str", self.name), value)

    def contribute_to_class(self, cls, name: str) -> None:
        """
        Register the field with the model class it belongs to.

        Args:
            cls: The model class to register with.
            name: The name of the field.

        """
        self.set_attributes_from_name(name)
        self.model = cls
        self.check()
        cls._meta.add_field(self)
        if self.choices:
            setattr(
                cls,
                f"get_{self.name}_display",
                partialmethod(cls._get_FIELD_display, field=self),
            )


class BooleanField(Field):
    """
    A boolean field which stores data internally as bool() but stores the
    strings 'true' and 'false' in LDAP.

    This field handles the conversion between Python boolean values and LDAP
    string representations, storing 'true' and 'false' in LDAP while working
    with Python bool values in the application.

    Args:
        *args: Positional arguments passed to the parent class.

    Keyword Args:
        **kwargs: Keyword arguments passed to the parent class.

    """

    #: Boolean fields don't allow empty strings.
    empty_strings_allowed: bool = False

    #: Error messages for boolean validation.
    default_error_messages: dict[str, str] = {  # type: ignore[assignment]  # noqa: RUF012
        "invalid": _("'%(value)s' value must be either True or False."),  # type: ignore[dict-item]
        "invalid_nullable": _("'%(value)s' value must be either True, False, or None."),  # type: ignore[dict-item]
    }

    #: Human-readable description of the field type.
    description: str = _("Boolean (Either True or False)")  # type: ignore[assignment]

    #: The string value used to represent True in LDAP.
    LDAP_TRUE: str = "true"
    #: The string value used to represent False in LDAP.
    LDAP_FALSE: str = "false"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def to_python(self, value: None | bool | str) -> bool | None:
        """
        Convert the value to a Python boolean.

        Args:
            value: The value to convert. Can be None, bool, or string.

        Returns:
            The converted boolean value or None if null is allowed.

        Raises:
            ValidationError: If the value cannot be converted to a boolean.

        """
        if self.null and value in self.empty_values:
            return None
        if value in (True, False):
            # if value is 1 or 0 than it's equal to True or False, but we want
            # to return a true bool for semantic reasons.
            return bool(value)
        if value in ("t", "True", "1"):
            return True
        if value in ("f", "False", "0"):
            return False
        raise exceptions.ValidationError(
            self.error_messages["invalid_nullable" if self.null else "invalid"],
            code="invalid",
            params={"value": value},
        )

    def from_db_value(self, value: list[bytes]) -> bool | None:  # type: ignore[override]
        """
        Convert LDAP data to Python boolean.

        Args:
            value: A list of byte strings from LDAP.

        Returns:
            The boolean value or None if empty.

        Raises:
            ValueError: If the LDAP data contains unexpected values.

        """
        db_value = cast("list[str]", super().from_db_value(value))
        if db_value == []:
            return None
        if db_value[0].lower() == self.LDAP_TRUE:
            return True
        if db_value[0].lower() == self.LDAP_FALSE:
            return False
        if db_value == [self.LDAP_TRUE]:
            return True
        if db_value == [self.LDAP_FALSE]:
            return False
        msg = (
            f'Field "{self.name}" (BooleanField) on model '
            f"{self.model._meta.object_name}"  # type: ignore[union-attr]
            f" got got unexpected data from LDAP: {db_value}"
        )
        raise ValueError(msg)

    def to_db_value(self, value: bool | None) -> dict[str, list[bytes]]:
        """
        Convert Python boolean to LDAP format.

        Args:
            value: The boolean value to convert.

        Returns:
            A dictionary mapping LDAP attribute name to list of bytes.

        """
        db_value: str | None = None
        if value is not None:
            db_value = self.LDAP_TRUE if value else self.LDAP_FALSE
        return super().to_db_value(db_value)

    def formfield(
        self,
        form_class: type[forms.Field] | None = None,
        choices_form_class: type[forms.Field] | None = None,  # noqa: ARG002
        **kwargs,
    ) -> forms.Field:
        """
        Return a Django form field for this boolean field.

        Args:
            form_class: The form field class to use.
            choices_form_class: Unused parameter for compatibility.
            **kwargs: Additional keyword arguments for the form field.

        Returns:
            A Django form field instance.

        """
        if self.choices:
            include_blank = not (self.has_default() or "initial" in kwargs)
            defaults = {"choices": self.get_choices(include_blank=include_blank)}
        else:
            form_class = forms.NullBooleanField if self.null else forms.BooleanField
            # In HTML checkboxes, 'required' means "must be checked" which is
            # different from the choices case ("must select some value").
            # required=False allows unchecked checkboxes.
            defaults = {"form_class": form_class, "required": False}
        return super().formfield(**{**defaults, **kwargs})


class AllCapsBooleanField(BooleanField):
    """
    A boolean field that uses uppercase 'TRUE' and 'FALSE' in LDAP.

    This field is similar to BooleanField but uses uppercase strings
    for LDAP storage, which is common in some LDAP schemas.

    """

    #: The uppercase string value used to represent True in LDAP.
    LDAP_TRUE: str = "TRUE"
    #: The uppercase string value used to represent False in LDAP.
    LDAP_FALSE: str = "FALSE"


class CharField(Field):
    """
    A field for storing character strings.

    This field handles string data with optional maximum length validation.
    It converts between Python strings and LDAP byte strings.

    Keyword Args:
        **kwargs: Keyword arguments passed to the parent class.

    Args:
        *args: Positional arguments passed to the parent class.

    """

    #: Human-readable description of the field type.
    description: str = _("String (up to %(max_length)s)")  # type: ignore[assignment]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.validators.append(dj_validators.MaxLengthValidator(self.max_length))  # type: ignore[attr-defined]

    def to_python(self, value: str | None) -> str | None:
        """
        Convert the value to a Python string.

        Args:
            value: The value to convert.

        Returns:
            The converted string value or None.

        """
        if isinstance(value, str) or value is None:
            return value
        return str(value)

    def from_db_value(self, value: list[bytes]) -> str | None:  # type: ignore[override]
        """
        Convert LDAP data to Python string.

        Args:
            value: A list of byte strings from LDAP.

        Returns:
            The decoded string value or None if empty.

        """
        db_value = cast("list[str]", super().from_db_value(value))
        if db_value == []:
            return None
        return db_value[0]

    def formfield(
        self,
        form_class: type[forms.Field] | None = None,
        choices_form_class: type[forms.Field] | None = None,
        **kwargs,
    ) -> forms.Field:
        """
        Return a Django form field for this character field.

        Args:
            form_class: The form field class to use.
            choices_form_class: The form field class to use for choices.
            **kwargs: Additional keyword arguments for the form field.

        Returns:
            A Django form field instance.

        """
        # Passing max_length to forms.CharField means that the value's length
        # will be validated twice. This is considered acceptable since we want
        # the value in the form field (to pass into widget for example).
        defaults: dict[str, Any] = {
            "form_class": form_class,
            "choices_form_class": choices_form_class,
            "max_length": self.max_length,
        }
        if self.null:
            defaults["empty_value"] = None
        defaults.update(kwargs)
        return super().formfield(**defaults)


class DateField(Field):
    """
    A field for storing dates without time information.

    This field handles date data, converting between Python date objects
    and LDAP date string format (YYYYMMDD).

    Keyword Args:
        verbose_name: The human-readable name of the field.
        name: The name of the field in the LDAP schema.
        auto_now: If True, automatically set to current date on save.
        auto_now_add: If True, automatically set to current date on creation.
        **kwargs: Additional keyword arguments passed to the parent class.

    """

    #: Date fields don't allow empty strings.
    empty_strings_allowed: bool = False
    #: Error messages for date validation.
    default_error_messages: dict[str, str] = {  # type: ignore[assignment]  # noqa: RUF012
        "invalid": _(
            "'%(value)s' value has an invalid date format. It must be in YYYY-MM-DD format."  # type: ignore[dict-item]  # noqa: E501
        ),
        "invalid_date": _(
            "'%(value)s' value has the correct format (YYYY-MM-DD) but it is an invalid date."  # type: ignore[dict-item]  # noqa: E501
        ),
    }
    #: Human-readable description of the field type.
    description: str = _("Date (without time)")  # type: ignore[assignment]

    #: The LDAP date format string.
    LDAP_DATETIME_FORMAT: str = "%Y%m%d"

    def __init__(
        self,
        verbose_name: str | None = None,
        name: str | None = None,
        auto_now: bool = False,
        auto_now_add: bool = False,
        **kwargs: Any,
    ) -> None:
        self.auto_now, self.auto_now_add = auto_now, auto_now_add
        if auto_now or auto_now_add:
            kwargs["editable"] = False
            kwargs["blank"] = True
        super().__init__(verbose_name, name, **kwargs)

    def check(self, **kwargs) -> list[checks.Error | checks.Warning]:  # noqa: ARG002
        """
        Run field validation checks.

        Returns:
            A list of validation errors and warnings.

        """
        return [
            *super().check(),
            *self._check_fix_default_value(),
        ]

    def _check_fix_default_value(self) -> list[checks.Warning]:
        """
        Warn that using an actual date or datetime value is probably wrong.

        This check warns developers that using a fixed date/datetime value as
        default is probably not what they want, as it's only evaluated on
        server startup.

        Returns:
            A list of warnings about fixed default values.

        """
        if not self.has_default():
            return []

        now = timezone.now()
        if not timezone.is_naive(now):
            now = timezone.make_naive(now, datetime.timezone.utc)
        value = self.default
        if isinstance(value, datetime.datetime):
            if not timezone.is_naive(value):
                value = timezone.make_naive(value, datetime.timezone.utc)
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
                    "Fixed default value provided.",
                    hint="It seems you set a fixed date / time / datetime "
                    "value as default for this field. This may not be "
                    "what you want. If you want to have the current date "
                    "as default, use `django.utils.timezone.now`",
                    obj=self,
                    id="fields.W161",
                )
            ]

        return []

    def to_python(
        self, value: str | datetime.date | datetime.datetime | None
    ) -> datetime.date | None:
        """
        Convert the value to a Python date.

        Args:
            value: The value to convert.

        Returns:
            The converted date value or None.

        Raises:
            ValidationError: If the value cannot be converted to a date.

        """
        if value is None:
            return value
        if isinstance(value, datetime.datetime):
            if settings.USE_TZ and timezone.is_aware(value):
                # Convert aware datetimes to the default time zone
                # before casting them to dates (#17742).
                default_timezone = timezone.get_default_timezone()
                value = timezone.make_naive(value, default_timezone)
            return cast("datetime.datetime", value).date()
        if isinstance(value, datetime.date):
            return value

        try:
            parsed = parse_date(value)
            if parsed is not None:
                return parsed
        except ValueError as e:
            raise exceptions.ValidationError(
                self.error_messages["invalid_date"],
                code="invalid_date",
                params={"value": value},
            ) from e

        raise exceptions.ValidationError(
            self.error_messages["invalid"],
            code="invalid",
            params={"value": value},
        )

    def pre_save(self, model_instance: "Model", add: bool) -> datetime.date | None:
        """
        Get the field's value just before saving.

        Args:
            model_instance: The model instance being saved.
            add: Whether this is a new instance being added.

        Returns:
            The field's value before saving.

        """
        if self.auto_now or (self.auto_now_add and add):
            value = datetime.date.today()
            setattr(model_instance, self.attname, value)
            return value
        return super().pre_save(model_instance, add)

    def contribute_to_class(self, cls, name: str, **kwargs) -> None:
        """
        Register the field with the model class and add convenience methods.

        Args:
            cls: The model class to register with.
            name: The name of the field.
            **kwargs: Additional keyword arguments.

        """
        super().contribute_to_class(cls, name, **kwargs)
        if not self.null:
            setattr(
                cls,
                f"get_next_by_{self.name}",
                partialmethod(
                    cls._get_next_or_previous_by_FIELD, field=self, is_next=True
                ),
            )
            setattr(
                cls,
                f"get_previous_by_{self.name}",
                partialmethod(
                    cls._get_next_or_previous_by_FIELD, field=self, is_next=False
                ),
            )

    def from_db_value(self, value: list[bytes]) -> datetime.date | None:  # type: ignore[override]
        """
        Convert LDAP data to Python date.

        Args:
            value: A list of byte strings from LDAP.

        Returns:
            The parsed date value or None if empty.

        """
        db_value = super().from_db_value(value)
        if not db_value:
            return None
        dt = db_value[0]
        ts = datetime.datetime.strptime(dt, self.LDAP_DATETIME_FORMAT)
        return datetime.date(year=ts.year, month=ts.month, day=ts.day)

    def to_db_value(
        self, value: datetime.date | datetime.datetime | None
    ) -> dict[str, list[bytes]]:
        """
        Convert Python date to LDAP format.

        Args:
            value: The date value to convert.

        Returns:
            A dictionary mapping LDAP attribute name to list of bytes.

        """
        db_value = None
        if value:
            db_value = value.strftime(self.LDAP_DATETIME_FORMAT)
        return super().to_db_value(db_value)

    def value_to_string(self, obj: "Model") -> str:
        """
        Convert the field's value to a string.

        Args:
            obj: The model object.

        Returns:
            An ISO format string representation of the date.

        """
        val = self.value_from_object(obj)
        return "" if val is None else val.isoformat()

    def formfield(
        self,
        form_class: type[forms.Field] | None = None,
        choices_form_class: type[forms.Field] | None = None,
        **kwargs,
    ) -> forms.Field:
        """
        Return a Django form field for this date field.

        Args:
            form_class: The form field class to use.
            choices_form_class: The form field class to use for choices.
            **kwargs: Additional keyword arguments for the form field.

        Returns:
            A Django form field instance.

        """
        if not form_class:
            form_class = forms.DateField
        return super().formfield(
            form_class=form_class,
            choices_form_class=choices_form_class,
            **kwargs,
        )


class DateTimeField(DateField):
    """
    A field for storing dates with time information.

    This field handles datetime data, converting between Python datetime objects
    and LDAP datetime string formats. It supports multiple LDAP datetime formats
    and handles timezone conversion.

    """

    #: List of supported LDAP datetime formats.
    LDAP_DATETIME_FORMATS: list[str] = ["%Y%m%d%H%M%SZ", "%Y%m%d%H%M%S+0000"]  # noqa: RUF012
    #: The default LDAP datetime format for output.
    LDAP_DATETIME_FORMAT: str = "%Y%m%d%H%M%S+0000"

    #: DateTime fields don't allow empty strings.
    empty_strings_allowed: bool = False
    #: Error messages for datetime validation.
    default_error_messages: dict[str, str] = {  # type: ignore[assignment]  # noqa: RUF012
        "invalid": _(
            "'%(value)s' value has an invalid format. It must be in "
            "YYYY-MM-DD HH:MM[:ss[.uuuuuu]][TZ] format."
        ),  # type: ignore[dict-item]
        "invalid_date": _(
            "'%(value)s' value has the correct format (YYYY-MM-DD) but it is an "
            "invalid date."
        ),  # type: ignore[dict-item]
        "invalid_datetime": _(
            "'%(value)s' value has the correct format "
            "(YYYY-MM-DD HH:MM[:ss[.uuuuuu]][TZ]) "
            "but it is an invalid date/time."
        ),  # type: ignore[dict-item]
        "invalid_ldap_datetime": _(
            "LDAP datetime '%(value)s' value is not in a supported format"
        ),  # type: ignore[dict-item]
    }
    #: Human-readable description of the field type.
    description: str = _("Date (with time)")  # type: ignore[assignment]

    def _check_fix_default_value(self) -> list[checks.Warning]:
        """
        Warn that using an actual date or datetime value is probably wrong.

        This check warns developers that using a fixed date/datetime value as
        default is probably not what they want, as it's only evaluated on
        server startup.

        Returns:
            A list of warnings about fixed default values.

        """
        if not self.has_default():
            return []

        now = timezone.now()
        if not timezone.is_naive(now):
            now = timezone.make_naive(now, datetime.timezone.utc)
        value = self.default
        if isinstance(value, datetime.datetime):
            second_offset = datetime.timedelta(seconds=10)
            lower = now - second_offset
            upper = now + second_offset
            if timezone.is_aware(value):
                value = timezone.make_naive(value, datetime.timezone.utc)
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
                    "Fixed default value provided.",
                    hint="It seems you set a fixed date / time / datetime "
                    "value as default for this field. This may not be "
                    "what you want. If you want to have the current date "
                    "as default, use `django.utils.timezone.now`",
                    obj=self,
                    id="fields.W161",
                )
            ]

        return []

    def to_python(
        self, value: str | datetime.datetime | datetime.date | None
    ) -> datetime.datetime | None:
        """
        Convert the value to a Python datetime.

        Args:
            value: The value to convert. Can be string, datetime, date, or None.

        Returns:
            The converted datetime value or None.

        Raises:
            ValidationError: If the value cannot be converted to a datetime.

        """
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
                warnings.warn(
                    "DateTimeField {}.{} received a naive datetime ({}) while time zone support is active.".format(  # noqa: E501
                        cast("type[Model]", self.model).__name__, self.name, value
                    ),
                    RuntimeWarning,
                    stacklevel=2,
                )
                default_timezone = timezone.get_default_timezone()
                value = timezone.make_aware(value, default_timezone)
            return value  # type: ignore[return-value]

        try:
            parsed = parse_datetime(value)
            if parsed is not None:
                return parsed
        except ValueError as e:
            raise exceptions.ValidationError(
                self.error_messages["invalid_datetime"],
                code="invalid_datetime",
                params={"value": value},
            ) from e

        try:
            parsed_date = parse_date(value)
            if parsed_date is not None:
                return datetime.datetime(
                    parsed_date.year, parsed_date.month, parsed_date.day
                )
        except ValueError as e:
            raise exceptions.ValidationError(
                self.error_messages["invalid_date"],
                code="invalid_date",
                params={"value": value},
            ) from e

        raise exceptions.ValidationError(
            self.error_messages["invalid"],
            code="invalid",
            params={"value": value},
        )

    def from_db_value(self, value: list[bytes]) -> datetime.datetime | None:  # type: ignore[override]
        """
        Convert LDAP data to Python datetime.

        Args:
            value: A list of byte strings from LDAP.

        Returns:
            The parsed datetime value or None if empty.

        Raises:
            ValidationError: If the LDAP datetime format is not supported.

        """
        db_value = Field.from_db_value(self, value)
        if not db_value:
            return None
        dt_str = db_value[0]
        dt: datetime.datetime | None = None
        for fmt in self.LDAP_DATETIME_FORMATS:
            try:
                dt = datetime.datetime.strptime(dt_str, fmt)
            except ValueError:  # noqa: PERF203
                pass
            else:
                break
        if not isinstance(dt, datetime.datetime):
            raise exceptions.ValidationError(
                self.error_messages["invalid_ldap_datetime"],
                code="invalid_ldap_datetime",
                params={"value": value},
            )
        return pytz.utc.localize(dt)

    def to_db_value(
        self, value: datetime.datetime | datetime.date | None
    ) -> dict[str, list[bytes]]:
        """
        Convert Python datetime to LDAP format.

        Args:
            value: The datetime value to convert.

        Returns:
            A dictionary mapping LDAP attribute name to list of bytes.

        """
        dt_str = None
        if value:
            utc = pytz.utc
            dt_str = (
                cast("datetime.datetime", value)
                .astimezone(utc)
                .strftime(self.LDAP_DATETIME_FORMAT)
            )
        return Field.to_db_value(self, dt_str)

    def pre_save(self, model_instance: "Model", add: bool) -> Any:
        """
        Get the field's value just before saving.

        Args:
            model_instance: The model instance being saved.
            add: Whether this is a new instance being added.

        Returns:
            The field's value before saving.

        """
        if self.auto_now or (self.auto_now_add and add):
            value = timezone.now()
            setattr(model_instance, self.attname, value)
            return value
        return super().pre_save(model_instance, add)

    def formfield(
        self,
        form_class: type[forms.Field] | None = None,
        choices_form_class: type[forms.Field] | None = None,
        **kwargs,
    ) -> forms.Field:
        """
        Return a Django form field for this datetime field.

        Args:
            form_class: The form field class to use.
            choices_form_class: The form field class to use for choices.
            **kwargs: Additional keyword arguments for the form field.

        Returns:
            A Django form field instance.

        """
        if not form_class:
            form_class = forms.DateTimeField
        return super().formfield(
            form_class=form_class,
            choices_form_class=choices_form_class,
            **kwargs,
        )


class EmailField(CharField):
    """
    A field for storing email addresses.

    This field extends CharField to add email validation. It uses Django's
    built-in email validator and sets a default max_length of 254 to be
    compliant with RFCs 3696 and 5321.

    Keyword Args:
        **kwargs: Keyword arguments passed to the parent class.

    Args:
        *args: Positional arguments passed to the parent class.

    """

    #: List containing Django's email validator.
    default_validators: list[Validator] = [dj_validators.validate_email]  # noqa: RUF012
    #: Human-readable description of the field type.
    description: str = _("Email address")  # type: ignore[assignment]

    def __init__(self, *args, **kwargs):
        # max_length=254 to be compliant with RFCs 3696 and 5321
        kwargs.setdefault("max_length", 254)
        super().__init__(*args, **kwargs)

    def formfield(
        self,
        form_class: type[forms.Field] | None = None,
        choices_form_class: type[forms.Field] | None = None,
        **kwargs,
    ) -> forms.Field:
        """
        Return a Django form field for this email field.

        Keyword Args:
            form_class: The form field class to use.
            choices_form_class: The form field class to use for choices.
            **kwargs: Additional keyword arguments for the form field.

        Returns:
            A Django form field instance.

        """
        # As with CharField, this will cause email validation to be performed
        # twice.
        if not form_class:
            form_class = forms.EmailField
        return super().formfield(
            form_class=form_class,
            choices_form_class=choices_form_class,
            **kwargs,
        )


class EmailForwardField(CharField):
    """
    A field for storing email forwarding addresses.

    This field extends CharField to add custom email forwarding validation.
    It uses a custom validator that allows email forwarding syntax.

    """

    #: List containing the email forward validator.
    default_validators: list[Validator] = [validate_email_forward]  # noqa: RUF012
    #: Human-readable description of the field type.
    description: str = _("Email address")  # type: ignore[assignment]


class IntegerField(Field):
    """
    A field for storing integer values.

    This field handles integer data, converting between Python integers
    and LDAP string representations.

    """

    #: Integer fields don't allow empty strings.
    empty_strings_allowed: bool = False
    #: Error messages for integer validation.
    default_error_messages: dict[str, str] = {  # noqa: RUF012
        "invalid": _("'%(value)s' value must be an integer."),  # type: ignore[dict-item]
    }
    #: Human-readable description of the field type.
    description: str = _("Integer")  # type: ignore[assignment]

    def check(self, **kwargs) -> list[checks.Error | checks.Warning]:  # noqa: ARG002
        """
        Run field validation checks.

        Returns:
            A list of validation errors and warnings.

        """
        return [
            *super().check(),
            *self._check_max_length_warning(),
        ]

    def _check_max_length_warning(self) -> list[checks.Warning]:
        """
        Warn that max_length is ignored for IntegerField.

        Returns:
            A list of warnings about max_length usage.

        """
        if self.max_length is not None:
            return [
                checks.Warning(
                    "'max_length' is ignored when used with IntegerField",
                    hint="Remove 'max_length' from field",
                    obj=self,
                    id="fields.W122",
                )
            ]
        return []

    def from_db_value(self, value: list[bytes]) -> int | None:  # type: ignore[override]
        """
        Convert LDAP data to Python integer.

        Args:
            value: A list of byte strings from LDAP.

        Returns:
            The parsed integer value or None if empty.

        """
        db_value = super().from_db_value(value)
        if not db_value:
            return None
        return self.to_python(db_value[0])

    def to_db_value(self, value: int | None) -> dict[str, list[bytes]]:
        """
        Convert Python integer to LDAP format.

        Args:
            value: The integer value to convert.

        Returns:
            A dictionary mapping LDAP attribute name to list of bytes.

        """
        db_value: str | None = str(value) if value else None
        return super().to_db_value(db_value)

    def to_python(self, value: str) -> int:
        """
        Convert the value to a Python integer.

        Args:
            value: The value to convert.

        Returns:
            The converted integer value.

        Raises:
            ValidationError: If the value cannot be converted to an integer.

        """
        if value is None:
            return value
        try:
            return int(value)
        except (TypeError, ValueError) as e:
            raise exceptions.ValidationError(
                self.error_messages["invalid"],
                code="invalid",
                params={"value": value},
            ) from e

    def formfield(
        self,
        form_class: type[forms.Field] | None = None,
        choices_form_class: type[forms.Field] | None = None,
        **kwargs,
    ) -> forms.Field:
        """
        Return a Django form field for this integer field.

        Keyword Args:
            form_class: The form field class to use.
            choices_form_class: The form field class to use for choices.
            **kwargs: Additional keyword arguments for the form field.

        Returns:
            A Django form field instance.

        """
        if not form_class:
            form_class = forms.IntegerField
        return super().formfield(
            form_class=form_class,
            choices_form_class=choices_form_class,
            **kwargs,
        )


class CharListField(CharField):
    """
    A field for storing lists of character strings.

    This field handles lists of strings, converting between Python lists
    and LDAP multi-valued attributes. It treats newlines as delimiters
    when converting from strings to lists.

    Keyword Args:
        **kwargs: Keyword arguments passed to the parent class.

    Args:
        *args: Positional arguments passed to the parent class.

    """

    description: str = _("List of strings (each up to %(max_length)s)")  # type: ignore[assignment]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.empty_values += ("[]",)
        self.validators.append(dj_validators.MaxLengthValidator(self.max_length))  # type: ignore[attr-defined]

    def get_default(self) -> list[str]:
        """
        Get the default value for this field.

        Returns:
            An empty list if no default is set, otherwise the default value.

        """
        if self.default is None:
            return []
        return self._get_default()  # type: ignore[return-value]

    def from_db_value(self, value):
        """
        Convert LDAP data to Python list.

        This is important because we don't want CharField.from_db_value() to
        execute; we only want Field.from_db_value(). CharField.from_db_value()
        turns the list that Field.from_db_value() returns into a string. We
        actually want the list.

        Args:
            value: A list of byte strings from LDAP.

        Returns:
            A list of decoded strings.

        """
        return Field.from_db_value(self, value)

    def to_python(self, value: str | list[str] | None) -> list[str]:  # type: ignore[override]
        """
        Convert the value to a Python list of strings.

        Keyword Args:
            value: The value to convert. Can be string, list, or None.

        Returns:
            A list of strings. If value is a string, it's split on newlines.

        """
        if not value:
            return []
        if isinstance(value, list):
            return value
        return value.splitlines()

    def formfield(
        self,
        form_class: type[forms.Field] | None = None,  # noqa: ARG002
        choices_form_class: type[forms.Field] | None = None,  # noqa: ARG002
        **kwargs,
    ) -> forms.Field:
        """
        Return a Django form field for this character list field.

        Keyword Args:
            form_class: Unused parameter for compatibility.
            choices_form_class: Unused parameter for compatibility.
            **kwargs: Additional keyword arguments for the form field.

        Returns:
            A Django form field instance.

        """
        # Passing max_length to forms.CharField means that the value's length
        # will be validated twice. This is considered acceptable since we want
        # the value in the form field (to pass into widget for example).
        defaults: dict[str, Any] = {
            "max_length": self.max_length,
            "form_class": ldap_forms.CharListField,
        }
        if self.null:
            defaults["empty_value"] = []
        defaults.update(kwargs)
        return super().formfield(**defaults)


class CaseInsensitiveSHA1Field(CharField):
    """
    A readonly field that stores its value as a lowercased SHA1 hash.

    Use this when you want to store a secret value that you will only ever
    compare to a similar hashed value. The field automatically hashes
    values before storing them in LDAP.

    """

    #: Human-readable description of the field type.
    description: str = _("SHA1 Hash")  # type: ignore[assignment]

    @staticmethod
    def hash_value(value: str | None) -> str | None:
        """
        Hash a value using SHA1 with lowercase conversion.

        Args:
            value: The value to hash.

        Returns:
            The SHA1 hash of the lowercase value, or None if value is None.

        """
        if value:
            return hashlib.sha1(value.lower().encode("utf-8")).hexdigest()  # noqa: S324
        return None

    def to_db_value(self, value: str) -> dict[str, list[bytes]]:
        """
        Convert Python string to LDAP format with hashing.

        Args:
            value: The string value to convert and hash.

        Returns:
            A dictionary mapping LDAP attribute name to list of bytes.

        """
        return super().to_db_value(self.hash_value(value))


class PasswordField(CharField):
    """
    Base class for password fields.

    This field provides basic password handling functionality.
    Subclasses should override hash_password() to implement specific
    password hashing algorithms.

    """

    #: Human-readable description of the field type.
    description: str = _("Password")  # type: ignore[assignment]

    def hash_password(self, password: str) -> bytes:
        """
        Hash a password using the default algorithm.

        Args:
            password: The plain text password to hash.

        Returns:
            The hashed password as bytes.

        """
        return password.encode("utf-8")

    def to_db_value(self, value: str) -> dict[str, list[bytes]]:
        """
        Convert Python string to LDAP format with password hashing.

        Args:
            value: The plain text password to hash and store.

        Returns:
            A dictionary mapping LDAP attribute name to list of bytes.

        """
        hashed_password = self.hash_password(value)
        return super().to_db_value(hashed_password)


class LDAPPasswordField(PasswordField):
    """
    A password field that uses LDAP SSHA hashing.

    This field implements the LDAP SSHA (Salted SHA1) password hashing
    algorithm, which is commonly used in LDAP directories.

    """

    #: Human-readable description of the field type.
    description: str = _("LDAP SSHA Password")  # type: ignore[assignment]

    def hash_password(self, password: str) -> bytes:
        """
        Hash a password using LDAP SSHA algorithm.

        Args:
            password: The plain text password to hash.

        Returns:
            The SSHA hashed password as bytes.

        """
        salt = os.urandom(8)
        h = hashlib.sha1(password.encode("utf-8"))  # noqa: S324
        h.update(salt)
        return b"{SSHA}" + encode(h.digest() + salt)


class ADPasswordField(PasswordField):
    """
    A password field for Active Directory.

    This field implements the Active Directory password format,
    which stores passwords as UTF-16LE encoded strings with quotes.

    """

    #: Human-readable description of the field type.
    description: str = _("Active Directory Password")  # type: ignore[assignment]

    def hash_password(self, password: str) -> bytes:
        """
        Hash a password for Active Directory.

        Args:
            password: The plain text password to hash.

        Returns:
            The AD-formatted password as bytes.

        """
        return f'"{password}"'.encode("utf-16-le")


class ActiveDirectoryTimestampField(DateTimeField):
    """
    A field for storing Active Directory timestamp values as datetime objects.

    This field handles Active Directory timestamps, which are stored as 18-digit
    integers representing the number of 100-nanosecond intervals since January 1,
    1601 UTC (also known as Windows NT time format). It converts between these
    timestamps and Python datetime objects.

    The Active Directory timestamp is the number of 100-nanosecond intervals
    (1 nanosecond = one billionth of a second) since Jan 1, 1601 UTC.

    """

    #: Human-readable description of the field type.
    description: str = _("Active Directory DateTime")  # type: ignore[assignment]

    #: Error messages for Active Directory datetime validation.
    default_error_messages: dict[str, str] = {  # type: ignore[assignment]  # noqa: RUF012
        "invalid": _(  # type: ignore[dict-item]
            "'%(value)s' value has an invalid format. It must be an 18-digit integer."
        ),
        "invalid_timestamp": _(  # type: ignore[dict-item]
            "'%(value)s' value is not a valid Active Directory timestamp."
        ),
        "timestamp_out_of_range": _(  # type: ignore[dict-item]
            "'%(value)s' value represents a timestamp outside the supported range."  # type: ignore[dict-item]
        ),
    }

    #: The Active Directory epoch (January 1, 1601 UTC).
    AD_EPOCH: datetime.datetime = datetime.datetime(1601, 1, 1, tzinfo=pytz.UTC)
    #: The number of 100-nanosecond intervals per second.
    INTERVALS_PER_SECOND: int = 10_000_000
    #: The number of 100-nanosecond intervals per day.
    INTERVALS_PER_DAY: int = 864_000_000_000

    def to_python(
        self, value: str | datetime.datetime | datetime.date | None
    ) -> datetime.datetime | None:
        """
        Convert the value to a Python datetime.

        Args:
            value: The value to convert. Can be string, integer, datetime, or None.

        Returns:
            The converted datetime value or None.

        Raises:
            ValidationError: If the value cannot be converted to a datetime.

        """
        if value is None:
            return value
        if isinstance(value, datetime.datetime):
            return value

        # Handle string or integer Active Directory timestamp
        if isinstance(value, (str, int)):
            try:
                # Convert to integer
                timestamp = int(value)

                # Validate it's an 18-digit number
                if len(str(timestamp)) != 18:  # noqa: PLR2004
                    raise exceptions.ValidationError(
                        self.error_messages["invalid"],
                        code="invalid",
                        params={"value": value},
                    )

                # Convert to datetime
                return self._ad_timestamp_to_datetime(timestamp)
            except (ValueError, OverflowError) as e:
                raise exceptions.ValidationError(
                    self.error_messages["invalid_timestamp"],
                    code="invalid_timestamp",
                    params={"value": value},
                ) from e

        # For other types, use parent's to_python method
        return super().to_python(value)

    def from_db_value(self, value: list[bytes]) -> datetime.datetime | None:  # type: ignore[override]
        """
        Convert LDAP data to Python datetime.

        Args:
            value: A list of byte strings from LDAP.

        Returns:
            The parsed datetime value or None if empty.

        Raises:
            ValidationError: If the LDAP timestamp format is invalid.

        """
        db_value = Field.from_db_value(self, value)
        if not db_value:
            return None

        try:
            # Convert the string timestamp to integer
            timestamp = int(db_value[0])
            return self._ad_timestamp_to_datetime(timestamp)
        except (ValueError, OverflowError) as e:
            raise exceptions.ValidationError(
                self.error_messages["invalid_timestamp"],
                code="invalid_timestamp",
                params={"value": db_value[0]},
            ) from e

    def to_db_value(
        self, value: datetime.datetime | datetime.date | None
    ) -> dict[str, list[bytes]]:
        """
        Convert Python datetime to Active Directory timestamp format.

        Args:
            value: The datetime value to convert.

        Returns:
            A dictionary mapping LDAP attribute name to list of bytes.

        """
        if value is None:
            return Field.to_db_value(self, None)

        # Convert datetime to Active Directory timestamp
        timestamp = self._datetime_to_ad_timestamp(value)
        return Field.to_db_value(self, str(timestamp))

    def _ad_timestamp_to_datetime(self, timestamp: int) -> datetime.datetime:
        """
        Convert Active Directory timestamp to Python datetime.

        Args:
            timestamp: The Active Directory timestamp (18-digit integer).

        Returns:
            The corresponding datetime object.

        Raises:
            ValidationError: If the timestamp is out of range.

        """
        try:
            # Convert 100-nanosecond intervals to seconds
            seconds = timestamp / self.INTERVALS_PER_SECOND

            # Add to AD epoch
            dt = self.AD_EPOCH + datetime.timedelta(seconds=seconds)

            # Validate the result is reasonable (not too far in past)
            if dt.year < 1601:  # noqa: PLR2004
                raise exceptions.ValidationError(
                    self.error_messages["timestamp_out_of_range"],
                    code="timestamp_out_of_range",
                    params={"value": timestamp},
                )

        except (OverflowError, OSError) as e:
            raise exceptions.ValidationError(
                self.error_messages["timestamp_out_of_range"],
                code="timestamp_out_of_range",
                params={"value": timestamp},
            ) from e
        else:
            return dt

    def _datetime_to_ad_timestamp(self, dt: datetime.datetime | datetime.date) -> int:
        """
        Convert Python datetime to Active Directory timestamp.

        Args:
            dt: The datetime object to convert.

        Returns:
            The Active Directory timestamp as an 18-digit integer.

        """
        # Ensure we have a datetime object
        if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
            dt = datetime.datetime.combine(dt, datetime.time.min)

        # Ensure timezone awareness
        dt = (
            timezone.make_aware(dt, pytz.UTC)
            if timezone.is_naive(dt)
            else dt.astimezone(pytz.UTC)
        )

        # Calculate the difference from AD epoch
        delta = dt - self.AD_EPOCH

        # Convert to 100-nanosecond intervals
        total_seconds = delta.total_seconds()
        return int(total_seconds * self.INTERVALS_PER_SECOND)


class BinaryField(Field):
    """
    A field for storing binary data.

    This field handles binary data, converting between Python bytes objects
    and LDAP binary attributes. It's commonly used for storing photos,
    certificates, and other binary data in LDAP.

    Keyword Args:
        **kwargs: Keyword arguments passed to the parent class.

    Args:
        *args: Positional arguments passed to the parent class.

    """

    #: Binary fields don't allow empty strings.
    empty_strings_allowed: bool = False
    #: Error messages for binary validation.
    default_error_messages: dict[str, str] = {  # type: ignore[assignment]  # noqa: RUF012
        "invalid": _("'%(value)s' value must be bytes or bytearray."),  # type: ignore[dict-item]
    }
    #: Human-readable description of the field type.
    description: str = _("Binary data")  # type: ignore[assignment]

    def check(self, **kwargs) -> list[checks.Error | checks.Warning]:  # noqa: ARG002
        """
        Run field validation checks.

        Returns:
            A list of validation errors and warnings.

        """
        return [
            *super().check(),
            *self._check_max_length_warning(),
        ]

    def _check_max_length_warning(self) -> list[checks.Warning]:
        """
        Warn that max_length is ignored for BinaryField.

        Returns:
            A list of warnings about max_length usage.

        """
        if self.max_length is not None:
            return [
                checks.Warning(
                    "'max_length' is ignored when used with BinaryField",
                    hint="Remove 'max_length' from field",
                    obj=self,
                    id="fields.W123",
                )
            ]
        return []

    def to_python(self, value: bytes | bytearray | None) -> bytes | None:
        """
        Convert the value to Python bytes.

        Args:
            value: The value to convert. Can be bytes, bytearray, or None.

        Returns:
            The converted bytes value or None.

        Raises:
            ValidationError: If the value cannot be converted to bytes.

        """
        if value is None:
            return value
        if isinstance(value, bytes):
            return value
        if isinstance(value, bytearray):
            return bytes(value)
        raise exceptions.ValidationError(
            self.error_messages["invalid"],
            code="invalid",
            params={"value": value},
        )

    def from_db_value(self, value: list[bytes]) -> bytes | None:  # type: ignore[override]
        """
        Convert LDAP data to Python bytes.

        Args:
            value: A list of byte strings from LDAP.

        Returns:
            The binary data as bytes or None if empty.

        """
        if not value:
            return None
        return value[0]

    def to_db_value(self, value: bytes | bytearray | None) -> dict[str, list[bytes]]:
        """
        Convert Python bytes to LDAP format.

        Args:
            value: The binary data to convert.

        Returns:
            A dictionary mapping LDAP attribute name to list of bytes.

        """
        if value is None:
            return {self.ldap_attribute: []}
        if isinstance(value, bytearray):
            value = bytes(value)
        return {self.ldap_attribute: [value]}

    def formfield(
        self,
        form_class: type[forms.Field] | None = None,
        choices_form_class: type[forms.Field] | None = None,
        **kwargs,
    ) -> forms.Field:
        """
        Return a Django form field for this binary field.

        Args:
            form_class: The form field class to use.
            choices_form_class: The form field class to use for choices.
            **kwargs: Additional keyword arguments for the form field.

        Returns:
            A Django form field instance.

        """
        if not form_class:
            form_class = forms.FileField
        return super().formfield(
            form_class=form_class,
            choices_form_class=choices_form_class,
            **kwargs,
        )
