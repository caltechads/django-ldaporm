from typing import (
    Any,
    ClassVar,
    cast,
)

from django.templatetags.static import static
from django.urls import reverse, reverse_lazy
from wildewidgets import (
    BasicModelTable,
    Block,
    BreadcrumbBlock,
    CardWidget,
    CrispyFormWidget,
    DataTable,
    DataTableFilter,
    LinkedImage,
    Menu,
    MenuItem,
    StandardWidgetMixin,
    TablerVerticalNavbar,
    TemplateWidget,
    WidgetListLayoutHeader,
    WidgetStream,
)

from ldaporm.managers import F, LdapManager
from ldaporm.models import Model as LdapModel
from ldaporm.wildewidgets import LdapModelTableMixin
from sandbox.demo.core.forms import LDAPPersonForm, ManagedRoleForm, VerifyPasswordForm
from sandbox.demo.core.ldap.models import LDAPGroup, LDAPUser, NSRole

# ====================================
# Navigation
# ====================================


class MainMenu(Menu):
    """
    The primary menu that appears in for the helpdesk app.

    It gives access to all the views that normal, non privileged users should be
    allowed to use.
    """

    items: ClassVar[list[MenuItem]] = [
        MenuItem(
            text="Users",
            icon="people-fill",
            url=reverse_lazy("core:user--list"),
        ),
        MenuItem(
            text="Groups",
            icon="collection",
            url=reverse_lazy("core:group-list"),
        ),
    ]


class Sidebar(TablerVerticalNavbar):
    """
    The vertical menu area on the left of the page.  it houses our main menu
    :py:class:`MainMenu`.
    """

    hide_below_viewport: str = "xl"
    branding: Block = Block(
        LinkedImage(
            image_src=static("core/images/logo.png"),
            image_width="150px",
            image_alt="django-ldaporm",
            css_class="d-flex justify-content-center ms-3",
            url="https://github.com/caltechads/django-ldaporm",
        ),
    )
    contents: ClassVar[list[Block]] = [
        MainMenu(),
    ]


class WildewidgetsMixin(StandardWidgetMixin):
    """
    We subclass :py:class:`wildewidgets.StandardWidgetMixin` here so that we can
    define our standard template.
    """

    template_name: str | None = "core/base.html"


