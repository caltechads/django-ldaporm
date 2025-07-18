Django REST Framework Integration
=================================

LDAP ORM provides integration with Django REST Framework (DRF) through specialized serializers that work with LDAP ORM models and fields.

Overview
--------

The LDAP ORM REST Framework integration provides two main serializers and pagination support:

* **LdapModelSerializer**: Basic serializer for LDAP ORM models
* **HyperlinkedModelSerializer**: Advanced serializer with URL-based identification and hyperlinked relationships
* **LdapCursorPagination**: Server-side LDAP paging for efficient handling of large result sets

Both serializers automatically introspect LDAP ORM fields and provide appropriate DRF field mappings. All list endpoints should use LDAP paging to handle large result sets efficiently.

LdapModelSerializer
-------------------

The ``LdapModelSerializer`` provides basic serialization for LDAP ORM models with automatic field introspection.

Basic Usage
~~~~~~~~~~~

.. code-block:: python

    from ldaporm import fields, models
    from ldaporm.restframework import LdapModelSerializer

    class User(models.Model):
        username = fields.CharField(max_length=50, primary_key=True)
        first_name = fields.CharField(max_length=50)
        last_name = fields.CharField(max_length=50)
        email = fields.EmailField()
        is_active = fields.BooleanField(default=True)

        class Meta:
            object_classes = ['person', 'organizationalPerson', 'inetOrgPerson']

    class UserSerializer(LdapModelSerializer):
        class Meta:
            model = User

Field Type Support
~~~~~~~~~~~~~~~~~~

The serializer automatically maps LDAP ORM field types to appropriate DRF fields:

+------------------------+------------------+----------------------------------+
| LDAP ORM Field         | DRF Field        | Notes                            |
+========================+==================+==================================+
| ``CharField``          | ``CharField``    | Standard string field            |
+------------------------+------------------+----------------------------------+
| ``IntegerField``       | ``IntegerField`` | Integer field                    |
+------------------------+------------------+----------------------------------+
| ``BooleanField``       | ``BooleanField`` | Boolean field                    |
+------------------------+------------------+----------------------------------+
| ``AllCapsBooleanField``| ``BooleanField`` | Boolean field (uppercase LDAP)   |
+------------------------+------------------+----------------------------------+
| ``DateTimeField``      | ``DateTimeField``| DateTime field                   |
+------------------------+------------------+----------------------------------+
| ``ActiveDirectoryTimestampField``| ``DateTimeField``| DateTime field                   |
+------------------------+------------------+----------------------------------+
| ``DateField``          | ``DateField``    | Date field                       |
+------------------------+------------------+----------------------------------+
| ``EmailForwardField``  | ``EmailField``   | Email field with forwarding      |
+------------------------+------------------+----------------------------------+
| ``EmailField``         | ``EmailField``   | Email field with validation      |
+------------------------+------------------+----------------------------------+
| ``CharListField``      | ``ListField``    | List of strings                  |
+------------------------+------------------+----------------------------------+

API Response Format
~~~~~~~~~~~~~~~~~~~

.. code-block:: json

    {
        "username": "john.doe",
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
        "is_active": true,
        "dn": "cn=john.doe,ou=users,dc=example,dc=com"
    }

HyperlinkedModelSerializer
--------------------------

The ``HyperlinkedModelSerializer`` provides URL-based identification and hyperlinked relationships for LDAP ORM models, similar to Django REST Framework's standard ``HyperlinkedModelSerializer``.

Features
~~~~~~~~

* **Automatic URL field**: Adds a ``url`` field that points to the detail view for each instance
* **Hyperlinked relationships**: Converts relationship fields (ending in ``_dn`` or ``_id``) to hyperlinked URLs
* **LDAP ORM field support**: Full support for all LDAP ORM field types
* **Flexible configuration**: Configurable relationship mappings and lookup fields
* **RESTful API design**: Follows REST API best practices with hyperlinked resources

Basic Usage
~~~~~~~~~~~

.. code-block:: python

    from ldaporm import fields, models
    from ldaporm.restframework import HyperlinkedModelSerializer

    class User(models.Model):
        username = fields.CharField(max_length=50, primary_key=True)
        first_name = fields.CharField(max_length=50)
        last_name = fields.CharField(max_length=50)
        email = fields.EmailField()
        department_dn = fields.CharField(max_length=500, blank=True)

        class Meta:
            object_classes = ['person', 'organizationalPerson', 'inetOrgPerson']

    class UserSerializer(HyperlinkedModelSerializer):
        class Meta:
            model = User
            lookup_field = 'dn'

Configuration Options
~~~~~~~~~~~~~~~~~~~~~

Meta Options
^^^^^^^^^^^^

* ``model``: The LDAP ORM model class (required)
* ``lookup_field``: The field to use for URL lookups (defaults to ``'dn'``)
* ``relationship_fields``: List of field names that should be treated as relationships
* ``relationship_models``: Dictionary mapping relationship field names to their model classes
* ``extra_kwargs``: Dictionary for customizing field configuration (view_name, lookup_field, etc.)

