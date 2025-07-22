django-wildewidgets Integration
===============================

LDAP ORM provides integration with `django-wildewidgets
<https://github.com/caltechads/django-wildewidgets>`_ through the
``LdapModelTableMixin``, which enables the use of wildewidgets tables with LDAP
ORM models.

Overview
--------

The ``LdapModelTableMixin`` makes :py:class:`~wildewidgets.BasicModelTable` work
with :py:class:`ldaporm.models.Model` by providing:

* **LDAP-aware search**: Global search across multiple LDAP attributes
* **Query building**: Proper construction of LDAP ORM query objects
* **Column filtering**: Support for filtering on specific LDAP attributes
* **Integration**: Seamless integration with wildewidgets table components

Basic Usage
-----------

To use the mixin, simply add ``LdapModelTableMixin`` before
``BasicModelTable`` in your table class inheritance list:

.. code-block:: python

    from wildewidgets import BasicModelTable
    from ldaporm.wildewidgets import LdapModelTableMixin
    from ldaporm import fields, models

    # Define your LDAP ORM model
    class LDAPUser(models.Model):

        EMPLOYEE_TYPE_CHOICES = [
            ('manager', 'Manager'),
            ('developer', 'Developer'),
            ('admin', 'Admin'),
        ]

        username = fields.CharField(max_length=50, primary_key=True)
        first_name = fields.CharField(max_length=50)
        last_name = fields.CharField(max_length=50)
        email = fields.EmailField()
        is_active = fields.BooleanField(default=True)
        employee_type = fields.CharField(max_length=50)

        class Meta:
            object_classes = ['top','person', 'organizationalPerson', 'inetOrgPerson']
            ...

    # Create a table with the mixin
    class LDAPUserTable(LdapModelTableMixin, BasicModelTable):
        model = LDAPUser
        page_length = 25
        striped = True
        fields: ClassVar[list[str]] = ['username', 'first_name', 'last_name', 'email', 'is_active', 'employee_type']
        verbose_names: ClassVar[dict[str, str]] = {
            'username': 'Username',
            'first_name': 'First Name',
            'last_name': 'Last Name',
            'email': 'Email',
            'is_active': 'Active',
        }
        hidden: ClassVar[list[str]] = ['employee_type']

        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            employee_type = DataTableFilter(
                header="Employee Type",
            )
            for choice in LDAPUser.EMPLOYEE_TYPE_CHOICES:
                employee_type.add_choice(choice[1], choice[0])
            self.add_filter("employee_type", employee_type)

        def get_initial_queryset(self) -> F:
            return cast("LdapManager", self.model.objects).order_by("username")


Configuration Options
---------------------

See :py:class:`~wildewidgets.BasicModelTable` for more information on the
configuration options.  The table will allow you to proceed normally as through
you had a Django Model.  The only difference is that you need to use the
``LdapModelTableMixin`` before ``BasicModelTable`` in your table class
inheritance list.

Complete Example
----------------

Here's a complete example showing all features:

.. code-block:: python

    from wildewidgets import BasicModelTable, Column
    from ldaporm.wildewidgets import LdapModelTableMixin
    from ldaporm import fields, models
    from django.views.generic import ListView

    # LDAP ORM Model
    class Department(models.Model):
        name = fields.CharField(max_length=100)
        description = fields.CharField(max_length=500, blank=True)
        location = fields.CharField(max_length=100, blank=True)
        is_active = fields.BooleanField(default=True)

        class Meta:
            object_classes = ['organizationalUnit']
            ...

    class User(models.Model):
        username = fields.CharField(max_length=50, primary_key=True)
        first_name = fields.CharField(max_length=50)
        last_name = fields.CharField(max_length=50)
        email = fields.EmailField()
        employee_id = fields.IntegerField(blank=True, null=True)
        department_dn = fields.CharField(max_length=500, blank=True)
        is_active = fields.BooleanField(default=True)
        created = fields.DateTimeField(auto_now_add=True)

        class Meta:
            object_classes = ['person', 'organizationalPerson', 'inetOrgPerson']
            ...

    # Department Table
    class DepartmentTable(LdapModelTableMixin, BasicModelTable):
        model = Department
        page_length = 25
        striped = True
        fields: ClassVar[list[str]] = ['name', 'description', 'location', 'is_active']
        verbose_names: ClassVar[dict[str, str]] = {
            'name': 'Name',
            'description': 'Description',
            'location': 'Location',
            'is_active': 'Active',
        }

        def get_initial_queryset(self) -> F:
            return cast("LdapManager", self.model.objects).order_by("name")

    # User Table with Advanced Features
    class UserTable(LdapModelTableMixin, BasicModelTable):
        model = User
        page_length = 25
        striped = True
        fields: ClassVar[list[str]] = ['username', 'first_name', 'last_name', 'email', 'is_active', 'employee_id']
        verbose_names: ClassVar[dict[str, str]] = {
            'username': 'Username',
            'first_name': 'First Name',
            'last_name': 'Last Name',
            'email': 'Email',
            'is_active': 'Active',
            'employee_id': 'Employee ID',
        }
        hidden: ClassVar[list[str]] = ['employee_id']

        def get_initial_queryset(self) -> F:
            return cast("LdapManager", self.model.objects).order_by("username")


Performance Considerations
--------------------------

* **Server-side filtering**: The mixin leverages LDAP server-side filtering when possible
* **Query optimization**: Use appropriate LDAP filters to minimize data transfer
* **Caching**: Consider caching frequently accessed LDAP data
* **Pagination**: Use wildewidgets pagination features for large datasets
* **Indexing**: Ensure your LDAP server has appropriate indexes for searched attributes

Error Handling
--------------

The mixin handles common LDAP errors gracefully:

* **Connection errors**: Displays appropriate error messages
* **Invalid queries**: Validates query parameters before execution
* **Missing attributes**: Handles cases where LDAP attributes are not present
* **Permission errors**: Shows appropriate messages for access denied scenarios
