Django REST Framework: Paging
=============================

For list endpoints, LDAP ORM provides integration with Django REST Framework
(DRF) through specialized pagination support that work with LDAP ORM models and
fields.

* **LdapCursorPagination**: Server-side LDAP paging for efficient handling of large result sets

LDAP Paging
-----------

LDAP ORM provides server-side paging through ``LdapCursorPagination``, which
uses LDAP's ``SimplePagedResultsControl`` for efficient handling of large result
sets.

Why Use LDAP Paging?
~~~~~~~~~~~~~~~~~~~~

* **Prevents timeouts**: Large LDAP queries can cause client or server timeouts
* **Memory efficiency**: Avoids loading entire result sets into memory
* **Server-side processing**: Leverages LDAP server's native paging capabilities
* **Unindexed attributes**: Efficient for queries on unindexed attributes
* **Scalability**: Handles result sets of any size

LdapCursorPagination
~~~~~~~~~~~~~~~~~~~~

The ``LdapCursorPagination`` class provides cursor-based pagination using
base64-encoded LDAP cookies:

.. code-block:: python

    from ldaporm.restframework import LdapCursorPagination

    class MyLdapCursorPagination(LdapCursorPagination):
        page_size = 100                    # Default page size
        page_size_query_param = 'page_size' # Query parameter for page size
        max_page_size = 1000               # Maximum allowed page size
        cursor_query_param = 'next_token'  # Query parameter for next page cursor

Basic Usage
^^^^^^^^^^^

.. code-block:: python

    from rest_framework import viewsets
    from ldaporm.restframework import LdapCursorPagination

    class UserViewSet(viewsets.ModelViewSet):
        serializer_class = UserSerializer
        pagination_class = LdapCursorPagination
        lookup_field = 'dn'

        def get_queryset(self):
            return User.objects.all()

Global Configuration
^^^^^^^^^^^^^^^^^^^^

You can configure LDAP paging globally in your Django settings:

.. code-block:: python

    REST_FRAMEWORK = {
        'DEFAULT_PAGINATION_CLASS': 'ldaporm.restframework.LdapCursorPagination',
        'PAGE_SIZE': 100,
    }

API Response Format
^^^^^^^^^^^^^^^^^^^

.. code-block:: json

    {
        "results": [
            {
                "url": "http://example.com/api/users/cn=john.doe,ou=users,dc=example,dc=com/",
                "username": "john.doe",
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com",
                "is_active": true,
                "dn": "cn=john.doe,ou=users,dc=example,dc=com"
            },
            {
                "url": "http://example.com/api/users/cn=jane.smith,ou=users,dc=example,dc=com/",
                "username": "jane.smith",
                "first_name": "Jane",
                "last_name": "Smith",
                "email": "jane.smith@example.com",
                "is_active": true,
                "dn": "cn=jane.smith,ou=users,dc=example,dc=com"
            }
        ],
        "has_more": true,
        "next": "http://example.com/api/users/?next_token=dGVzdF9jb29raWVfMTIz"
    }

Query Parameters
^^^^^^^^^^^^^^^^

* ``page_size``: Number of results per page (default: 100, max: 1000)
* ``next_token``: Base64-encoded cursor for the next page.  You don't need to
  pass this parameter on the first page.

.. note::

    The ``page_size`` parameter is automatically preserved in the ``next`` URL,
    ensuring that subsequent pages maintain the same page size requested by the
    user.

Example Requests
^^^^^^^^^^^^^^^^

.. code-block:: bash

    # First page
    GET /api/users/

    # Next page
    GET /api/users/?next_token=dGVzdF9jb29raWVfMTIz

    # Custom page size
    GET /api/users/?page_size=50

    # Next page with custom size
    GET /api/users/?page_size=50&next_token=dGVzdF9jb29raWVfMTIz

Paging with Filters
^^^^^^^^^^^^^^^^^^^

LDAP paging works seamlessly with filters and other query parameters:

.. code-block:: python

    class UserViewSet(viewsets.ModelViewSet):
        serializer_class = UserSerializer
        pagination_class = LdapCursorPagination
        lookup_field = 'dn'

        def get_queryset(self):
            queryset = User.objects.all()

            # Apply filters
            is_active = self.request.query_params.get('is_active')
            if is_active is not None:
                queryset = queryset.filter(is_active=is_active.lower() == 'true')

            return queryset

.. code-block:: bash

    # Filtered and paged request
    GET /api/users/?is_active=true&page_size=25

    # Next page of filtered results
    GET /api/users/?is_active=true&page_size=25&next_token=dGVzdF9jb29raWVfMTIz

Best Practices
^^^^^^^^^^^^^^

1. **Always use paging**: Configure paging for all list endpoints
2. **Set reasonable page sizes**: Default to 100, allow up to 1000
3. **Handle cursor errors**: Invalid cursors should start from the beginning
4. **Preserve query parameters**: The pagination automatically preserves all query parameters (including ``page_size``, filters, etc.) in the next page URL
5. **Test with large datasets**: Ensure paging works with your expected data volumes
