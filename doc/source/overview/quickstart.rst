Quickstart Guide
================

This guide will walk you through setting up django-ldaporm in your Django project
and creating your first LDAP model. For detailed installation instructions and
advanced configuration options, see the :doc:`installation guide <installation>`
and :doc:`configuration guide <configuration>`.

Installation
------------

Install django-ldaporm using pip:

.. code-block:: bash

   pip install django-ldaporm

Add ``django-ldaporm`` to ``INSTALLED_APPS`` in your Django settings:

.. code-block:: python

   INSTALLED_APPS = [
       # ... your other apps
       'ldaporm',
   ]

Configuration
-------------

Configure your LDAP servers in your Django settings. For complete configuration
options, see the :doc:`configuration guide <configuration>`.

.. code-block:: python

   LDAP_SERVERS = {
       'default': {
           'basedn': 'dc=example,dc=com',
           'read': {
               'url': 'ldap://ldapslave.example.com',
               'user': 'cn=admin,dc=example,dc=com',
               'password': 'your-password',
            },
            'write': {
                'url': 'ldaps://ldapmaster.example.com:636',
                'user': 'cn=admin,dc=example,dc=com',
                'password': 'your-password',
            }
       }
   }

Creating Your First Model
-------------------------

Create a model for LDAP users:

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import CharField, EmailField, BooleanField, DateTimeField

   class LDAPUser(Model):
       # Define fields that map to LDAP attributes
       uid = CharField('uid', primary_key=True, max_length=50)
       cn = CharField('cn', max_length=100)
       sn = CharField('sn', max_length=100)
       givenName = CharField('givenName', max_length=100)
       mail = EmailField('mail', max_length=254)
       telephoneNumber = CharField('telephoneNumber', max_length=20, blank=True)
       is_active = BooleanField('userAccountControl', default=True)
       created = DateTimeField('whenCreated', auto_now_add=True)
       modified = DateTimeField('whenChanged', auto_now=True)

       class Meta:
           ldap_server = 'default'
           basedn = 'ou=users,dc=example,dc=com'
           objectclass = 'person'
           objectclasses = ['inetOrgPerson', 'organizationalPerson']
           verbose_name = 'LDAP User'
           verbose_name_plural = 'LDAP Users'

For detailed model configuration options, see :doc:`models`.

Basic Usage
-----------

Query LDAP users:

.. code-block:: python

   # Get all users
   users = LDAPUser.objects.all()

   # Filter users
   active_users = LDAPUser.objects.filter(is_active=True)
   admin_users = LDAPUser.objects.filter(cn__icontains='admin')

   # Get a specific user
   user = LDAPUser.objects.get(uid='john.doe')

   # Create a new user
   new_user = LDAPUser(
       uid='jane.smith',
       cn='Jane Smith',
       sn='Smith',
       givenName='Jane',
       mail='jane.smith@example.com'
   )
   new_user.save()

   # Update a user
   user.telephoneNumber = '+1-555-123-4567'
   user.save()

   # Delete a user
   user.delete()

For advanced querying options, see :doc:`managers`.

Using with Django Forms
-----------------------

Create a form for your LDAP model:

.. code-block:: python

   from django import forms
   from .models import LDAPUser

   class LDAPUserForm(forms.ModelForm):
       class Meta:
           model = LDAPUser
           fields = ['uid', 'cn', 'sn', 'givenName', 'mail', 'telephoneNumber']

Use the form in a view:

.. code-block:: python

   from django.shortcuts import render, redirect
   from django.views.generic import CreateView, UpdateView
   from .models import LDAPUser
   from .forms import LDAPUserForm

   class LDAPUserCreateView(CreateView):
       model = LDAPUser
       form_class = LDAPUserForm
       template_name = 'ldap_users/create.html'
       success_url = '/users/'

   class LDAPUserUpdateView(UpdateView):
       model = LDAPUser
       form_class = LDAPUserForm
       template_name = 'ldap_users/update.html'
       success_url = '/users/'

   def user_list(request):
       users = LDAPUser.objects.all()
       return render(request, 'ldap_users/list.html', {'users': users})

Using with Django Admin
-----------------------

Register your model with Django admin using the ldaporm admin integration:

.. code-block:: python

   from ldaporm.admin import register_ldap_model, LdapUserAdmin
   from .models import LDAPUser

   # Register with default admin class
   register_ldap_model(LDAPUser)

   # Or register with specialized user admin class
   register_ldap_model(LDAPUser, LdapUserAdmin)

   # Or create a custom admin class
   class CustomUserAdmin(LdapUserAdmin):
       list_display = ['uid', 'cn', 'sn', 'mail', 'is_active']
       list_filter = ['is_active']
       search_fields = ['uid', 'cn', 'sn', 'mail']
       readonly_fields = ['uidNumber']

   register_ldap_model(LDAPUser, CustomUserAdmin)

The admin integration provides automatic field conversion, LDAP validation, and full Django Admin functionality. You can mix Django ORM models and LDAP ORM models in the same admin interface. See :doc:`/admin` for complete documentation.

Advanced Features
-----------------

Active Directory Timestamps
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For Active Directory environments, use the specialized timestamp field:

.. code-block:: python

   from ldaporm.fields import ActiveDirectoryTimestampField

   class ADUser(LDAPUser):
       last_logon = ActiveDirectoryTimestampField('lastLogon', null=True)
       pwd_last_set = ActiveDirectoryTimestampField('pwdLastSet', null=True)

       class Meta:
           objectclass = 'user'

Multi-valued Attributes
^^^^^^^^^^^^^^^^^^^^^^^

Handle multi-valued LDAP attributes:

.. code-block:: python

   from ldaporm.fields import CharListField

   class LDAPGroup(Model):
       cn = CharField('cn', primary_key=True, max_length=50)
       description = CharField('description', max_length=200, blank=True)
       member = CharListField('member', max_length=100)

       class Meta:
           ldap_server = 'default'
           basedn = 'ou=groups,dc=example,dc=com'
           objectclass = 'groupOfNames'

For complete field documentation, see :doc:`../api/fields`.

Next Steps
----------

* Read the :doc:`installation guide <installation>` for detailed setup instructions
* Explore the :doc:`models guide <models>` for advanced model configuration
* Check out the :doc:`fields guide <fields>` for available field types and usage patterns
* See the :doc:`managers guide <managers>` for querying and filtering options
* Learn about :doc:`/admin` for Django Admin integration
* Review the :doc:`../api/fields` for complete field API reference