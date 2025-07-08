from typing import TYPE_CHECKING, Any, cast

from braces.views import (
    FormInvalidMessageMixin,
    FormValidMessageMixin,
    JSONResponseMixin,
)
from django.forms import Form
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import FormView, UpdateView, View
from wildewidgets import (
    BasicHeader,
    Block,
    BreadcrumbBlock,
    CardWidget,
    Datagrid,
    Navbar,
    NavbarMixin,
    WidgetListLayout,
    WidgetStream,
)

from demo.logging import logger

from .forms import LDAPPersonForm, ResetPasswordForm
from .ldap.models import LDAPGroup, LDAPUser
from .password.changer import PasswordChanger
from .wildewidgets import (
    BaseBreadcrumbs,
    GroupTableWidget,
    Sidebar,
    UserConfigurationWidget,
    UserDataDetailWidget,
    UserRoleWidget,
    UserTableWidget,
    UserVerifyPasswordWidget,
    WildewidgetsMixin,
)

if TYPE_CHECKING:
    from ldaporm.managers import LdapManager

# -----------------------------------------------------------------------------
# User views
# -----------------------------------------------------------------------------


class UserDetailView(
    FormValidMessageMixin,
    FormInvalidMessageMixin,
    WildewidgetsMixin,
    NavbarMixin,
    UpdateView,
):
    """
    View for displaying and editing person details from LDAP.

    This view provides a comprehensive interface for viewing and editing
    information about a :py:class:`~demo.core.ldap.models.LDAPUser`.  It
    includes various widgets for displaying different aspects of the user's
    information and configuration.

    Attributes:
        form_class: The form class for editing person details
        slug_field: The field to use for looking up the person
        slug_url_kwarg: The URL kwarg that contains the person ID
        navbar_class: The class to use for the navigation sidebar
        menu_item: The menu item to highlight in the navigation

    """

    form_class: type[Form] = LDAPPersonForm
    slug_field: str = "uid"
    slug_url_kwarg: str = "uid"
    navbar_class: type[Navbar] = Sidebar
    menu_item: str = "Search"

    def get_content(self) -> WidgetListLayout:
        """
        Build the wildewidgets content layout for the person detail view.

        This method creates a layout with various widgets displaying different
        aspects of the person's configuration, including user information,
        password changing and validation and their roles.

        Returns:
            A layout containing all the person detail widgets

        """
        layout = WidgetListLayout(
            self.object.full_name, sidebar_title="Info", sidebar_width=4
        )
        layout.add_widget(UserConfigurationWidget(self.object))
        layout.add_widget(UserRoleWidget(self.object))
        layout.add_widget(UserVerifyPasswordWidget(self.object))
        layout.add_sidebar_bare_widget(UserDataDetailWidget(self.object))
        layout.add_sidebar_form_widget(
            "Reset Password",
            reverse("core:user--reset-password"),
            data={"uid": self.object.uid},
        )
        return layout

    def get_breadcrumbs(self) -> BreadcrumbBlock:
        """
        Get the breadcrumb navigation for this view.

        Returns:
            Breadcrumb navigation showing the path to this person

        """
        breadcrumbs = BaseBreadcrumbs()
        breadcrumbs.add_breadcrumb("Users", reverse("core:users--list"))
        breadcrumbs.add_breadcrumb(self.object.full_name)
        return breadcrumbs

    def get_success_url(self) -> str:
        """
        Get the URL to redirect to after successful form submission.

        Returns:
            URL to redirect to

        """
        return reverse("core:user--detail", uid=self.object.uid)

    def get_form_invalid_message(self) -> str:
        """
        Get the message to display when form submission is invalid.

        Returns:
            Error message for invalid form submission

        """
        return (
            f"There was a problem updating the {self.object.full_name} "
            f"(uid={self.object.uid}). Please see the errors below."
        )

    def get_form_valid_message(self) -> str:
        """
        Get the message to display when form submission is valid.

        Returns:
            str: Success message for valid form submission

        """
        return f'Updated "{self.object.full_name}" (uid={self.object.uid})'

    def form_valid(self, form: Form) -> HttpResponse:
        """
        Handle valid form submission.

        This method saves the form data and adds a delay to allow LDAP
        changes to propagate.

        Args:
            form: The validated form

        Returns:
            Redirect to success URL

        """
        return super().form_valid(form)


class UserListView(WildewidgetsMixin, NavbarMixin, View):
    """
    View for displaying a list of users.

    This view provides a dataTable.js table of all
    :py:class:`~demo.core.ldap.models.LdapUser` objects.

    Attributes:
        navbar_class: The class to use for the navigation sidebar
        menu_item: The menu item to highlight in the navigation

    """

    navbar_class: type[Navbar] = Sidebar
    menu_item: str = "Users"

    def get_content(self) -> WidgetListLayout:
        """
        Get the content for the user list view.
        """
        return WidgetStream(
            [
                BasicHeader("Users", badge_text=len(LDAPUser.objects.count())),
                UserTableWidget(),
            ]
        )

    def get_breadcrumbs(self) -> BreadcrumbBlock:
        """
        Get the breadcrumb navigation for this view.

        Returns:
            Breadcrumb navigation showing the path to this person

        """
        breadcrumbs = BaseBreadcrumbs()
        breadcrumbs.add_breadcrumb("Users")
        return breadcrumbs


