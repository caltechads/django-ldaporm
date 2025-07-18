from django.urls import path

from . import views

app_name: str = "core"

urlpatterns = [
    path("", views.UserListView.as_view(), name="user--list"),
    path("user/<str:uid>/edit/", views.UserDetailView.as_view(), name="user--detail"),
    path("user/add/", views.UserAddView.as_view(), name="user--add"),
    path(
        "users/<str:uid>/roles/",
        views.UserRolesUpdateView.as_view(),
        name="user--roles--update",
    ),
    path(
        "users/<str:uid>/reset-password/",
        views.UserResetPasswordView.as_view(),
        name="user--reset-password",
    ),
    path(
        "users/<str:uid>/verify-password/",
        views.VerifyPasswordAPI.as_view(),
        name="user--verify-password",
    ),
    path("groups/", views.GroupListView.as_view(), name="group--list"),
    path(
        "group/<str:gid>/edit/", views.GroupDetailView.as_view(), name="group--detail"
    ),
    path("group/add/", views.GroupAddView.as_view(), name="group--add"),
    path(
        "group/<str:gid>/add-member/",
        views.GroupAddMemberView.as_view(),
        name="group--user--add",
    ),
    path(
        "group/<str:gid>/remove-member/",
        views.GroupRemoveMemberView.as_view(),
        name="group--user--remove",
    ),
    path("roles/", views.RoleListView.as_view(), name="role--list"),
]
