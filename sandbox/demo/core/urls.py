from django.urls import path

from . import views

app_name: str = "ldap_users"

urlpatterns = [
    path("", views.UserListView.as_view(), name="user--list"),
    path("users/<str:uid>/", views.UserDetailView.as_view(), name="user--detail"),
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
    path("groups/<str:uid>/", views.GroupDetailView.as_view(), name="group--detail"),
    path(
        "groups/<str:uid>/remove-member/<str:member_uid>/",
        views.GroupRemoveMemberView.as_view(),
        name="group--user--remove",
    ),
]
