####################################
# Define your core app's forms here.
####################################

from typing import TYPE_CHECKING, Any, Final, cast

from crispy_forms.helper import FormHelper
from crispy_forms.layout import ButtonHolder, Field, Fieldset, Layout, Submit
from django import forms
from django.urls import reverse

from ldaporm.models import Model as LdapModel
from sandbox.demo.core.ldap.models import LDAPUser, NSRole

if TYPE_CHECKING:
    from ldaporm.managers import LdapManager


class LDAPPersonForm(forms.ModelForm):
    """
    Form for editing LDAP person attributes and settings.
    """

    is_active = forms.BooleanField(
        label="Is Active?",
        help_text="Whether the user is active",
        required=False,
    )

    class Meta:
        model: type[LdapModel] = LDAPUser
        fields = (
            "uid",
            "is_active",
            "login_shell",
            "home_phone",
            "mobile",
        )
        widgets: Final[dict[str, Any]] = {
            "uid": forms.HiddenInput(),
            "is_active": forms.CheckboxInput(
                attrs={"class": "custom-switch custom-control-input"}
            ),
            "login_shell": forms.Select(choices=LDAPUser.LOGIN_SHELL_CHOICES),
            "home_phone": forms.TelInput(),
            "mobile": forms.TelInput(),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if "is_active" not in self.initial:
            self.initial["is_active"] = self.instance.is_active  # type: ignore[index]
        self.helper = FormHelper()
        self.helper.form_class = "form"
        self.helper.form_method = "post"
        self.helper.form_action = reverse("core:user--update")
        self.helper.layout = Layout(
            Fieldset(
                "",
                Field("login_shell", css_class="mb-2 border-bottom"),
                Field("home_phone", css_class="mb-2 border-bottom"),
                Field("mobile", css_class="mb-2 border-bottom"),
                Field("is_active", css_class="mb-2 border-bottom"),
                ButtonHolder(
                    Submit("submit", "Save", css_class="btn btn-primary"),
                ),
            ),
        )


class ManagedRoleForm(forms.Form):
    """
    Form for managing user roles in the LDAP system.

    This form provides an interface for assigning and removing managed roles
    from users. It dynamically loads available roles from the LDAP system
    and presents them as checkboxes for selection.
    """

    def get_roles(self) -> list[NSRole]:
        """
        Get all the available managed roles.

        Returns:
            A list of all the available managed roles.

        """
        return (
            cast("LdapManager", NSRole.objects)
            .filter(objectclass="nsmanagedroledefinition")
            .all()
        )

    def __init__(self, user, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["uid"] = forms.CharField(
            widget=forms.HiddenInput(), initial=user.uid
        )
        choices = [(cast("str", r.dn).lower(), r.cn.lower()) for r in self.get_roles()]  # type: ignore[attr-defined]
        initial = []
        userroles = [r.lower() for r in user.nsroledn]
        initial = [choice[0] for choice in choices if choice[0] in userroles]
        self.fields["nsroledn"] = forms.MultipleChoiceField(
            choices=choices,
            initial=initial,
            required=False,
            widget=forms.CheckboxSelectMultiple(attrs={"class": "form-control"}),
        )
        self.helper = FormHelper()
        self.helper.form_class = "form"
        self.helper.form_method = "post"
        self.helper.form_action = reverse("core:user--roles--update")
        self.helper.layout = Layout(
            Fieldset(
                "",
                Field("uid"),
                Field("Roles", id="nsroledn"),
            ),
            ButtonHolder(
                Submit("submit", "Update", css_class="btn btn-primary"),
                css_class="d-flex flex-row justify-content-end button-holder",
            ),
        )


class ResetPasswordForm(forms.Form):
    """
    Form for resetting a user's password.
    """

    uid = forms.CharField(widget=forms.HiddenInput())


class VerifyPasswordForm(forms.Form):
    """
    Form for verifying a user's password.
    """

    uid = forms.CharField(widget=forms.HiddenInput())
    verify_password_value = forms.CharField(widget=forms.PasswordInput())

    def __init__(self, user: LDAPUser, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["uid"] = forms.CharField(
            widget=forms.HiddenInput(), initial=user.uid
        )
        self.fields["verify_password_value"] = forms.CharField(
            widget=forms.PasswordInput(), label="Password"
        )
        self.helper = FormHelper()
        self.helper.form_id = "id_verify_password_form"
        self.helper.form_class = "form"
        self.helper.form_method = "post"
        self.helper.form_action = reverse("core:user--verify-password")
        self.helper.attrs = {"onsubmit": "verify_password(); return false;"}
        self.helper.layout = Layout(
            Fieldset(
                "",
                Field("uid"),
                Field("verify_password_value"),
            ),
            ButtonHolder(
                Submit("submit", "Verify", css_class="btn btn-primary"),
            ),
        )
