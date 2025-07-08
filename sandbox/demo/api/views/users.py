from typing import ClassVar

from rest_framework import status, viewsets
from rest_framework.jdecorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from demo.core.ldap.models import LDAPUser

from ..serializers import LDAPUserSerializer


class LDAPUserViewSet(viewsets.GenericViewSet):
    """
    ViewSet for LDAP User operations.
    Provides CRUD operations for LDAP users.
    """

    serializer_class = LDAPUserSerializer
    permission_classes: ClassVar[list[type[BasePermission]]] = [IsAuthenticated]

    def get_queryset(self):
        """Return all LDAP users."""
        return LDAPUser.objects.all()

    def get_object(self):
        """Get a specific LDAP user by uid."""
        uid = self.kwargs.get("pk")
        return LDAPUser.objects.get(uid=uid)

    def list(self, request: Request) -> Response:  # noqa: ARG002
        """List all LDAP users."""
        users = self.get_queryset()
        serializer = self.get_serializer(users, many=True)
        return Response(serializer.data)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        """Retrieve a specific LDAP user."""
        try:
            user = self.get_object()
            serializer = self.get_serializer(user)
            return Response(serializer.data)
        except LDAPUser.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

    def create(self, request: Request) -> Response:
        """Create a new LDAP user."""
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        """Update an LDAP user."""
        try:
            user = self.get_object()
            serializer = self.get_serializer(user, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except LDAPUser.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

    def destroy(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        """Delete an LDAP user."""
        try:
            user = self.get_object()
            user.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except LDAPUser.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=["get"])
    def full_name(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        """Get the full name of a user."""
        try:
            user = self.get_object()
            return Response({"full_name": user.full_name})
        except LDAPUser.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
