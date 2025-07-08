from typing import TYPE_CHECKING, ClassVar, Final, cast

from django.http import HttpRequest
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from demo.core.ldap.models import LDAPGroup, get_next_group_gid
from demo.logging import logger

from ..serializers import LDAPGroupSerializer

if TYPE_CHECKING:
    from ldaporm.managers import LdapManager
    from ldaporm.models import Model

# --------------------------------------------------------
# LDAP Groups
# --------------------------------------------------------


class GroupEndpointPermission(permissions.IsAuthenticated):
    """
    Permission class for all the group endpoints.

    Since group changes are irreversable, we require the API user to have
    additional rights.

    First, the user must be authenticated. Then, the user must have
    the following permissions:

    - view group: ``core.view_group_api_endpoints``
    - add group: ``core.add_group_api_endpoints``
    - change group: ``core.change_group_api_endpoints``
    - delete group: ``core.delete_group_api_endpoints``
    """

    # add, change, delete, view

    def has_permission(self, request: HttpRequest, view: APIView) -> bool:
        is_authenticated = super().has_permission(request, view)
        if not is_authenticated:
            return False
        if request.method in ("GET", "HEAD"):
            return request.user.has_perm("core.view_group_api_endpoints")  # type: ignore[union-attr]
        if request.method == "POST":
            return request.user.has_perm("core.add_group_api_endpoints")  # type: ignore[union-attr]
        if request.method == "PUT":
            return request.user.has_perm("core.change_group_api_endpoints")  # type: ignore[union-attr]
        if request.method == "DELETE":
            return request.user.has_perm("core.delete_group_api_endpoints")  # type: ignore[union-attr]
        return False


class LDAPGlobalCreateGroupView(APIView):
    """
    Create groups in both trees - CAP and LDAP Auth.
    """

    http_method_names: Final[list[str]] = ["post"]
    permission_classes: ClassVar[list[type[BasePermission]]] = [GroupEndpointPermission]

    def post(self, request: Request) -> Response:
        group = request.data.get("cn", None)
        if not group:
            logger.warning("ldap.group.create.failed.no-group-name")
            return Response(status=status.HTTP_400_BAD_REQUEST)
        gid_number = get_next_group_gid()

        if cast("LdapManager", LDAPGroup.objects).filter(cn=group).exists():
            logger.warning("ldap.group.create.failed.group-exists", group=group)
            return Response(
                {"cn": ["Group already exists"]}, status=status.HTTP_400_BAD_REQUEST
            )

        cast("LdapManager", LDAPGroup.objects).create(
            cn=group,
            gid_number=gid_number,
            description=request.data.get("description", None),
        )

        logger.info("ldap.group.create.success", group=group)
        return Response(
            {"msg": "Group created successfully"}, status=status.HTTP_201_CREATED
        )


class LDAPGlobalGroupView(APIView):
    """
    Create groups in both trees - CAP and LDAP Auth.
    """

    http_method_names: Final[list[str]] = ["head", "get", "delete"]
    permission_classes = (GroupEndpointPermission,)

    def head(self, _: Request, group: str | None = None) -> Response:
        """
        The user sends HEAD to check for the existence of the group.
        """
        try:
            cast("LdapManager", LDAPGroup.objects).get(cn=group)
        except LDAPGroup.DoesNotExist:
            logger.warning("ldap.group.head.failed", group=group, tree="cap")
            return Response(
                {"group": ["CAP group not found"]}, status=status.HTTP_404_NOT_FOUND
            )
        logger.info("ldap.group.head.success", group=group)
        return Response({"status": "Group exists"})

    def get(self, _: Request, group: str | None = None) -> Response:
        """
        The user sends GET to get the content of the specified group.
        """
        try:
            group_obj: LDAPGroup = cast("LdapManager", LDAPGroup.objects).get(cn=group)
        except LDAPGroup.DoesNotExist:
            logger.warning("ldap.group.get.failed", group=group)
            return Response(
                {"group": ["Group not found"]}, status=status.HTTP_404_NOT_FOUND
            )
        data = {
            "cn": group_obj.cn,
            "gid": group_obj.gid_number,
            "description": group_obj.description,
        }
        logger.info("ldap.group.get.success", group=group)
        return Response(data)

    def delete(self, _: Request, group: str | None = None) -> Response:
        """
        The user sends DELETE to delete the specified group.
        """
        try:
            group_obj: Model = cast("LdapManager", LDAPGroup.objects).get(cn=group)
        except LDAPGroup.DoesNotExist:
            logger.warning("ldap.group.delete.failed", group=group)
            return Response(
                {"group": ["CAP group not found"]}, status=status.HTTP_404_NOT_FOUND
            )
        group_obj.delete()
        logger.info("ldap.group.delete.success", group=group)
        return Response({"status": "Group deleted"})


