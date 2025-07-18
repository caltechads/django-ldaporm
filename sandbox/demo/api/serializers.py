from demo.core.ldap.models import LDAPGroup, LDAPUser, NSRole
from ldaporm.restframework import LdapModelSerializer


class LDAPUserSerializer(LdapModelSerializer):
    """Serializer for LDAPUser model."""

    class Meta:
        model = LDAPUser
        fields = (
            "uid",
            "full_name",
            "last_name",
            "first_name",
            "mail",
            "uid_number",
            "gid_number",
            "home_directory",
            "login_shell",
            "employee_number",
            "room_number",
            "home_phone",
            "mobile",
            "nsroledn",
            "nsrole",
        )


class LDAPGroupSerializer(LdapModelSerializer):
    """Serializer for LDAPGroup model."""

    class Meta:
        model = LDAPGroup
        fields = (
            "cn",
            "gid_number",
            "member_uids",
            "description",
        )


class NSRoleSerializer(LdapModelSerializer):
    """Serializer for NSRole model."""

    class Meta:
        model = NSRole
        fields = (
            "cn",
            "description",
        )
