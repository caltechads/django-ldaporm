Django REST Framework: ViewSets
===============================

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

- ``LDAPCursorPagination`` is a pagination class that uses the ``.page()`` method
  to get paged results.
- ``LdapOrderingFilter`` is a filter class that allows you to order the results
  by a given attribute.
- ``LdapFilterBackend`` is an abstract base class for creating custom filter backends
  that work with LDAP ORM models.

.. code-block:: python

    from typing import cast

    from ldaporm.managers import LdapManager
    from ldaporm.restframework import HyperlinkedModelSerializer, LdapCursorPagination, LdapOrderingFilter, LdapFilterBackend
    from rest_framework import viewsets

    from .mycode.ldap.models import LDAPUser

    class UserFilterBackend(LdapFilterBackend):
        """
        Custom filter backend for LDAPUser using the abstracted LdapFilterBackend.
        """
        filter_fields = {
            'uid': {'lookup': 'iexact', 'type': 'string'},
            'mail': {'lookup': 'icontains', 'type': 'string'},
            'employee_number': {'lookup': 'iexact', 'type': 'integer'},
            'employee_type': {'lookup': 'iexact', 'type': 'string'},
            'full_name': {'lookup': 'icontains', 'type': 'string'},
            'gid_number': {'lookup': 'iexact', 'type': 'integer'},
            'uid_number': {'lookup': 'iexact', 'type': 'integer'},
            'login_shell': {'lookup': 'iexact', 'type': 'string'},
        }

    class UserViewSet(viewsets.ModelViewSet):
        model = LDAPUser
        serializer_class = UserSerializer
        pagination_class = LdapCursorPagination
        lookup_field = 'uid'
        filter_backends = [UserFilterBackend, LdapOrderingFilter]
        ordering_fields = ['uid', 'full_name']
        ordering = ('uid', )

        def get_queryset(self):
            return cast("LdapManager", LDAPUser.objects).all()

Filter Backend Configuration
----------------------------

The ``LdapFilterBackend`` provides a configuration-driven approach to filtering
LDAP ORM models. You define filterable fields and their behavior in a
``filter_fields`` dictionary.

Field Configuration
~~~~~~~~~~~~~~~~~~~

Each field in the ``filter_fields`` dictionary can be configured with:

- **lookup**: The LDAP ORM lookup type (e.g., 'iexact', 'icontains', 'exact')
- **type**: The field type for value conversion ('string', 'integer', 'boolean', 'float')

.. code-block:: python

    class DepartmentFilterBackend(LdapFilterBackend):
        filter_fields = {
            'name': {'lookup': 'icontains', 'type': 'string'},
            'code': {'lookup': 'iexact', 'type': 'string'},
            'budget': {'lookup': 'gte', 'type': 'integer'},
            'active': {'lookup': 'exact', 'type': 'boolean'},
        }

Supported Lookup Types
~~~~~~~~~~~~~~~~~~~~~~

- **iexact**: Case-insensitive exact match
- **icontains**: Case-insensitive contains
- **exact**: Exact match
- **contains**: Contains
- **startswith**: Starts with
- **endswith**: Ends with
- **gte**: Greater than or equal
- **lte**: Less than or equal
- **gt**: Greater than
- **lt**: Less than

Supported Field Types
~~~~~~~~~~~~~~~~~~~~~

- **string**: String values (no conversion)
- **integer**: Integer values (converts string to int)
- **boolean**: Boolean values (converts string to bool)
- **float**: Float values (converts string to float)

API Usage Examples
~~~~~~~~~~~~~~~~~~

With the above filter backend, you can make API calls like:

.. code-block:: bash

    # Filter by user ID (exact match)
    GET /api/users/?uid=john.doe

    # Filter by email (contains)
    GET /api/users/?mail=example.com

    # Filter by employee type (exact match)
    GET /api/users/?employee_type=staff

    # Filter by full name (contains)
    GET /api/users/?full_name=John

    # Filter by employee number (exact match)
    GET /api/users/?employee_number=12345

    # Combine filtering with ordering
    GET /api/users/?employee_type=staff&ordering=uid

    # Multiple filters
    GET /api/users/?employee_type=staff&gid_number=1000&ordering=-full_name

Advanced Filter Backend
~~~~~~~~~~~~~~~~~~~~~~~

For more complex filtering logic, you can override the ``get_filter_queryset`` method:

.. code-block:: python

    class AdvancedUserFilterBackend(LdapFilterBackend):
        filter_fields = {
            'uid': {'lookup': 'iexact', 'type': 'string'},
            'mail': {'lookup': 'icontains', 'type': 'string'},
        }

        def get_filter_queryset(self, request, queryset, view):
            """
            Apply custom filtering logic beyond the standard filter_fields.
            """
            # Apply standard filters first
            queryset = self.apply_filters(request, queryset)

            # Add custom filtering logic
            department = request.query_params.get('department')
            if department:
                queryset = queryset.filter(department__icontains=department)

            return queryset

OpenAPI Documentation
~~~~~~~~~~~~~~~~~~~~~

The ``LdapFilterBackend`` automatically generates OpenAPI schema parameters
for documentation. The filter fields are automatically included in the API
documentation with appropriate descriptions and types.

Example Response
~~~~~~~~~~~~~~~~

When using the filter backend, API responses maintain the standard DRF format:

.. code-block:: json

    {
        "count": 2,
        "next": null,
        "previous": null,
        "results": [
            {
                "uid": "john.doe",
                "full_name": "John Doe",
                "mail": ["john.doe@example.com"],
                "employee_number": 12345,
                "employee_type": "staff"
            },
            {
                "uid": "jane.smith",
                "full_name": "Jane Smith",
                "mail": ["jane.smith@example.com"],
                "employee_number": 12346,
                "employee_type": "staff"
            }
        ]
    }
