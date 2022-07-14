from typing import Any, Dict, List, Optional, Type, Union, cast
from django import forms
from django.forms.widgets import Textarea, Widget
from django.forms.renderers import BaseRenderer
from django.core.exceptions import ValidationError
from django.core import validators


class CharListWidget(Textarea):

    is_hidden: bool = False

    def render(
        self,
        name: str,
        value: Optional[Union[str, List[str]]],
        attrs: Dict[str, Any] = None,
        renderer: BaseRenderer = None
    ):
        if value in self.attrs['empty_values']:
            value = ""
        elif isinstance(value, list):
            value = "\n".join(value)
        return super().render(name, value, attrs)


class CharListField(forms.CharField):

    widget: Type[Widget] = CharListWidget
    empty_values: List[Any] = list(validators.EMPTY_VALUES) + ['[]']

    def to_python(self, value: Optional[str]) -> List[str]:  # type: ignore
        if value in self.empty_values:
            return []
        res = []
        for v in cast(str, value).splitlines():
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
