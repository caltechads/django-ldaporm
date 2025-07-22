from typing import TYPE_CHECKING, ClassVar, cast

from rest_framework import viewsets
from rest_framework.filters import BaseFilterBackend
from rest_framework.pagination import PageNumberPagination

from demo.core.ldap.models import NSRole
from ldaporm.restframework import LdapFilterBackend, LdapOrderingFilter

from ..serializers import NSRoleSerializer

if TYPE_CHECKING:
    from ldaporm.managers import LdapManager


class NSRoleFilter(LdapFilterBackend):
    """
    Filter backend for NSRole using the abstracted LdapFilterBackend.
    """

    filter_fields: ClassVar[dict[str, dict[str, str]]] = {
        "cn": {"lookup": "iexact", "type": "string"},
        "description": {"lookup": "icontains", "type": "string"},
    }


class NSRoleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for NSRole operations.
    Provides CRUD operations for NSRoles with filtering and ordering support.
    """

    serializer_class = NSRoleSerializer
    model = NSRole
    lookup_field = "cn"  # Use cn as the primary key for NSRoles
    pagination_class = PageNumberPagination  # Use standard pagination for testing
    filter_backends: ClassVar[list[BaseFilterBackend]] = [
        NSRoleFilter,
        LdapOrderingFilter,
    ]

    # Define which fields can be used for searching
    search_fields = (
        "cn",
        "description",
    )

    # Define which fields can be used for ordering
    ordering_fields = (
        "cn",
        "description",
    )

    ordering = ("cn",)

    def get_queryset(self):
        """
        Return the NSRole queryset.
        """
        return cast("LdapManager", NSRole.objects).all()