class UserResetPasswordView(
    FormInvalidMessageMixin,
    WildewidgetsMixin,
    NavbarMixin,
    FormView,
):
    """
    The view that handles the POST after the user has submitted the form from
    the "Reset Password" button on the user detail page.
    """

    navbar_class: type[Navbar] = Sidebar
    menu_item: str = "Search"
    form_class: type[Form] = ResetPasswordForm
    form_invalid_message: str = "No username provided when resetting password."

    def form_valid(self, form: Form) -> HttpResponse:
        """
        Actually reset the user's password by using the
        :py:class:`demo.core.password.changer.PasswordChanger`
        class, which will reset passwords in CAP, LDAP, and AD.

        Args:
            form: The password change form

        Returns:
            A response with the new password and phonetic spelling of the password.

        """
        self.uid = form.cleaned_data["username"]
        pc = PasswordChanger()
        self.password, self.phonetic_strings = pc.set_random_password(self.uid)
        logger.info("user.password_reset.success", user_uid=self.uid)
        return self.render_to_response(self.get_context_data())

    def form_invalid(self, form: Form) -> HttpResponseRedirect:  # noqa: ARG002
        """
        Something was wrong with our password reset form. Log a warning and
        redirect the user back to the search page.

        Args:
            form: The password reset form

        Returns:
            A redirect to the search page.

        """
        logger.warning("user.password_reset.no_user_provided")
        return redirect(reverse("core:user--list"))

    def get_breadcrumbs(self) -> BreadcrumbBlock:
        """
        Build the breadcrumbs for this view.

        Returns:
            The completed breadcrumbs widget

        """
        user = cast("LdapManager", LDAPUser.objects).get(uid=self.uid)
        breadcrumbs = BaseBreadcrumbs()
        breadcrumbs.add_breadcrumb("User")
        breadcrumbs.add_breadcrumb(
            user.full_name,
            reverse("core:user--detail", uid=self.uid),
        )
        breadcrumbs.add_breadcrumb("Reset Password")
        return breadcrumbs

    def get_content(self) -> WidgetListLayout:
        """
        Supply the wildewidgets content for this view.   ``get_content`` is
        a method that is called by the ``WildewidgetsMixin`` to get the
        content for the view.  This part of the view is responsible for
        creating the widgets that will be displayed on the page after
        the password has been reset.

        It shows the password, the phonetic spelling of the password, and
        some information about the user.

        Returns:
            The set of widgets that will be displayed on the page.

        """
        user = cast("LdapManager", LDAPUser.objects).get(uid=self.uid)
        grid = Datagrid()
        grid.add_item(title="Employee Number", content=user.employee_number)
        grid.add_item(title="Username", content=user.uid)
        grid.add_item(title="E-mail", content=user.mail[0])
        if user.home_phone:
            grid.add_item(title="Phone", content=user.home_phone)
        elif user.mobile:
            grid.add_item(title="Phone", content=f"{user.mobile} [mobile]")
        else:
            grid.add_item(title="Phone", content="No phone number")
        grid.add_item(
            title="Password",
            content=Block(self.password, tag="mark", css_class="font-monospace"),
        )
        phonetics = Block(
            tag="div",
            css_class="list-group",
        )
        for phonetic_string in self.phonetic_strings:
            phonetics.add_block(
                Block(phonetic_string, tag="li", css_class="list-group-item p-2")
            )
        block = Block(
            grid,
            BasicHeader(header_level=3, header_text="Phonetic spelling"),
            phonetics,
        )
        return WidgetStream(
            widgets=[
                BasicHeader(
                    header_text=f"Password Reset for {user.full_name}",
                ),
                CardWidget(widget=block, css_class=CardWidget.css_class + " shadow"),
            ],
            css_class=WidgetStream.css_class + " w-50",
        )


@method_decorator(csrf_exempt, name="dispatch")
class VerifyPasswordAPI(JSONResponseMixin, View):
    """
    Verify the password for a user.  This means try binding each of our
    ldap servers with the provided username and password: CAP, LDAP, and AD.

    If ``settings.TRY_AD`` is False, then we will not try to bind to AD.
    """

    def post(self, request: HttpRequest, *args, **kwargs):
        """
        Handle the POST from the "Verify Password" button on the user detail page.

        Args:
            request: the request object
            *args: the positional arguments used by the view

        Keyword Args:
            **kwargs: the keyword arguments used by the view

        Returns:
            The JSON response with the status of the password verification.

        """
        return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs) -> dict[str, Any]:  # noqa: ARG002
        context: dict[str, Any] = {}
        uid = self.request.POST.get("uid", None)
        password = self.request.POST.get("password", None)
        if password is None or uid is None:
            context["status"] = False
            return context
        pc = PasswordChanger()
        result = pc.verify_password(uid, password)
        context["status"] = result
        return context

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:  # noqa: ARG002
        return self.render_json_response(self.get_context_data())


# -----------------------------------------------------------------------------
# Group views
# -----------------------------------------------------------------------------