class BaseBreadcrumbs(BreadcrumbBlock):
    """
    Base breadcrumb block.

    Attributes:
        title_class: CSS class to apply to the breadcrumb title

    """

    title_class: str = "text-white"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Initialize the breadcrumb block with a default helpdesk link.

        Args:
            *args: Variable length argument list passed to parent
            **kwargs: Arbitrary keyword arguments passed to parent

        """
        super().__init__(*args, **kwargs)
        self.add_breadcrumb("django-ldaporm demo", reverse("core:user--list"))


# ====================================
# Shared
# ====================================


class ValueBlock(Block):
    """
    Block for displaying a user value.
    """

    css_class: str = "d-flex justify-content-between p-3 border-bottom"

    def __init__(self, label: str, value: str, monospace: bool = True) -> None:
        """
        Initialize the user value block.  This is a block that displays a label in bold
        on the left and a value in a grey box on the right.

        Args:
            label: The label to display
            value: The value to display

        Keyword Args:
            monospace: Whether to display the value in monospace

        """
        _label = Block(label, css_class="fw-bold")
        self.add_block(_label)
        _value = Block(
            str(value),
            css_class="p-2 bg-grey-200 text-grey-200-fg border rounded-2",
        )
        if monospace:
            _value.css_class += " font-monospace"
        self.add_block(_value)


# ====================================
# Users
# ====================================


class UserDataDetailWidget(WidgetStream):
    """
    Widget for displaying detailed user information.

    This widget renders a template containing detailed information about a user,
    including their personal data and account settings.

    """

    def __init__(
        self,
        user: LDAPUser,
    ) -> None:
        """
        Initialize the user data detail widget.

        Args:
            user: The LDAPUser object whose details will be displayed

        """
        full_name = Block(
            Block("Name", css_class="fw-bold"),
            Block(user.full_name),  # type: ignore[arg-type]
            css_class=(  # type: ignore[arg-type]
                "d-flex justify-content-between p-3 bg-blue text-blue-fg border-bottom",
            ),
        )
        uid = Block(
            Block("Username", css_class="fw-bold"),
            Block(user.uid),  # type: ignore[arg-type]
            css_class=(  # type: ignore[arg-type]
                "d-flex justify-content-between p-3 bg-grey-200 text-grey-200-fg "
                "border-bottom",
            ),
        )
        email = Block(
            Block("Email", css_class="fw-bold"),
            Block(user.mail[0]),  # type: ignore[arg-type]
            css_class="d-flex justify-content-between p-3 border-bottom",
        )
        employee_number = Block(
            Block("Employee Number", css_class="fw-bold"),
            Block(user.employee_number),  # type: ignore[arg-type]
            css_class="d-flex justify-content-between p-3 border-bottom",
        )

        super().__init__([full_name, uid, email, employee_number])


class UserConfigurationFormWidget(CrispyFormWidget):
    """
    Widget for displaying a user configuration form.
    """

    def __init__(self, user: LDAPUser, **kwargs: Any) -> None:
        if "form" not in kwargs:
            kwargs["form"] = LDAPPersonForm(instance=user)
        super().__init__(**kwargs)


class UserConfigurationWidget(WidgetStream):
    """
    Widget for displaying user configuration information.

    This widget renders a template containing user configuration information,
    including their personal data and account settings.

    """

    title: str = "User Configuration"
    icon: str = "gear-fill"
    name: str = "user-configuration"

    def __init__(self, user: LDAPUser) -> None:
        """
        Initialize the user configuration widget.

        Args:
            user: The LDAPUser object whose configuration will be displayed

        """
        dn = ValueBlock("Distinguished Name", user.dn)
        uid_number = ValueBlock("UID Number", user.uid_number)
        _group = LDAPGroup.objects.get(gid_number=user.gid_number)
        group = ValueBlock("Group", f"{_group.cn} ({_group.gid_number})")
        room_number = ValueBlock("Room Number", user.room_number)
        form = UserConfigurationFormWidget(user)

        super().__init__([dn, uid_number, group, room_number, form])


class UserRoleWidget(TemplateWidget):
    """
    Widget for displaying and managing a user's roles.

    This widget shows the roles assigned to a user and provides a form
    for administrators to modify these roles. It's only visible to users
    with admin rights.

    Attributes:
        template_name: Path to the template used to render the widget
        title: The widget title
        icon: The icon to display with the title

    """

    template_name: str = "core/widgets/user--role.html"
    title: str = "Roles"
    icon: str = "card-checklist"

    def __init__(self, user: LDAPUser) -> None:
        """
        Initialize the user roles widget.

        Args:
            user: The LDAPUser object whose roles will be displayed and managed

        """
        self.user = user

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        """
        Get the context data for rendering the template.

        This method adds the user object, role management form, and role type
        to the context for template rendering.

        Args:
            **kwargs: Additional context variables

        Returns:
            Dictionary containing the context data for the template

        """
        kwargs["user"] = self.user
        kwargs["form"] = ManagedRoleForm(self.user)
        return super().get_context_data(**kwargs)


class UserVerifyPasswordWidget(CardWidget):
    """
    Widget for verifying a user's password.

    This widget provides an interface for administrators to verify a user's
    password. It's only visible to users with admin rights.

    Attributes:
        template_name: Path to the template used to render the widget
        title: The widget title
        icon: The icon to display with the title

    """

    title: str = "Verify Password"
    icon: str = "patch-check"
    tag: str = "div"
    css_class: str = "p-4"
    script: str = """
    function verify_password() {
        const form = document.getElementById('id_verify_password_form');
        const formData = new FormData(form);
        const response = fetch(form.action, {
            method: 'POST',
            body: formData,
        });
        const result = await response.json();
        if (result.success) {
            document.getElementById('verify_password_success').classList.remove('d-none');
            document.getElementById('verify_password_failed').classList.add('d-none');
        } else {
            document.getElementById('verify_password_success').classList.add('d-none');
            document.getElementById('verify_password_failed').classList.remove('d-none');
        }
    }
    """

    def __init__(self, user: LDAPUser) -> None:
        """
        Initialize the password verification widget.

        Args:
            user: The LDAPUser object whose password will be verified

        """
        self.user = user
        form = CrispyFormWidget(form=VerifyPasswordForm(user))
        result = Block(
            Block(
                "Success",
                css_class="badge bg-success d-none",
                css_id="verify_password_success",
            ),
            Block(
                "Failed",
                css_class="badge bg-danger d-none",
                css_id="verify_password_failed",
            ),
        )
        super().__init__(widget=WidgetStream([form, result]))


class UserTableWidget(CardWidget):
    """
    Widget for displaying a user table.
    """

    title: str = "Users"
    icon: str = "people-fill"
    name: str = "user-table"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(UserTable, **kwargs)

    def get_title(self) -> WidgetListLayoutHeader:
        """
        Get the title for the widget.
        """
        return WidgetListLayoutHeader(
            header_text=self.title,
            badge_text=len(cast("LdapManager", LDAPUser.objects).all()),
        )


class UserTable(LdapModelTableMixin, BasicModelTable):
    """
    A data table that displays a list of all non-function applications.

    This table shows applications with their status, enabled state, proxy usage,
    and other details. It includes filtering, sorting, and actions for administrators
    to manage applications.

    Attributes:
        model: The model class that this table displays
        page_length: Number of rows to display per page
        striped: Whether to use alternating row colors
        fields: List of model fields to display as columns
        unsearchable: List of fields that should not be searchable
        hidden: List of fields that should be hidden by default
        verbose_names: Dictionary mapping field names to display names
        alignment: Dictionary mapping field names to alignment values
        form_actions: List of actions that can be performed on selected rows
        form_url: URL to submit form actions to

    """

    model: type[LdapModel] = LDAPUser
    page_length: int = 25
    striped: bool = True
    fields: ClassVar[list[str]] = [
        "uid",
        "full_name",
        "mail",
        "employee_number",
        "is_active",
    ]
    verbose_names: ClassVar[dict[str, str]] = {
        "uid": "Username",
        "full_name": "Name",
        "mail": "Email",
        "employee_number": "Employee Number",
        "is_active": "Active?",
    }
    unsearchable: ClassVar[list[str]] = ["is_active"]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        enabled = DataTableFilter()
        enabled.add_choice("True", "True")
        enabled.add_choice("False", "False")
        self.add_filter("is_active", enabled)

    def get_initial_queryset(self) -> F:
        """
        Get the initial queryset for the table.

        This method excludes applications with sign-on type "function" and
        orders the results by display name.

        Returns:
            :py:class:`ldaporm.managers.F` object containing the initial
            queryset

        """
        return cast("LdapManager", self.model.objects).order_by("uid")

    def render_is_active_column(self, value: bool) -> str:
        """
        Render the is_active column.
        """
        if value:
            return "<span class='badge bg-success'>Yes</span>"
        return "<span class='badge bg-danger'>No</span>"


# ====================================
# Groups
# ====================================


class GroupDataDetailWidget(WidgetStream):
    """
    Widget for displaying detailed group information.

    This widget renders a template containing detailed information about a group,
    including its name, description, and members.

    """

    def __init__(
        self,
        group: LDAPGroup,
    ) -> None:
        """
        Initialize the group data detail widget.

        Args:
            group: The LDAPGroup object whose details will be displayed

        """
        name = Block(
            Block("Name", css_class="fw-bold"),
            Block(group.cn),  # type: ignore[arg-type]
            css_class=(  # type: ignore[arg-type]
                "d-flex justify-content-between p-3 bg-blue text-blue-fg border-bottom",
            ),
        )
        gid_number = Block(
            Block("Group ID", css_class="fw-bold"),
            Block(group.gid_number),  # type: ignore[arg-type]
            css_class=(  # type: ignore[arg-type]
                "d-flex justify-content-between p-3 bg-grey-200 text-grey-200-fg "
                "border-bottom",
            ),
        )
        n_users = Block(
            Block("Number of Users", css_class="fw-bold"),
            Block(len(group.memberUid)),  # type: ignore[arg-type]
            css_class=(  # type: ignore[arg-type]
                "d-flex justify-content-between p-3 bg-grey-200 text-grey-200-fg "
                "border-bottom",
            ),
        )

        super().__init__([name, gid_number, n_users])


class GroupConfigurationWidget(WidgetStream):
    """
    Widget for displaying group configuration information.
    """

    title: str = "Group Configuration"
    icon: str = "gear-fill"
    name: str = "group-configuration"

    def __init__(self, group: LDAPGroup) -> None:
        dn = ValueBlock("Distinguished Name", group.dn)
        description = ValueBlock("Description", group.description)
        super().__init__([dn, description])


class GroupMembershipTableWidget(CardWidget):
    """
    Widget for displaying a group membership table.
    """

    title: str = "Group Membership"
    icon: str = "people-fill"
    name: str = "group-membership-table"


class GroupTableWidget(CardWidget):
    """
    Widget for displaying a group table.
    """

    title: str = "Groups"
    icon: str = "collection"
    name: str = "group-table"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(GroupTable, **kwargs)

    def get_title(self) -> WidgetListLayoutHeader:
        """
        Get the title for the widget.
        """
        return WidgetListLayoutHeader(
            header_text=self.title,
            badge_text=len(cast("LdapManager", LDAPGroup.objects).all()),
        )


class GroupMembershipTable(LdapModelTableMixin, DataTable):
    """
    A data table that displays the members of a group.
    """

    model: type[LdapModel] = LDAPGroup
    page_length: int = 25
    striped: bool = True

    def __init__(self, group: LDAPGroup, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.add_column("uid", "UID")
        self.add_column("full_name", "Name")
        self.add_column("employee_number", "Employee Number")
        self.add_column("is_active", "Active?")
        self.add_column("actions", "Actions")
        users = LDAPUser.objects.filter(uid__in=group.memberUid)
        for user in users:
            self.add_row(
                user.uid,
                user.full_name,
                user.employee_number,
                user.is_active,
            )

    def render_actions_column(self, row: LDAPUser, _: str) -> str:
        """
        Render the actions column.
        """
        actions = []
        actions.append(
            f"<a class='btn btn-primary me-2' href='{reverse('core:user--detail', args=[row.uid])}'>View</a>"  # noqa: E501
        )
        actions.append(
            f"<a class='btn btn-danger' href='{reverse('core:group--user--remove', args=[row.uid])}' onclick='return confirm(\"Are you sure you want to remove this user from the group?\")'>Remove</a>"  # noqa: E501
        )
        return '<div class="d-flex flex-row">{}</div>'.format("".join(actions))


class GroupTable(LdapModelTableMixin, BasicModelTable):
    """
    A data table that displays a list of all groups.
    """

    model: type[LdapModel] = LDAPGroup
    page_length: int = 25
    striped: bool = True
    fields: ClassVar[list[str]] = ["cn", "gid_number", "memberUid"]
    verbose_names: ClassVar[dict[str, str]] = {
        "cn": "Name",
        "gid_number": "Group ID",
        "memberUid": "Members",
    }

    def get_initial_queryset(self) -> F:
        """
        Get the initial queryset for the table.
        """
        return cast("LdapManager", self.model.objects).order_by("cn")

    def render_memberUid_column(self, value: list[str]) -> str:  # noqa: N802
        """
        Render the memberUid column.
        """
        return "<br>".join(value)


# ====================================
# Roles
# ====================================


class RoleTableWidget(CardWidget):
    """
    Widget for displaying a role table.
    """

    title: str = "Roles"
    icon: str = "card-checklist"
    name: str = "role-table"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(RoleTable, **kwargs)

    def get_title(self) -> WidgetListLayoutHeader:
        """
        Get the title for the widget.
        """
        return WidgetListLayoutHeader(
            header_text=self.title,
            badge_text=len(cast("LdapManager", NSRole.objects).all()),
        )


class RoleTable(LdapModelTableMixin, BasicModelTable):
    """
    A data table that displays a list of all roles.
    """

    model: type[LdapModel] = NSRole
    page_length: int = 25
    striped: bool = True
    fields: ClassVar[list[str]] = ["cn", "description"]
    verbose_names: ClassVar[dict[str, str]] = {
        "cn": "Name",
        "description": "Description",
    }

    def get_initial_queryset(self) -> F:
        """
        Get the initial queryset for the table.
        """
        return cast("LdapManager", self.model.objects).order_by("cn")
