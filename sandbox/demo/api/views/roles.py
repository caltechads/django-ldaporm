from typing import TYPE_CHECKING, ClassVar, cast

from rest_framework import status, viewsets
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from demo.core.ldap.models import NSRole

from ..serializers import NSRoleSerializer

if TYPE_CHECKING:
    from ldaporm.managers import LdapManager


class NSRoleViewSet(viewsets.GenericViewSet):
    """
    ViewSet for NSRole operations.
    Provides CRUD operations for LDAP roles.
    """

    serializer_class = NSRoleSerializer
    permission_classes: ClassVar[list[type[BasePermission]]] = [IsAuthenticated]

    def get_queryset(self):
        """Return all LDAP roles."""
        return cast("LdapManager", NSRole.objects).all()

    def get_object(self):
        """Get a specific LDAP role by cn."""
        cn = self.kwargs.get("pk")
        return cast("LdapManager", NSRole.objects).get(cn=cn)

    def list(self, request: Request) -> Response:  # noqa: ARG002
        """List all LDAP roles."""
        roles = self.get_queryset()
        serializer = self.get_serializer(roles, many=True)
        return Response(serializer.data)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        """Retrieve a specific LDAP role."""
        try:
            role = self.get_object()
            serializer = self.get_serializer(role)
            return Response(serializer.data)
        except NSRole.DoesNotExist:
            return Response(
                {"error": "Role not found"}, status=status.HTTP_404_NOT_FOUND
            )

    def create(self, request: Request) -> Response:
        """Create a new LDAP role."""
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        """Update an LDAP role."""
        try:
            role = self.get_object()
            serializer = self.get_serializer(role, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except NSRole.DoesNotExist:
            return Response(
                {"error": "Role not found"}, status=status.HTTP_404_NOT_FOUND
            )

    def destroy(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        """Delete an LDAP role."""
        try:
            role = self.get_object()
            role.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except NSRole.DoesNotExist:
            return Response(
                {"error": "Role not found"}, status=status.HTTP_404_NOT_FOUND
            )