class GroupDetailView(
    FormValidMessageMixin,
    FormInvalidMessageMixin,
    WildewidgetsMixin,
    NavbarMixin,
    UpdateView,
):
    """
    View for displaying and editing posix group details from LDAP.

    This view provides a comprehensive interface for viewing and editing
    information about a :py:class:`~demo.core.ldap.models.LDAPGroup` It
    includes various widgets for displaying different aspects of the group's
    information and configuration.

    Attributes:
        form_class: The form class for editing person details
        slug_field: The field to use for looking up the person
        slug_url_kwarg: The URL kwarg that contains the person ID
        navbar_class: The class to use for the navigation sidebar
        menu_item: The menu item to highlight in the navigation

    """

    form_class: type[Form] = LDAPPersonForm
    slug_field: str = "uid"
    slug_url_kwarg: str = "uid"
    navbar_class: type[Navbar] = Sidebar
    menu_item: str = "Search"

    def get_content(self) -> WidgetListLayout:
        """
        Build the wildewidgets content layout for the person detail view.

        This method creates a layout with various widgets displaying different
        aspects of the groups's configuration, including name, description,
        and group membership.

        Returns:
            A layout containing all the person detail widgets

        """
        layout = WidgetListLayout(
            self.object.full_name, sidebar_title="Info", sidebar_width=4
        )
        layout.add_widget(UserConfigurationWidget(self.object))
        layout.add_widget(UserRoleWidget(self.object))
        layout.add_widget(UserVerifyPasswordWidget(self.object))
        layout.add_sidebar_bare_widget(UserDataDetailWidget(self.object))
        layout.add_sidebar_form_widget(
            "Reset Password",
            reverse("core:user--reset-password"),
            data={"uid": self.object.uid},
        )
        return layout

    def get_breadcrumbs(self) -> BreadcrumbBlock:
        """
        Get the breadcrumb navigation for this view.

        Returns:
            Breadcrumb navigation showing the path to this person

        """
        breadcrumbs = BaseBreadcrumbs()
        breadcrumbs.add_breadcrumb("Groups", reverse("core:groups--list"))
        breadcrumbs.add_breadcrumb(self.object.full_name)
        return breadcrumbs

    def get_success_url(self) -> str:
        """
        Get the URL to redirect to after successful form submission.

        Returns:
            URL to redirect to

        """
        return reverse("core:user--detail", uid=self.object.uid)

    def get_form_invalid_message(self) -> str:
        """
        Get the message to display when form submission is invalid.

        Returns:
            Error message for invalid form submission

        """
        return (
            f"There was a problem updating the {self.object.full_name} "
            f"(uid={self.object.uid}). Please see the errors below."
        )

    def get_form_valid_message(self) -> str:
        """
        Get the message to display when form submission is valid.

        Returns:
            str: Success message for valid form submission

        """
        return f'Updated "{self.object.full_name}" (uid={self.object.uid})'

    def form_valid(self, form: Form) -> HttpResponse:
        """
        Handle valid form submission.

        This method saves the form data and adds a delay to allow LDAP
        changes to propagate.

        Args:
            form: The validated form

        Returns:
            Redirect to success URL

        """
        return super().form_valid(form)


class GroupListView(WildewidgetsMixin, NavbarMixin, View):
    """
    View for displaying a list of posix groups.

    This view provides a dataTable.js table of all
    :py:class:`~demo.core.ldap.models.LDAPGroup` objects.

    Attributes:
        navbar_class: The class to use for the navigation sidebar
        menu_item: The menu item to highlight in the navigation

    """

    navbar_class: type[Navbar] = Sidebar
    menu_item: str = "Groups"

    def get_content(self) -> WidgetListLayout:
        """
        Get the content for the user list view.
        """
        return WidgetStream(
            [
                BasicHeader("Groups", badge_text=len(LDAPGroup.objects.count())),
                GroupTableWidget(),
            ]
        )

    def get_breadcrumbs(self) -> BreadcrumbBlock:
        """
        Get the breadcrumb navigation for this view.

        Returns:
            Breadcrumb navigation showing the path to this person

        """
        breadcrumbs = BaseBreadcrumbs()
        breadcrumbs.add_breadcrumb("Groups")
        return breadcrumbs


class GroupRemoveMemberView(WildewidgetsMixin, NavbarMixin, View):
    """
    View for removing a member from a group.
    """

    navbar_class: type[Navbar] = Sidebar
    menu_item: str = "Groups"

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponseRedirect:  # noqa: ARG002
        """
        Remove a member from a group.

        Args:
            request: the request object
            *args: the positional arguments used by the view

        Keyword Args:
            **kwargs: the keyword arguments used by the view

        Returns:
            A redirect to the group detail page.

        """
        try:
            user = LDAPUser.objects.get(uid=kwargs["member_uid"])
        except LDAPUser.DoesNotExist:
            return HttpResponse(status=404)
        group = LDAPGroup.objects.get(uid=kwargs["uid"])
        group.memberUid.remove(user.uid)
        group.save()
        return redirect(reverse("core:group--detail", uid=kwargs["uid"]))
