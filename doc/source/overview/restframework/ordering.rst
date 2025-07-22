Django REST Framework: Ordering
===============================

For list endpoints, LDAP ORM provides ordering capabilities for REST framework
views through the ``LdapOrderingFilter`` filter backend. This filter leverages
LDAP ORM's built-in ordering capabilities, which automatically use server-side
sorting when available and fall back to client-side sorting when the LDAP server
doesn't support server-side sorting.   See :ref:`managers_ordering` for more
details on server-side sorting.

Overview
--------

The ``LdapOrderingFilter`` provides:

* **Server-side sorting**: Uses LDAP's server-side sorting when supported
* **Client-side fallback**: Automatically falls back to client-side sorting when needed
* **Field validation**: Validates ordering fields against the LDAP model
* **Multiple field support**: Supports ordering by multiple fields
* **Ascending/descending**: Supports both ascending and descending ordering
* **Default ordering**: Falls back to model's default ordering when no ordering is specified

Basic Usage
-----------

Add the ``LdapOrderingFilter`` to your ViewSet's ``filter_backends``:

.. code-block:: python

    from rest_framework import viewsets
    from ldaporm.restframework import LdapOrderingFilter, LdapCursorPagination
    from your_app.models import YourLdapModel
    from your_app.serializers import YourLdapModelSerializer

    class YourLdapModelViewSet(viewsets.ModelViewSet):
        serializer_class = YourLdapModelSerializer
        pagination_class = LdapCursorPagination
        filter_backends = [LdapOrderingFilter]
        ordering_fields = ['field1', 'field2', 'field3']  # Optional: restrict fields
        ordering = ['field1']  # Default ordering
        lookup_field = 'dn'

        def get_queryset(self):
            return YourLdapModel.objects.all()

Configuration Options
---------------------

ordering_fields
~~~~~~~~~~~~~~~

A list of field names that can be used for ordering. If not specified, all model
fields are allowed.

.. code-block:: python

    class UserViewSet(viewsets.ModelViewSet):
        ordering_fields = ['uid', 'cn', 'mail', 'created']
        # ... rest of configuration

ordering
~~~~~~~~

The default ordering to use when no ordering parameter is provided. This can be
a single field or a list of fields.

.. code-block:: python

    class UserViewSet(viewsets.ModelViewSet):
        ordering = ['uid']  # Single field
        # or
        ordering = ['uid', 'cn']  # Multiple fields

ordering_param
~~~~~~~~~~~~~~

The query parameter name for ordering (default: 'ordering').

.. code-block:: python

    class UserViewSet(viewsets.ModelViewSet):
        filter_backends = [LdapOrderingFilter]

        def get_ordering_param(self):
            return 'sort'  # Use 'sort' instead of 'ordering'

API Usage
---------

Single Field Ordering
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    # Order by field ascending
    GET /api/users/?ordering=uid

    # Order by field descending (use '-' prefix)
    GET /api/users/?ordering=-uid

Multiple Field Ordering
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    # Order by multiple fields
    GET /api/users/?ordering=uid,-cn,mail

    # This orders by:
    # 1. uid ascending
    # 2. cn descending
    # 3. mail ascending

Combining with Other Filters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ordering filter works alongside other filter backends:

.. code-block:: bash

    # Filter + ordering
    GET /api/users/?uid=john&ordering=cn

    # Multiple filters + ordering
    GET /api/users/?uid=john&is_active=true&ordering=-created

Error Handling
--------------

Invalid Field Names
~~~~~~~~~~~~~~~~~~~

If an invalid field name is provided, the API returns a 400 Bad Request with
a clear error message:

.. code-block:: json

    {
        "detail": "Invalid ordering field 'invalid_field'. Available fields: uid, cn, mail, created"
    }

Empty or Invalid Parameters
~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Empty ordering parameter: Uses default ordering
* Invalid field names: Returns 400 with error message
* Malformed parameters: Gracefully handles and ignores invalid parts

Integration Examples
--------------------

With Django Filter
~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from django_filters import rest_framework as filters
    from rest_framework import viewsets
    from ldaporm.restframework import LdapOrderingFilter, LdapCursorPagination

    class UserFilter(filters.FilterSet):
        uid = filters.CharFilter(field_name="uid", lookup_expr="icontains")
        mail = filters.CharFilter(field_name="mail", lookup_expr="icontains")

        class Meta:
            model = User
            fields = ['uid', 'mail']

    class UserViewSet(viewsets.ModelViewSet):
        serializer_class = UserSerializer
        pagination_class = LdapCursorPagination
        filter_backends = [filters.DjangoFilterBackend, LdapOrderingFilter]
        filterset_class = UserFilter
        ordering_fields = ['uid', 'cn', 'mail', 'created']
        ordering = ['uid']
        lookup_field = 'dn'

        def get_queryset(self):
            return User.objects.all()

