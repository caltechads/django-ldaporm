# LDAP ORM Django REST Framework Integration

This example demonstrates how to use `ldaporm` models with Django REST Framework (DRF) for building REST APIs.

## Overview

The integration provides:
- `LdapModelSerializer`: A custom serializer that works with `ldaporm.Model` subclasses
- ViewSet examples using `GenericViewSet`
- APIView examples for individual endpoints
- Complete CRUD operations for LDAP objects

## Files Structure

```
api/
├── serializers.py      # LdapModelSerializer subclasses for each model
├── views/
│   ├── users.py        # LDAPUserViewSet - ViewSet example
│   ├── groups.py       # LDAPGroupViewSet - ViewSet example
│   ├── roles.py        # NSRoleViewSet - ViewSet example
│   └── simple.py       # APIView examples
├── urls.py             # URL routing configuration
└── README.md           # This file
```

## Usage Examples

### 1. Using ViewSets (Recommended)

ViewSets provide full CRUD operations with minimal code:

```python
from rest_framework import viewsets
from api.serializers import LDAPUserSerializer
from core.ldap.models import LDAPUser

class LDAPUserViewSet(viewsets.GenericViewSet):
    serializer_class = LDAPUserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return LDAPUser.objects.all()

    def get_object(self):
        uid = self.kwargs.get('pk')
        return LDAPUser.objects.get(uid=uid)

    # DRF will automatically handle list, retrieve, create, update, destroy
```

### 2. Using APIViews

For more control over individual endpoints:

```python
from rest_framework.views import APIView
from api.serializers import LDAPUserSerializer

class LDAPUserListAPIView(APIView):
    def get(self, request):
        users = LDAPUser.objects.all()
        serializer = LDAPUserSerializer(users, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = LDAPUserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)
```

### 3. Creating Serializers

Subclass `LdapModelSerializer` and specify your model:

```python
from ldaporm.restframework import LdapModelSerializer

class LDAPUserSerializer(LdapModelSerializer):
    class Meta:
        model = LDAPUser
        fields = ['uid', 'full_name', 'mail', 'uid_number']
```

## API Endpoints

When using the ViewSets with the provided URL configuration:

### Users
- `GET /api/users/` - List all users
- `POST /api/users/` - Create a new user
- `GET /api/users/{uid}/` - Get specific user
- `PUT /api/users/{uid}/` - Update user
- `DELETE /api/users/{uid}/` - Delete user
- `GET /api/users/{uid}/full_name/` - Get user's full name

### Groups
- `GET /api/groups/` - List all groups
- `POST /api/groups/` - Create a new group
- `GET /api/groups/{cn}/` - Get specific group
- `PUT /api/groups/{cn}/` - Update group
- `DELETE /api/groups/{cn}/` - Delete group
- `GET /api/groups/{cn}/member_count/` - Get member count

### Roles
- `GET /api/roles/` - List all roles
- `POST /api/roles/` - Create a new role
- `GET /api/roles/{cn}/` - Get specific role
- `PUT /api/roles/{cn}/` - Update role
- `DELETE /api/roles/{cn}/` - Delete role

## Key Features

1. **Automatic Field Introspection**: The serializer automatically maps `ldaporm` fields to DRF fields
2. **CRUD Operations**: Full create, read, update, delete support
3. **Error Handling**: Proper HTTP status codes and error responses
4. **Custom Actions**: Additional endpoints for model-specific operations
5. **Authentication**: Built-in permission classes support

## Requirements

- Django REST Framework 3.16.0+
- ldaporm 1.1.1+
- Python 3.10+

## Notes

- The `LdapModelSerializer` automatically handles field mapping from `ldaporm` to DRF
- ViewSets provide the most Django-like experience
- APIViews offer more control for custom endpoints
- All operations use the underlying `ldaporm` manager for LDAP operations