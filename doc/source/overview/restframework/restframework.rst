Django REST Framework Integration
=================================

LDAP ORM provides integration with Django REST Framework (DRF) through
specialized serializers, pagination, and ordering support that work with LDAP
ORM models and fields.

Overview
--------

The LDAP ORM REST Framework integration provides two main serializers, pagination, and ordering support:

* **LdapModelSerializer**: Basic serializer for LDAP ORM models
* **HyperlinkedModelSerializer**: Advanced serializer with URL-based identification and hyperlinked relationships
* **LdapCursorPagination**: Server-side LDAP paging for efficient handling of large result sets
* **LdapOrderingFilter**: Filter backend for ordering LDAP ORM models

Both serializers automatically introspect LDAP ORM fields and provide
appropriate DRF field mappings. All list endpoints should use LDAP paging to
handle large result sets efficiently, and ordering should be used when
appropriate.

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

Complete Example
----------------

Here's a complete example showing all LDAP ORM REST Framework components in action:

.. code-block:: python

    from ldaporm import fields, models
    from ldaporm.restframework import (
        LdapModelSerializer, HyperlinkedModelSerializer, LdapCursorPagination,
        LdapFilterBackend, LdapOrderingFilter
    )
    from rest_framework import viewsets

    # LDAP ORM Models
    class Department(models.Model):
        name = fields.CharField(max_length=100)
        description = fields.CharField(max_length=500, blank=True)
        location = fields.CharField(max_length=100, blank=True)
        created = fields.DateTimeField(auto_now_add=True)
        is_active = fields.BooleanField(default=True)

        class Meta:
            object_classes = ['organizationalUnit']
            ordering = ['name']

    class User(models.Model):
        username = fields.CharField(max_length=50, primary_key=True)
        first_name = fields.CharField(max_length=50)
        last_name = fields.CharField(max_length=50)
        email = fields.EmailField()
        employee_id = fields.IntegerField(blank=True, null=True)
        salary = fields.FloatField(blank=True, null=True)
        hire_date = fields.DateField(blank=True, null=True)
        department_dn = fields.CharField(max_length=500, blank=True)
        manager_dn = fields.CharField(max_length=500, blank=True)
        is_active = fields.BooleanField(default=True)
        created = fields.DateTimeField(auto_now_add=True)
        photo = fields.BinaryField(blank=True)
        certificate = fields.BinaryField(blank=True)
        email_list = fields.CharListField(max_length=100, blank=True)
        password_hash = fields.CaseInsensitiveSHA1Field(blank=True)
        ldap_password = fields.LDAPPasswordField(blank=True)
        ad_password = fields.ADPasswordField(blank=True)
        email_forward = fields.EmailForwardField(blank=True)

        class Meta:
            object_classes = ['person', 'organizationalPerson', 'inetOrgPerson']
            ordering = ['username']

    # Custom Filter Backends
    class DepartmentFilterBackend(LdapFilterBackend):
        filter_fields = {
            'name': {'lookup': 'icontains'},
            'description': {'lookup': 'icontains'},
            'location': {'lookup': 'icontains'},
            'is_active': {'lookup': 'exact'},
            'created': {'lookup': 'gte', 'type': 'date'},
        }

    class UserFilterBackend(LdapFilterBackend):
        filter_fields = {
            'username': {'lookup': 'icontains'},
            'first_name': {'lookup': 'icontains'},
            'last_name': {'lookup': 'icontains'},
            'email': {'lookup': 'icontains'},
            'employee_id': {'lookup': 'exact', 'type': 'integer'},
            'salary': {'lookup': 'gte', 'type': 'float'},
            'hire_date': {'lookup': 'gte', 'type': 'date'},
            'is_active': {'lookup': 'exact', 'type': 'boolean'},
            'created': {'lookup': 'gte', 'type': 'date'},
            'photo': {'lookup': 'exact', 'type': 'binary'},
            'certificate': {'lookup': 'exact', 'type': 'binary'},
        }

    # Basic Serializer
    class DepartmentSerializer(LdapModelSerializer):
        class Meta:
            model = Department

    # Hyperlinked Serializer with all field types
    class UserSerializer(HyperlinkedModelSerializer):
        class Meta:
            model = User
            lookup_field = 'username'
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

    # ViewSets with all components
    class DepartmentViewSet(viewsets.ModelViewSet):
        serializer_class = DepartmentSerializer
        pagination_class = LdapCursorPagination
        filter_backends = [DepartmentFilterBackend, LdapOrderingFilter]
        ordering_fields = ['name', 'description', 'location', 'created', 'is_active']
        ordering = ['name']  # Default ordering
        lookup_field = 'dn'

        def get_queryset(self):
            return Department.objects.all()

    class UserViewSet(viewsets.ModelViewSet):
        serializer_class = UserSerializer
        pagination_class = LdapCursorPagination
        filter_backends = [UserFilterBackend, LdapOrderingFilter]
        ordering_fields = [
            'username', 'first_name', 'last_name', 'email', 'employee_id',
            'salary', 'hire_date', 'created', 'is_active'
        ]
        ordering = ['username']  # Default ordering
        lookup_field = 'dn'

        def get_queryset(self):
            return User.objects.all()

    # URL Configuration
    from django.urls import path, include
    from rest_framework.routers import DefaultRouter

    router = DefaultRouter()
    router.register(r'departments', DepartmentViewSet, basename='department')
    router.register(r'users', UserViewSet, basename='user')

    urlpatterns = [
        path('api/', include(router.urls)),
    ]
