####################################
# Define your core app's forms here.
####################################

from typing import TYPE_CHECKING, Any, Final, cast

from crispy_bootstrap5.bootstrap5 import FloatingField
from crispy_forms.helper import FormHelper
from crispy_forms.layout import ButtonHolder, Field, Fieldset, Layout, Submit
from django import forms
from django.core.validators import validate_email
from django.urls import reverse

from demo.core.ldap.models import LDAPGroup, LDAPUser, NSRole
from demo.core.ldap.utils import (
    get_next_employee_number,
    get_next_group_gid,
    get_next_user_uid,
)
from ldaporm.models import Model as LdapModel

if TYPE_CHECKING:
    from ldaporm.managers import LdapManager

# -----------------------------------------------------------------------------
# User forms
# -----------------------------------------------------------------------------


class LDAPPersonAddForm(forms.ModelForm):
    """
    Form for adding a new LDAP person.
    """

    class Meta:
        model: type[LdapModel] = LDAPUser
        fields = (
            "uid",
            "full_name",
            "first_name",
            "last_name",
            "employee_type",
            "mail",
            "login_shell",
            "home_phone",
            "mobile",
        )
        widgets: Final[dict[str, Any]] = {
            "employee_type": forms.Select(choices=LDAPUser.EMPLOYEE_TYPE_CHOICES),
            "login_shell": forms.Select(choices=LDAPUser.LOGIN_SHELL_CHOICES),
            "home_phone": forms.TelInput(),
            "mobile": forms.TelInput(),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["mail"].help_text = "Comma-separated list of email addresses"
        self.helper = FormHelper()
        self.helper.form_class = "form-row"
        self.helper.form_method = "post"
        self.helper.form_action = reverse("core:user--add")
        self.helper.layout = Layout(
            Fieldset(
                "",
                FloatingField("uid", wrapper_class="border-bottom"),
                FloatingField("full_name", wrapper_class="border-bottom"),
                FloatingField("first_name", wrapper_class="border-bottom"),
                FloatingField("last_name", wrapper_class="border-bottom"),
                FloatingField("employee_type", wrapper_class="border-bottom"),
                FloatingField("mail", wrapper_class="border-bottom"),
                FloatingField("login_shell", wrapper_class="border-bottom"),
                FloatingField("home_phone", wrapper_class="border-bottom"),
                FloatingField("mobile", wrapper_class="border-bottom"),
                ButtonHolder(
                    Submit("submit", "Save", css_class="btn btn-primary me-3"),
                    css_class="d-flex flex-row justify-content-end button-holder mb-3",
                ),
            ),
        )

    def clean_uid(self) -> str:
        """
        Clean the uid.
        """
        if (
            cast("LdapManager", LDAPUser.objects)
            .filter(uid=self.cleaned_data["uid"])
            .exists()
        ):
            msg = f'User with uid "{self.cleaned_data["uid"]}" already exists'
            raise forms.ValidationError(msg)
        return self.cleaned_data["uid"]

    def clean_mail(self) -> str:
        """
        Clean the mail.
        """
        if self.cleaned_data["mail"]:
            for email in self.cleaned_data["mail"]:
                if not email.strip():
                    continue
                validate_email(email.strip())
        return self.cleaned_data["mail"]

    def clean(self) -> dict[str, Any]:
        """
        Clean the form data.
        """
        data = cast("dict[str, Any]", super().clean())
        official_email = (
            f"{data['first_name'].lower()}.{data['last_name'].lower()}@example.com"
        )
        if "mail" not in data or not data["mail"]:
            data["mail"] = []
        if official_email not in data["mail"]:
            data["mail"] = official_email
        data["uid_number"] = get_next_user_uid()
        data["employee_number"] = get_next_employee_number()
        group = cast("LdapManager", LDAPGroup.objects).get(cn="users")
        data["gid_number"] = group.gid_number
        data["home_directory"] = f"/home/{data['uid']}"
        return data


class LDAPPersonEditForm(forms.ModelForm):
    """
    Form for editing LDAP person attributes and settings.
    """

    class Meta:
        model: type[LdapModel] = LDAPUser
        fields = (
            "uid",
            "employee_type",
            "login_shell",
            "home_phone",
            "mobile",
        )
        widgets: Final[dict[str, Any]] = {
            "uid": forms.HiddenInput(),
            "employee_type": forms.Select(choices=LDAPUser.EMPLOYEE_TYPE_CHOICES),
            "login_shell": forms.Select(choices=LDAPUser.LOGIN_SHELL_CHOICES),
            "home_phone": forms.TelInput(),
            "mobile": forms.TelInput(),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class = "form"
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            Fieldset(
                "",
                Field("uid"),
                Field("employee_type", wrapper_class="p-3 border-bottom"),
                Field("login_shell", wrapper_class="p-3 border-bottom"),
                Field("home_phone", wrapper_class="px-3 pb-3 border-bottom"),
                Field("mobile", wrapper_class="px-3 pb-3 border-bottom"),
                ButtonHolder(
                    Submit("submit", "Save", css_class="btn btn-primary me-3"),
                    css_class="d-flex flex-row justify-content-end button-holder mb-3",
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

    def __init__(self, user: LDAPUser, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["uid"] = forms.CharField(
            widget=forms.HiddenInput(), initial=user.uid
        )
        choices = [(cast("str", r.dn).lower(), r.cn.lower()) for r in self.get_roles()]  # type: ignore[attr-defined]
        initial = []
        userroles = [r.lower() for r in user.nsroledn] if user.nsroledn else []
        initial = (
            [choice[0] for choice in choices if choice[0] in userroles]
            if userroles
            else []
        )
        self.fields["nsroledn"] = forms.MultipleChoiceField(
            choices=choices,
            initial=initial,
            required=False,
            widget=forms.CheckboxSelectMultiple(attrs={"class": "form-control"}),
        )
        self.helper = FormHelper()
        self.helper.form_class = "form"
        self.helper.form_method = "post"
        self.helper.form_group_wrapper_class = "m-3"
        self.helper.form_action = reverse(
            "core:user--roles--update", kwargs={"uid": user.uid}
        )
        self.helper.layout = Layout(
            Fieldset(
                "",
                Field("uid", wrapper_class="p-3"),
                Field("nsroledn", wrapper_class="p-3", id="nsroledn"),
            ),
            ButtonHolder(
                Submit("submit", "Update", css_class="btn btn-primary me-3"),
                css_class="d-flex flex-row justify-content-end button-holder mb-3",
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
        self.helper.form_action = reverse(
            "core:user--verify-password", kwargs={"uid": user.uid}
        )
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


# -----------------------------------------------------------------------------
# Group forms
# -----------------------------------------------------------------------------


class LDAPGroupAddForm(forms.ModelForm):
    """
    Form for adding a new LDAP group.
    """

    class Meta:
        model: type[LdapModel] = LDAPGroup
        fields = (
            "cn",
            "description",
        )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class = "form-horizontal"
        self.helper.form_method = "post"
        self.helper.form_action = reverse("core:group--add")
        self.helper.layout = Layout(
            Fieldset(
                "",
                Field("cn", wrapper_class="p-3 border-bottom"),
                Field("description", wrapper_class="p-3 border-bottom"),
                ButtonHolder(
                    Submit("submit", "Save", css_class="btn btn-primary me-3"),
                    css_class="d-flex flex-row justify-content-end button-holder mb-3",
                ),
            ),
        )

    def clean_cn(self) -> str:
        """
        Clean the cn.
        """
        if (
            cast("LdapManager", LDAPGroup.objects)
            .filter(cn=self.cleaned_data["cn"])
            .exists()
        ):
            msg = f'Group with cn "{self.cleaned_data["cn"]}" already exists'
            raise forms.ValidationError(msg)
        return self.cleaned_data["cn"]

    def clean(self) -> dict[str, Any]:
        """
        Clean the form data.
        """
        data = cast("dict[str, Any]", super().clean())
        data["gid_number"] = get_next_group_gid()
        return data


class LDAPGroupEditForm(forms.ModelForm):
    """
    Form for editing LDAP group attributes and settings.
    """

    class Meta:
        model: type[LdapModel] = LDAPGroup
        fields = (
            "gid_number",
            "description",
        )
        widgets: Final[dict[str, Any]] = {
            "gid_number": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_class = "form"
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            Fieldset(
                "",
                Field("gid_number", wrapper_class="p-3 border-bottom"),
                Field("description", wrapper_class="p-3 border-bottom"),
                ButtonHolder(
                    Submit("submit", "Save", css_class="btn btn-primary me-3"),
                    css_class="d-flex flex-row justify-content-end button-holder mb-3",
                ),
            ),
        )


class LDAPGroupRemoveMemberForm(forms.Form):
    """
    Form for adding a member to a group.
    """

    member_uid = forms.CharField(widget=forms.HiddenInput())

    def __init__(self, group: LDAPGroup, uid: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["member_uid"] = forms.CharField(
            widget=forms.HiddenInput(),
            initial=uid,
        )

        self.helper = FormHelper()
        self.helper.form_class = "form"
        self.helper.form_method = "post"
        self.helper.form_action = reverse(
            "core:group--user--remove", kwargs={"gid": group.gid_number}
        )
        self.helper.layout = Layout(
            Fieldset(
                "",
                Field("member_uid"),
                ButtonHolder(
                    Submit("submit", "Remove", css_class="btn btn-danger me-3"),
                    css_class="d-flex flex-row justify-content-end button-holder mb-3",
                ),
            )
        )


class LDAPGroupAddMemberForm(forms.Form):
    """
    Form for adding a member to a group.
    """

    member_uid = forms.CharField(widget=forms.HiddenInput())

    def __init__(self, group: LDAPGroup, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.group = group
        member_uids: list[str] = group.member_uids or []  # type: ignore[assignment]
        choices = [
            (u.uid, u.full_name)
            for u in cast("LdapManager", LDAPUser.objects).exclude(uid__in=member_uids)
        ]
        self.fields["member_uid"] = forms.CharField(
            widget=forms.Select(choices=choices),
            label="Member Name",
        )
        self.helper = FormHelper()
        self.helper.form_id = "id_add_member_form"
        self.helper.form_class = "form"
        self.helper.form_method = "post"
        self.helper.form_action = reverse(
            "core:group--user--add", kwargs={"gid": group.gid_number}
        )
        self.helper.layout = Layout(
            Fieldset(
                "",
                Field("member_uid"),
                ButtonHolder(
                    Submit("submit", "Add", css_class="btn btn-primary me-3"),
                    css_class="d-flex flex-row justify-content-end button-holder mb-3",
                ),
            ),
        )

        def clean_member_uid(self) -> str:
            """
            Clean the member uid.

            Raises:
                forms.ValidationError: If the user does not exist or is already a
                    member of the group.

            """
            if (
                not cast("LdapManager", LDAPUser.objects)
                .filter(uid=self.cleaned_data["member_uid"])
                .exists()
            ):
                msg = "User does not exist"
                raise forms.ValidationError(msg)
            if not self.group.member_uids:
                self.group.member_uids = []
            if self.cleaned_data["member_uid"] in self.group.member_uids:
                msg = f'User is already a member of group "{self.group.cn}"'
                raise forms.ValidationError(msg)
            return self.cleaned_data["member_uid"]