With Custom Filter Backends
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from rest_framework import viewsets
    from ldaporm.restframework import LdapOrderingFilter

    class CustomFilterBackend(BaseFilterBackend):
        def filter_queryset(self, request, queryset, view):
            # Custom filtering logic
            return queryset

    class UserViewSet(viewsets.ModelViewSet):
        filter_backends = [CustomFilterBackend, LdapOrderingFilter]
        ordering_fields = ['uid', 'cn', 'mail']
        ordering = ['uid']

        def get_queryset(self):
            return User.objects.all()

Performance Considerations
--------------------------

Server-Side Sorting
~~~~~~~~~~~~~~~~~~~

When the LDAP server supports server-side sorting, the ordering is performed
efficiently on the server side. This is the most efficient approach for large
datasets.

Client-Side Sorting
~~~~~~~~~~~~~~~~~~~

When server-side sorting is not available, LDAP ORM automatically falls back
to client-side sorting. This involves:

1. Fetching all results from LDAP
2. Sorting them in Python memory
3. Returning the sorted results

For large datasets, this can be less efficient, but it ensures compatibility
with all LDAP servers.

Pagination with Ordering
~~~~~~~~~~~~~~~~~~~~~~~~

When using ``LdapCursorPagination`` with ordering:

1. The ordering is applied first
2. Then pagination is applied to the ordered results
3. This ensures consistent ordering across pages

.. code-block:: python

    class UserViewSet(viewsets.ModelViewSet):
        pagination_class = LdapCursorPagination
        filter_backends = [LdapOrderingFilter]
        ordering_fields = ['uid', 'cn', 'mail']
        ordering = ['uid']

        def get_queryset(self):
            return User.objects.all()

Best Practices
--------------

1. **Always specify ordering_fields**: Restrict ordering to fields that make
   sense for your use case and have good performance characteristics.

2. **Use server-side sorting when possible**: The filter automatically uses
   server-side sorting when available, which is more efficient.

3. **Combine with pagination**: Always use pagination (like ``LdapCursorPagination``)
   when dealing with potentially large result sets.

4. **Test with your LDAP server**: Different LDAP servers have different
   capabilities. Test ordering with your specific LDAP server to understand
   performance characteristics.

5. **Monitor performance**: For large datasets, monitor the performance of
   ordering operations, especially when client-side sorting is used.

6. **Provide meaningful defaults**: Set a sensible default ordering that
   matches user expectations.

Example Complete Implementation
-------------------------------

.. code-block:: python

    from ldaporm import fields, models
    from ldaporm.restframework import (
        LdapModelSerializer, LdapOrderingFilter, LdapCursorPagination, LdapFilterBackend
    )
    from rest_framework import viewsets

    # LDAP ORM Model
    class User(models.Model):
        uid = fields.CharField(max_length=50, primary_key=True)
        cn = fields.CharField(max_length=100)
        mail = fields.EmailField()
        created = fields.DateTimeField(auto_now_add=True)
        is_active = fields.BooleanField(default=True)

        class Meta:
            object_classes = ['person', 'organizationalPerson', 'inetOrgPerson']
            ordering = ['uid']  # Default ordering

    # Custom Filter Backend
    class UserFilterBackend(LdapFilterBackend):
        filter_fields = {
            'uid': {'lookup': 'icontains'},
            'cn': {'lookup': 'icontains'},
            'mail': {'lookup': 'icontains'},
            'is_active': {'lookup': 'exact'},
        }

    # Serializer
    class UserSerializer(LdapModelSerializer):
        class Meta:
            model = User

    # ViewSet
    class UserViewSet(viewsets.ModelViewSet):
        serializer_class = UserSerializer
        pagination_class = LdapCursorPagination
        filter_backends = [UserFilterBackend, LdapOrderingFilter]
        ordering_fields = ['uid', 'cn', 'mail', 'created', 'is_active']
        ordering = ['uid']  # Default ordering
        lookup_field = 'dn'

        def get_queryset(self):
            return User.objects.all()

    # URL Configuration
    from django.urls import path, include
    from rest_framework.routers import DefaultRouter

    router = DefaultRouter()
    router.register(r'users', UserViewSet, basename='user')

    urlpatterns = [
        path('api/', include(router.urls)),
    ]

This implementation provides:

- Full CRUD operations for LDAP users
- Filtering by uid, cn, mail, and is_active using a custom UserFilterBackend
- Ordering by any of the specified fields
- Pagination with cursor-based navigation
- Server-side sorting when available
- Proper error handling for invalid ordering fields