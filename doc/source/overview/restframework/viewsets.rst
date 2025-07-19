Django REST Framework: ViewSets
==============================

For list endpoints, LDAP ORM provides integration with Django REST Framework
(DRF) through specialized viewsets that work with LDAP ORM models and fields.


URL Configuration
-----------------

Django URLs
~~~~~~~~~~~

.. code-block:: python

    from django.urls import path, include
    from rest_framework.routers import DefaultRouter
    from .views import UserViewSet, DepartmentViewSet

    router = DefaultRouter()
    router.register(r'users', UserViewSet, basename='user')
    router.register(r'departments', DepartmentViewSet, basename='department')

    urlpatterns = [
        path('api/', include(router.urls)),
    ]

ViewSet Example
~~~~~~~~~~~~~~~

You can just use the ``ModelViewSet`` class from DRF, and it will work with
LDAP ORM models and fields:

.. code-block:: python

    from rest_framework import viewsets
    from ldaporm.restframework import HyperlinkedModelSerializer, LdapCursorPagination

    class UserViewSet(viewsets.ModelViewSet):
        serializer_class = UserSerializer
        pagination_class = LdapCursorPagination
        lookup_field = 'dn'

        def get_queryset(self):
            return User.objects.all()
