from typing import TYPE_CHECKING, ClassVar, cast

from rest_framework import viewsets
from rest_framework.filters import BaseFilterBackend
from rest_framework.pagination import PageNumberPagination

from demo.core.ldap.models import LDAPUser
from ldaporm.restframework import LdapFilterBackend, LdapOrderingFilter

from ..serializers import LDAPUserSerializer

if TYPE_CHECKING:
    from ldaporm.managers import LdapManager


class LDAPUserFilter(LdapFilterBackend):
    """
    Filter backend for LDAPUser using the abstracted LdapFilterBackend.
    """

    filter_fields: ClassVar[dict[str, dict[str, str]]] = {
        "uid": {"lookup": "iexact", "type": "string"},
        "mail": {"lookup": "icontains", "type": "string"},
        "employee_number": {"lookup": "iexact", "type": "integer"},
        "employee_type": {"lookup": "iexact", "type": "string"},
        "full_name": {"lookup": "icontains", "type": "string"},
        "gid_number": {"lookup": "iexact", "type": "integer"},
        "uid_number": {"lookup": "iexact", "type": "integer"},
        "login_shell": {"lookup": "iexact", "type": "string"},
    }


class LDAPUserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for LDAP User operations.
    Provides CRUD operations for LDAP users with filtering and ordering support.

    This ViewSet demonstrates how to use LdapOrderingFilter alongside a custom
    filter backend for LDAP models. The ordering filter leverages LDAP ORM's
    server-side sorting capabilities when available.

    Example API calls:
    - GET /api/users/                           # Default ordering (uid)
    - GET /api/users/?ordering=cn               # Order by cn ascending
    - GET /api/users/?ordering=-cn              # Order by cn descending
    - GET /api/users/?ordering=uid,-cn,mail     # Multiple field ordering
    - GET /api/users/?uid=testuser1             # Filter by uid
    - GET /api/users/?employee_type=staff       # Filter by employee type
    - GET /api/users/?employee_type=staff&ordering=uid  # Filter + ordering
    """

    serializer_class = LDAPUserSerializer
    model = LDAPUser
    lookup_field = "uid"  # Use uid as the primary key for LDAP users
    pagination_class = PageNumberPagination  # Use standard pagination for testing
    filter_backends: ClassVar[list[BaseFilterBackend]] = [
        LDAPUserFilter,
        LdapOrderingFilter,
    ]

    # Define which fields can be used for searching
    search_fields = (
        "uid",
        "full_name",
        "mail",
        "employee_number",
        "employee_type",
        "gid_number",
        "uid_number",
        "login_shell",
        "home_directory",
        "home_phone",
        "mobile",
        "nsroledn",
    )

    # Define which fields can be used for ordering
    ordering_fields = (
        "uid",
        "full_name",
        "mail",
        "employee_number",
        "employee_type",
        "gid_number",
        "uid_number",
        "login_shell",
        "home_directory",
        "home_phone",
        "mobile",
    )

    ordering = ("uid",)

    def get_queryset(self):
        """
        Return the LDAP user queryset.
        """
        return cast("LdapManager", LDAPUser.objects).all()