Example with Relationships
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    class UserSerializer(HyperlinkedModelSerializer):
        class Meta:
            model = User
            lookup_field = 'dn'
            relationship_fields = ['department_dn', 'manager_dn']
            relationship_models = {
                'department_dn': Department,
                'manager_dn': User,  # Self-referencing relationship
            }

Using extra_kwargs for Custom Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The ``extra_kwargs`` Meta option allows you to customize field configuration, including view names and lookup fields:

.. code-block:: python

    class UserSerializer(HyperlinkedModelSerializer):
        class Meta:
            model = User
            lookup_field = 'dn'
            relationship_fields = ['department_dn', 'manager_dn']
            relationship_models = {
                'department_dn': Department,
                'manager_dn': User,
            }
            extra_kwargs = {
                'url': {
                    'view_name': 'api:user-detail',  # Custom view name for URL field
                    'lookup_field': 'username',      # Use username instead of dn
                },
                'department_dn': {
                    'view_name': 'api:department-detail',  # Custom view name for relationship
                    'lookup_field': 'name',               # Use name instead of dn
                },
                'manager_dn': {
                    'view_name': 'api:user-detail',       # Custom view name for relationship
                    'lookup_field': 'username',           # Use username instead of dn
                }
            }

Relationship Detection
~~~~~~~~~~~~~~~~~~~~~~

The serializer automatically detects relationship fields by:

1. **Field name pattern**: Fields ending in ``_dn`` or ``_id``
2. **Explicit configuration**: Fields listed in ``Meta.relationship_fields``

Automatic Detection
^^^^^^^^^^^^^^^^^^

.. code-block:: python

    class User(models.Model):
        # These will be automatically detected as relationships
        department_dn = fields.CharField(max_length=500)
        manager_id = fields.CharField(max_length=500)

        # This will not be detected as a relationship
        description = fields.CharField(max_length=500)

Explicit Configuration
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    class UserSerializer(HyperlinkedModelSerializer):
        class Meta:
            model = User
            relationship_fields = ['custom_relationship_field']
            relationship_models = {
                'custom_relationship_field': CustomModel,
            }

API Response Format
~~~~~~~~~~~~~~~~~~~

Single Object
^^^^^^^^^^^^^

.. code-block:: json

    {
        "url": "http://example.com/api/users/cn=john.doe,ou=users,dc=example,dc=com/",
        "username": "john.doe",
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
        "department_dn": "http://example.com/api/departments/ou=engineering,dc=example,dc=com/",
        "is_active": true,
        "dn": "cn=john.doe,ou=users,dc=example,dc=com"
    }

List Response (Paged)
^^^^^^^^^^^^^^^^^^^^^

All list responses are automatically paged using LDAP cursor-based pagination:

.. code-block:: json

    {
        "results": [
            {
                "url": "http://example.com/api/users/cn=john.doe,ou=users,dc=example,dc=com/",
                "username": "john.doe",
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@example.com",
                "department_dn": "http://example.com/api/departments/ou=engineering,dc=example,dc=com/",
                "is_active": true,
                "dn": "cn=john.doe,ou=users,dc=example,dc=com"
            },
            {
                "url": "http://example.com/api/users/cn=jane.smith,ou=users,dc=example,dc=com/",
                "username": "jane.smith",
                "first_name": "Jane",
                "last_name": "Smith",
                "email": "jane.smith@example.com",
                "department_dn": "http://example.com/api/departments/ou=engineering,dc=example,dc=com/",
                "is_active": true,
                "dn": "cn=jane.smith,ou=users,dc=example,dc=com"
            }
        ],
        "has_more": true,
        "next": "http://example.com/api/users/?next_token=dGVzdF9jb29raWVfMTIz"
    }

.. note::

    List responses always include pagination metadata. Use the ``next`` URL to
    retrieve subsequent pages, and check ``has_more`` to determine if more
    results are available.

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

The ``LdapCursorPagination`` class provides cursor-based pagination using base64-encoded LDAP cookies:

.. code-block:: python

    from ldaporm.restframework import LdapCursorPagination

    class LdapCursorPagination(BasePagination):
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
^^^^^^^^^^^^^^^

* ``page_size``: Number of results per page (default: 100, max: 1000)
* ``next_token``: Base64-encoded cursor for the next page

.. note::

    The ``page_size`` parameter is automatically preserved in the ``next`` URL, ensuring that subsequent pages maintain the same page size requested by the user.

Example Requests
^^^^^^^^^^^^^^^

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
^^^^^^^^^^^^^^^^^^

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
^^^^^^^^^^^^^

1. **Always use paging**: Configure paging for all list endpoints
2. **Set reasonable page sizes**: Default to 100, allow up to 1000
3. **Handle cursor errors**: Invalid cursors should start from the beginning
4. **Preserve query parameters**: The pagination automatically preserves all query parameters (including ``page_size``, filters, etc.) in the next page URL
5. **Test with large datasets**: Ensure paging works with your expected data volumes

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

