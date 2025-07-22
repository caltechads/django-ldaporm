from typing import TYPE_CHECKING, ClassVar, cast

from rest_framework import viewsets
from rest_framework.filters import BaseFilterBackend
from rest_framework.pagination import PageNumberPagination

from demo.core.ldap.models import LDAPGroup
from ldaporm.restframework import LdapFilterBackend, LdapOrderingFilter

from ..serializers import LDAPGroupSerializer

if TYPE_CHECKING:
    from ldaporm.managers import LdapManager


class LDAPGroupFilter(LdapFilterBackend):
    """
    Filter backend for LDAPGroup using the abstracted LdapFilterBackend.
    """

    filter_fields: ClassVar[dict[str, dict[str, str]]] = {
        "cn": {"lookup": "iexact", "type": "string"},
        "gid_number": {"lookup": "iexact", "type": "integer"},
        "description": {"lookup": "icontains", "type": "string"},
    }


class LDAPGroupViewSet(viewsets.ModelViewSet):
    """
    ViewSet for LDAP Group operations.
    Provides CRUD operations for LDAP groups with filtering and ordering support.
    """

    serializer_class = LDAPGroupSerializer
    model = LDAPGroup
    lookup_field = "cn"  # Use cn as the primary key for LDAP groups
    pagination_class = PageNumberPagination  # Use standard pagination for testing
    filter_backends: ClassVar[list[BaseFilterBackend]] = [
        LDAPGroupFilter,
        LdapOrderingFilter,
    ]

    # Define which fields can be used for searching
    search_fields = (
        "cn",
        "gid_number",
        "description",
        "member_uids",
    )

    # Define which fields can be used for ordering
    ordering_fields = (
        "cn",
        "gid_number",
        "description",
        "member_uids",
    )

    ordering = ("cn",)

    def get_queryset(self):
        """
        Return the LDAP group queryset.
        """
        return cast("LdapManager", LDAPGroup.objects).all()
