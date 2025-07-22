Django REST Framework: Serializers
==================================

The LDAP ORM REST Framework integration provides two main serializers:

* **LdapModelSerializer**: Basic serializer for LDAP ORM models
* **HyperlinkedModelSerializer**: Advanced serializer with URL-based identification and hyperlinked relationships

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

The serializer automatically maps LDAP ORM field types to appropriate DRF fields.

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

The ``HyperlinkedModelSerializer`` provides URL-based identification and
hyperlinked relationships for LDAP ORM models, similar to Django REST
Framework's standard ``HyperlinkedModelSerializer``.

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
^^^^^^^^^^^^^^^^^^^

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