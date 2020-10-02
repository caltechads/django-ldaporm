from django import forms
from django.forms.widgets import Textarea
from django.core.exceptions import ValidationError
from django.core import validators


class CharListWidget(Textarea):

    is_hidden = False

    def render(self, name, value, attrs=None, renderer=None):
        if value in self.attrs['empty_values']:
            value = ""
        elif isinstance(value, str):
            value = value
        elif isinstance(value, list):
            value = "\n".join(value)
        return super().render(name, value, attrs)


class CharListField(forms.CharField):

    widget = CharListWidget
    empty_values = list(validators.EMPTY_VALUES) + ['[]']

    def to_python(self, value):
        if value in self.empty_values:
            return []
        res = []
        for v in value.splitlines():
            if self.strip:
                v = v.strip()
            if v == "":
                continue
            res.append(v)
        return res

    def run_validators(self, value):
        """
        Validate each line independently.
        """
        # Use the parent's handling of required fields, etc.
        errors = []
        for v in value:
            try:
                super().run_validators(v)
            except ValidationError as e:
                errors.extend(e.error_list)
        if errors:
            raise ValidationError(errors)

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)
        attrs['empty_values'] = self.empty_values
        return attrs
