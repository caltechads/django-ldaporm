"""
LDAP ORM Form field implementations.

This module provides Django form field classes for LDAP data modeling.
These form fields handle the conversion between form data and LDAP field formats.
"""

from typing import Any, cast

from django import forms
from django.core import validators
from django.core.exceptions import ValidationError
from django.forms.renderers import BaseRenderer
from django.forms.widgets import Textarea, Widget


class CharListWidget(Textarea):
    """
    A :py:class:`~django.forms.widgets.Textarea` subclass for handling lists of
    character strings. This is used as the default widget for the
    :py:class:`~ldaporm.forms.CharListField` field.

    This widget converts between a list of strings and a newline-separated
    text format for display in forms. It handles empty values appropriately
    and provides a user-friendly interface for editing string lists.

    """

    #: Whether this widget should be hidden in forms.
    is_hidden: bool = False

    def render(  # type: ignore[override]
        self,
        name: str,
        value: str | list[str] | None,
        attrs: dict[str, Any] | None = None,
        renderer: BaseRenderer | None = None,  # noqa: ARG002
    ) -> str:
        """
        Render the widget as HTML.

        Args:
            name: The name attribute for the form field.
            value: The current value, which can be a string, list of strings, or None.
            attrs: Additional HTML attributes for the widget.
            renderer: The form renderer to use.

        Returns:
            The rendered HTML string for the widget.

        """
        if value in self.attrs["empty_values"]:
            value = ""
        elif isinstance(value, list):
            value = "\n".join(value)
        return super().render(name, value, attrs)


class CharListField(forms.CharField):
    """
    A form field for handling lists of character strings.  This is the default
    field for the :py:class:`~ldaporm.forms.CharListWidget` widget on
    :py:class:`django.forms.ModelForm`.

    This field extends :py:class:`~django.forms.CharField` to handle lists of
    strings, converting between newline-separated text input and Python lists.
    It validates each line independently and provides appropriate error
    handling.

    """

    #: The widget class to use for this field.
    widget: type[Widget] = CharListWidget
    #: Values that should be considered empty, including the empty list string.
    empty_values: list[Any] = [*list(validators.EMPTY_VALUES), "[]"]  # noqa: RUF012

    def to_python(self, value: str | None) -> list[str]:  # type: ignore[override]
        """
        Convert the input value to a Python list of strings.

        Args:
            value: The input value, which can be a string or None.

        Returns:
            A list of strings. Empty input returns an empty list.

        """
        if value in self.empty_values:
            return []
        res = []
        for v in cast("str", value).splitlines():
            _v = v
            if self.strip:
                _v = v.strip()
            if _v == "":
                continue
            res.append(_v)
        return res

    def run_validators(self, value: list[str]) -> None:
        """
        Validate each line independently.

        This method runs the parent field's validators on each individual
        string in the list, collecting all validation errors.

        Args:
            value: The list of strings to validate.

        Raises:
            ValidationError: If any validation fails, containing all error messages.

        """
        # Use the parent's handling of required fields, etc.
        errors = []
        for v in value:
            try:
                super().run_validators(v)
            except ValidationError as e:  # noqa: PERF203
                errors.extend(e.error_list)
        if errors:
            raise ValidationError(errors)

    def widget_attrs(self, widget: Widget) -> dict[str, Any]:
        """
        Get HTML attributes for the widget.

        Args:
            widget: The widget instance to get attributes for.

        Returns:
            A dictionary of HTML attributes for the widget.

        """
        attrs = super().widget_attrs(widget)
        attrs["empty_values"] = self.empty_values
        return attrs