.. code-block:: python

    from rest_framework import viewsets
    from ldaporm.restframework import HyperlinkedModelSerializer, LdapCursorPagination

    class UserViewSet(viewsets.ModelViewSet):
        serializer_class = UserSerializer
        pagination_class = LdapCursorPagination
        lookup_field = 'dn'

        def get_queryset(self):
            return User.objects.all()

Advanced Features
-----------------

Custom Field Mapping
~~~~~~~~~~~~~~~~~~~~

You can override the ``_get_drf_field`` method to customize field mapping:

.. code-block:: python

    class CustomUserSerializer(HyperlinkedModelSerializer):
        def _get_drf_field(self, ldap_field):
            if isinstance(ldap_field, fields.CharField) and ldap_field.name == 'custom_field':
                return serializers.CharField(max_length=100, help_text="Custom help text")
            return super()._get_drf_field(ldap_field)

        class Meta:
            model = User
            lookup_field = 'dn'

Custom Relationship Resolution
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Override ``_get_related_model`` for custom relationship resolution:

.. code-block:: python

    class CustomUserSerializer(HyperlinkedModelSerializer):
        def _get_related_model(self, ldap_field):
            # Custom logic to determine related model
            if ldap_field.name == 'custom_relationship':
                return CustomModel
            return super()._get_related_model(ldap_field)

Error Handling
--------------

The serializers gracefully handle various error conditions:

* If a related object cannot be found, the field value is returned as-is (e.g., the DN string)
* If relationship mapping is not configured, fields are treated as regular fields
* Missing or invalid relationship configurations don't break the serializer
* Field validation errors are properly propagated

Best Practices
--------------

1. **Always use LDAP paging**: Configure ``LdapCursorPagination`` for all list endpoints to prevent timeouts and memory issues
2. **Use descriptive field names**: Use ``_dn`` suffix for relationship fields
3. **Configure relationships explicitly**: Use ``Meta.relationship_models`` for clarity
4. **Handle missing relationships**: Implement proper error handling for missing related objects
5. **Use appropriate lookup fields**: Use ``dn`` for LDAP ORM models
6. **Test relationship resolution**: Ensure all relationships can be properly resolved
7. **Use HyperlinkedModelSerializer for RESTful APIs**: Provides better discoverability and navigation
8. **Set reasonable page sizes**: Default to 100, allow up to 1000 for optimal performance
9. **Preserve query parameters**: Ensure filters and other parameters are maintained across pages

Migration from LdapModelSerializer
----------------------------------

To migrate from ``LdapModelSerializer`` to ``HyperlinkedModelSerializer``:

1. Change the base class
2. Configure relationship mappings if needed
3. Update URL patterns to use the new view names

.. code-block:: python

    # Before
    class UserSerializer(LdapModelSerializer):
        class Meta:
            model = User

    # After
    class UserSerializer(HyperlinkedModelSerializer):
        class Meta:
            model = User
            lookup_field = 'dn'
            relationship_fields = ['department_dn']
            relationship_models = {'department_dn': Department}

Complete Example
----------------

Here's a complete example showing both serializers in action:

.. code-block:: python

    from ldaporm import fields, models
    from ldaporm.restframework import LdapModelSerializer, HyperlinkedModelSerializer, LdapCursorPagination

    # LDAP ORM Models
    class Department(models.Model):
        name = fields.CharField(max_length=100)
        description = fields.CharField(max_length=500, blank=True)
        location = fields.CharField(max_length=100, blank=True)

        class Meta:
            object_classes = ['organizationalUnit']

    class User(models.Model):
        username = fields.CharField(max_length=50, primary_key=True)
        first_name = fields.CharField(max_length=50)
        last_name = fields.CharField(max_length=50)
        email = fields.EmailField()
        department_dn = fields.CharField(max_length=500, blank=True)
        manager_dn = fields.CharField(max_length=500, blank=True)
        is_active = fields.BooleanField(default=True)

        class Meta:
            object_classes = ['person', 'organizationalPerson', 'inetOrgPerson']

    # Basic Serializer
    class DepartmentSerializer(LdapModelSerializer):
        class Meta:
            model = Department

    # Hyperlinked Serializer
    class UserSerializer(HyperlinkedModelSerializer):
        class Meta:
            model = User
            lookup_field = 'dn'
            relationship_fields = ['department_dn', 'manager_dn']
            relationship_models = {
                'department_dn': Department,
                'manager_dn': User,
            }
            extra_kwargs = {
                'url': {
                    'view_name': 'api:user-detail',
                    'lookup_field': 'username',
                },
                'department_dn': {
                    'view_name': 'api:department-detail',
                    'lookup_field': 'name',
                },
                'manager_dn': {
                    'view_name': 'api:user-detail',
                    'lookup_field': 'username',
                }
            }

    # ViewSets
    class DepartmentViewSet(viewsets.ModelViewSet):
        serializer_class = DepartmentSerializer
        pagination_class = LdapCursorPagination
        lookup_field = 'dn'

        def get_queryset(self):
            return Department.objects.all()

    class UserViewSet(viewsets.ModelViewSet):
        serializer_class = UserSerializer
        pagination_class = LdapCursorPagination
        lookup_field = 'dn'

        def get_queryset(self):
            return User.objects.all()
