from django import template

from demo.core.ldap.models import LDAPUser

register = template.Library()


@register.filter("role_name")
def role_name(value: str) -> str:
    """
    Return the cn of a role.

    Args:
        value: The role value

    Returns:
        The cn of the role.

    """
    return value.split(",")[0].split("=")[1]


@register.filter("derived_roles")
def derived_roles(person: LDAPUser) -> list[str]:
    return [role for role in person.nsrole if role not in person.nsroledn]  # type: ignore[operator]
