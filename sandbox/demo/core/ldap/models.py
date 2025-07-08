from typing import TYPE_CHECKING, Final, cast

from ldaporm.fields import (
    AllCapsBooleanField,
    CharField,
    CharListField,
    IntegerField,
)
from ldaporm.models import Model
from ldaporm.validators import EmailForwardValidator

if TYPE_CHECKING:
    from ldaporm.managers import LdapManager


def get_next_group_gid() -> int:
    """
    Return the next available gid_number for a group by finding the maximum
    gid_number in the LDAP and adding 1.
    """
    current_gid: int = 0
    for group in cast("LdapManager", LDAPGroup.objects).all():
        _group: LDAPGroup = cast("LDAPGroup", group)
        if not _group.gid_number:
            continue
        current_gid = max(_group.gid_number, current_gid)  # type: ignore[assignment]
    return current_gid + 1


class LDAPUser(Model):
    """
    LDAP model for POSIX users.
    """

    LOGIN_SHELL_CHOICES: Final[list[tuple[str, str]]] = [
        ("/bin/csh", "C Shell"),
        ("/bin/tcsh", "Tcsh"),
        ("/bin/bash", "Bash"),
        ("/bin/zsh", "Zsh"),
        ("/bin/fish", "Fish"),
    ]

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
    employee_number = IntegerField("Employee Number", db_column="employeeNumber")
    room_number = CharField("Room Number", max_length=50, db_column="roomNumber")
    home_phone = CharField("Home Phone", max_length=50, db_column="homePhone")
    mobile = CharField("Mobile", max_length=50, db_column="mobile")

    # Status
    is_disabled = AllCapsBooleanField(
        "User Account Control", default=True, db_column="loginDisabled"
    )

    # 389-ds fields
    nsroledn = CharListField(
        "RoleDNs",
        max_length=254,
        db_column="nsroledn",
        help_text="List of NSRole DNs",
    )
    nsrole = CharListField(
        "Roles",
        max_length=254,
        db_column="nsrole",
        help_text="List of all nsroles, managed, search and nested roles",
    )

    class Meta:
        ldap_server = "default"
        basedn = "ou=people,o=example,c=us"
        objectclass = "posixAccount"
        extra_objectclasses = [  # noqa: RUF012
            "top",
            "inetOrgPerson",
        ]
        verbose_name = "LDAP User"
        verbose_name_plural = "LDAP Users"
        ordering = ["uid"]  # noqa: RUF012

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
