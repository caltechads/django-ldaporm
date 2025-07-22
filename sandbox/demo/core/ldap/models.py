from typing import Final

from django.urls import reverse

from ldaporm.fields import (
    CharField,
    CharListField,
    DateTimeField,
    IntegerField,
)
from ldaporm.models import Model
from ldaporm.validators import EmailForwardValidator


class LDAPUser(Model):
    """
    LDAP model for POSIX users.
    """

    #: Login shell choices
    LOGIN_SHELL_CHOICES: Final[list[tuple[str, str]]] = [
        ("/bin/csh", "C Shell"),
        ("/bin/tcsh", "Tcsh"),
        ("/bin/bash", "Bash"),
        ("/bin/zsh", "Zsh"),
        ("/bin/fish", "Fish"),
    ]

    #: Employee type choices
    EMPLOYEE_TYPE_CHOICES: Final[list[tuple[str, str]]] = [
        ("employee", "Employee"),
        ("contractor", "Contractor"),
        ("intern", "Intern"),
        ("manager", "Manager"),
        ("external", "External"),
    ]

    def get_absolute_url(self) -> str:
        """
        Return the absolute URL for the user.
        """
        return reverse("core:user--detail", kwargs={"uid": self.uid})

    # Identity fields
    uid = CharField("uid", primary_key=True, max_length=50)
    full_name = CharField("Full Name", max_length=100, db_column="cn")
    last_name = CharField("Last Name", max_length=100, db_column="sn")
    first_name = CharField("First Name", max_length=100, db_column="givenName")

    # Contact information
    mail = CharListField(
        "Aliases",
        max_length=254,
        help_text="List of email addresses for this user",
        validators=[EmailForwardValidator()],
    )

    # POSIX fields
    uid_number = IntegerField("UID Number", db_column="uidNumber")
    gid_number = IntegerField("GID Number", db_column="gidNumber")
    home_directory = CharField(
        "Home Directory", max_length=200, db_column="homeDirectory"
    )
    login_shell = CharField(
        "Login Shell", max_length=50, default="/bin/bash", db_column="loginShell"
    )

    # inetOrgPerson fields
    employee_type = CharField(
        "Employee Type", max_length=50, null=True, db_column="employeeType"
    )
    employee_number = IntegerField("Employee Number", db_column="employeeNumber")
    room_number = CharField("Room Number", max_length=50, db_column="roomNumber")
    home_phone = CharField("Home Phone", max_length=50, db_column="homePhone")
    mobile = CharField("Mobile", max_length=50, db_column="mobile")

    # 389-ds fields
    created_at = DateTimeField(
        "Created At",
        null=True,
        blank=True,
        default=None,
        db_column="createTimestamp",
        editable=False,
    )
    created_by = CharField(
        "Created By",
        null=True,
        blank=True,
        default=None,
        db_column="creatorsName",
        editable=False,
    )
    updated_at = DateTimeField(
        "Updated At",
        null=True,
        blank=True,
        default=None,
        db_column="modifyTimestamp",
        editable=False,
    )
    updated_by = CharField(
        "Updated By",
        null=True,
        blank=True,
        default=None,
        db_column="modifiersName",
        editable=False,
    )

    nsroledn = CharListField(
        "nsroledn",
        max_length=255,
        help_text="List of NSRole DNs",
    )
    nsrole = CharListField(
        "nsrole",
        blank=True,
        default=None,
        editable=False,
        help_text="List of all nsroles, managed, search and nested roles",
    )

    class Meta:
        ldap_server: str = "default"
        basedn: str = "ou=people,o=example,c=us"
        objectclass: str = "posixAccount"
        extra_objectclasses: list[str] = [  # noqa: RUF012
            "top",
            "inetOrgPerson",
        ]
        verbose_name: str = "LDAP User"
        verbose_name_plural: str = "LDAP Users"
        ordering: list[str] = ["uid"]  # noqa: RUF012
        password_attribute: str = "userPassword"  # noqa: S105

    def get_full_name(self) -> str:
        """Return the user's full name."""
        return f"{self.first_name} {self.last_name}"

    def __str__(self) -> str:
        return f"{self.full_name} (uid: {self.uid})"

    def __repr__(self) -> str:
        return f"<LDAPUser: {self.uid}>"


class LDAPGroup(Model):
    """LDAP model for POSIX groups."""

    cn = CharField(
        "Common Name", primary_key=True, max_length=50, help_text="Common Name"
    )
    gid_number = IntegerField(
        "GID Number", db_column="gidNumber", help_text="GID Number"
    )
    member_uids = CharListField(
        "Member UID",
        max_length=50,
        db_column="memberUid",
        help_text="List of UIDs of group members",
    )
    description = CharField(
        "Description", max_length=200, blank=True, help_text="Description of the group"
    )

    class Meta:
        ldap_server = "default"
        basedn = "ou=groups,o=example,c=us"
        objectclass = "posixGroup"
        extra_objectclasses = [  # noqa: RUF012
            "top",
        ]
        verbose_name = "LDAP Group"
        verbose_name_plural = "LDAP Groups"
        ordering = ["cn"]  # noqa: RUF012

    def get_member_count(self) -> int:
        """Return the number of members in the group."""
        return len(self.member_uids) if self.member_uids else 0  # type: ignore[arg-type]

    def __str__(self) -> str:
        return f"{self.cn} (gid: {self.gid_number})"

    def __repr__(self) -> str:
        return f"<LDAPGroup: {self.cn}>"


class NSRole(Model):
    """LDAP model for NSRoles."""

    cn = CharField(
        "Common Name", primary_key=True, max_length=50, help_text="Common Name"
    )
    description = CharField(
        "Description", max_length=200, blank=True, help_text="Description of the role"
    )

    class Meta:
        ldap_server = "default"
        basedn = "ou=roles,o=example,c=us"
        objectclass = "ldapsubentry"
        extra_objectclasses = [  # noqa: RUF012
            "top",
            "nsroledefinition",
            "nssimpleroledefinition",
            "nsmanagedroledefinition",
        ]
        verbose_name = "Role"
        verbose_name_plural = "Roles"
        ordering = ["cn"]  # noqa: RUF012