class LDAPGroupView(APIView):
    """
    Manage groups
    """

    http_method_names: Final[list[str]] = ["head", "get"]
    permission_classes = (GroupEndpointPermission,)

    def head(self, _: Request, group: str | None = None) -> Response:
        """
        The user sends HEAD to check for the existence of the group.
        """
        try:
            cast("LdapManager", LDAPGroup.objects).get(cn=group)
        except LDAPGroup.DoesNotExist:
            logger.warning("ldap.group.head.failed", group=group)
            return Response(
                {"group": ["Group not found"]}, status=status.HTTP_404_NOT_FOUND
            )
        logger.info("ldap.group.head.success", group=group)
        return Response({"status": "Group exists"})

    def get(
        self,
        _: Request,
        group: str | None = None,
    ) -> Response:
        """
        The user sends GET to get the content of the specified group.


        """
        try:
            group_obj: Model = cast("LdapManager", LDAPGroup.objects).get(cn=group)
        except LDAPGroup.DoesNotExist:
            logger.warning("ldap.group.get.missing", group=group)
            return Response(
                {"group": ["Group not found"]}, status=status.HTTP_404_NOT_FOUND
            )
        data = {
            "cn": group_obj.cn,
            "gid": group_obj.gid_number,
            "description": group_obj.description,
            "members": group_obj.memberUid,
        }
        logger.info("ldap.group.get.success", group=group)
        return Response(data)


class LDAPGroupMembersView(APIView):
    """
    View for managing members of a group.
    """

    http_method_names: Final[list[str]] = ["get", "put", "post", "delete"]
    permission_classes = (GroupEndpointPermission,)

    def get(self, _: Request, group: str | None = None) -> Response:
        """
        The user sends GET to get the content of the specified group.
        """
        try:
            group_obj: Model = cast("LdapManager", LDAPGroup.objects).get(cn=group)
        except LDAPGroup.DoesNotExist:
            logger.warning("ldap.group.members.get.missing", group=group)
            return Response(
                {"group": ["Group not found"]}, status=status.HTTP_404_NOT_FOUND
            )
        data = {
            "cn": group_obj.cn,
            "members": group_obj.memberUid,
        }
        logger.info("ldap.group.members.get.success", group=group)
        return Response(data)

    def put(
        self,
        request: Request,
        group: str | None = None,
    ) -> Response:
        """
        The user sends PUT to add a member to a group
        """
        # First ensure the group exists
        try:
            group_obj: Model = cast("LdapManager", LDAPGroup.objects).get(cn=group)
        except LDAPGroup.DoesNotExist:
            logger.warning("ldap.group.members.put.missing", group=group)
            return Response(
                {"group": ["Group not found"]}, status=status.HTTP_404_NOT_FOUND
            )
        data = request.data
        if "members" not in data:
            logger.warning("ldap.group.members.put.missing_members", group=group)
            return Response(
                {"member": ["Member not found"]}, status=status.HTTP_404_NOT_FOUND
            )
        members = data["members"]
        for member in members:
            if member in group_obj.members:
                continue
            group_obj.memberUid.append(member)
        group_obj.save()
        logger.info("ldap.group.members.put.success", group=group, members=members)
        return Response({"status": "members added"})

    def post(
        self,
        request: Request,
        group: str | None = None,
    ) -> Response:
        """
        The user sends POST to set the members of a group
        """
        # First ensure the group exists
        try:
            group_obj: Model = cast("LdapManager", LDAPGroup.objects).get(cn=group)
        except LDAPGroup.DoesNotExist:
            logger.warning("ldap.group.members.post.missing", group=group)
            return Response(
                {"group": ["Group not found"]}, status=status.HTTP_404_NOT_FOUND
            )
        data = request.data
        if "members" not in data:
            return Response(
                {"member": ["Member not found"]}, status=status.HTTP_404_NOT_FOUND
            )
        members = data["members"]
        group_obj.memberUid = members
        group_obj.save()
        logger.info("ldap.group.members.post.success", group=group, members=members)
        return Response({"status": "members removed"})

    def delete(
        self,
        _: Request,
        group: str | None = None,
    ) -> Response:
        """
        The user sends DELETE to remove all members from a group
        """
        # First ensure the group exists
        try:
            group_obj: Model = cast("LdapManager", LDAPGroup.objects).get(cn=group)
        except LDAPGroup.DoesNotExist:
            logger.warning("ldap.group.members.delete.missing", group=group)
            return Response(
                {"group": ["Group not found"]}, status=status.HTTP_404_NOT_FOUND
            )
        group_obj.memberUid = []
        group_obj.save()
        logger.info("ldap.group.members.delete.success", group=group)
        return Response({"status": "all members removed"})


