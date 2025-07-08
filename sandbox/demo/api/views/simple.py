from typing import TYPE_CHECKING, ClassVar, cast

from rest_framework import status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from demo.core.ldap.models import LDAPUser

from ..serializers import LDAPUserSerializer

if TYPE_CHECKING:
    from ldaporm.managers import LdapManager


class LDAPUserListAPIView(APIView):
    """
    Simple APIView example for listing LDAP users.
    Shows how to use LdapModelSerializer with individual views.
    """

    permission_classes: ClassVar[list[type[BasePermission]]] = [IsAuthenticated]

    def get(self, request: Request) -> Response:  # noqa: ARG002
        """List all LDAP users."""
        users = cast("LdapManager", LDAPUser.objects).all()
        serializer = LDAPUserSerializer(users, many=True)
        return Response(serializer.data)

    def post(self, request):
        """Create a new LDAP user."""
        serializer = LDAPUserSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LDAPUserDetailAPIView(APIView):
    """
    Simple APIView example for individual LDAP user operations.
    """

    permission_classes: ClassVar[list[type[BasePermission]]] = [IsAuthenticated]

    def get(self, request: Request, uid: str) -> Response:  # noqa: ARG002
        """Get a specific LDAP user."""
        try:
            user = cast("LdapManager", LDAPUser.objects).get(uid=uid)
            serializer = LDAPUserSerializer(user)
            return Response(serializer.data)
        except LDAPUser.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

    def put(self, request: Request, uid: str) -> Response:
        """Update a specific LDAP user."""
        try:
            user = cast("LdapManager", LDAPUser.objects).get(uid=uid)
            serializer = LDAPUserSerializer(user, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except LDAPUser.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

    def delete(self, request: Request, uid: str) -> Response:  # noqa: ARG002
        """Delete a specific LDAP user."""
        try:
            user = cast("LdapManager", LDAPUser.objects).get(uid=uid)
            user.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except LDAPUser.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
