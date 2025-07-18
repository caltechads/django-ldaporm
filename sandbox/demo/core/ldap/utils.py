from typing import TYPE_CHECKING, cast

from .models import LDAPGroup, LDAPUser

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


def get_next_user_uid() -> int:
    """
    Return the next available uid for a user by finding the maximum uid in the
    LDAP and adding 1.
    """
    current_uid: int = 0
    for user in cast("LdapManager", LDAPUser.objects).all():
        _user: LDAPUser = cast("LDAPUser", user)
        if not _user.uid_number:
            continue
        current_uid = max(_user.uid_number, current_uid)  # type: ignore[assignment]
    return current_uid + 1


def get_next_employee_number() -> int:
    """
    Return the next available employee number by finding the maximum employee number
    in the LDAP and adding 1.
    """
    current_employee_number: int = 0
    for user in cast("LdapManager", LDAPUser.objects).all():
        _user: LDAPUser = cast("LDAPUser", user)
        if not _user.employee_number:
            continue
        current_employee_number = max(_user.employee_number, current_employee_number)  # type: ignore[assignment]
    return current_employee_number + 1