class LDAPGroupRemoveMemberView(APIView):
    """
    View for removing a member from a group.
    """

    http_method_names: Final[list[str]] = ["delete"]
    permission_classes = (GroupEndpointPermission,)

    def delete(
        self,
        _: Request,
        group: str | None = None,
        member: str | None = None,
    ) -> Response:
        """
        The user sends DELETE to remove a member from a group
        """
        try:
            group_obj: Model = cast("LdapManager", LDAPGroup.objects).get(cn=group)
        except LDAPGroup.DoesNotExist:
            logger.warning("ldap.group.member.delete.missing", group=group)
            return Response(
                {"group": ["Group not found"]}, status=status.HTTP_404_NOT_FOUND
            )
        group_obj.memberUid.remove(member)
        group_obj.save()
        logger.info("ldap.group.member.delete.success", group=group, member=member)
        return Response({"status": "member removed"})


class LDAPGroupViewSet(viewsets.GenericViewSet):
    """
    ViewSet for LDAP Group operations.
    Provides CRUD operations for LDAP groups.
    """

    serializer_class = LDAPGroupSerializer
    permission_classes: ClassVar[list[type[BasePermission]]] = [IsAuthenticated]

    def get_queryset(self):
        """Return all LDAP groups."""
        return LDAPGroup.objects.all()

    def get_object(self) -> LDAPGroup:
        """Get a specific LDAP group by cn."""
        cn = self.kwargs.get("pk")
        return cast("LdapManager", LDAPGroup.objects).get(cn=cn)

    def list(self, request: Request) -> Response:  # noqa: ARG002
        """List all LDAP groups."""
        groups = self.get_queryset()
        serializer = self.get_serializer(groups, many=True)
        return Response(serializer.data)

    def retrieve(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        """Retrieve a specific LDAP group."""
        try:
            group = self.get_object()
            serializer = self.get_serializer(group)
            return Response(serializer.data)
        except LDAPGroup.DoesNotExist:
            return Response(
                {"error": "Group not found"}, status=status.HTTP_404_NOT_FOUND
            )

    def create(self, request: Request) -> Response:
        """Create a new LDAP group."""
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        """Update an LDAP group."""
        try:
            group = self.get_object()
            serializer = self.get_serializer(group, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except LDAPGroup.DoesNotExist:
            return Response(
                {"error": "Group not found"}, status=status.HTTP_404_NOT_FOUND
            )

    def destroy(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        """Delete an LDAP group."""
        try:
            group = self.get_object()
            group.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except LDAPGroup.DoesNotExist:
            return Response(
                {"error": "Group not found"}, status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=["get"])
    def member_count(self, request: Request, pk: str | None = None) -> Response:  # noqa: ARG002
        """Get the number of members in a group."""
        try:
            group = self.get_object()
            return Response({"member_count": group.get_member_count()})
        except LDAPGroup.DoesNotExist:
            return Response(
                {"error": "Group not found"}, status=status.HTTP_404_NOT_FOUND
            )
