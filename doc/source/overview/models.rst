Models Guide
============

This guide covers creating and working with LDAP models in django-ldaporm.

Creating LDAP Models
--------------------

LDAP models are similar to Django ORM models but represent LDAP object classes:

Models must:

* Inherit from :py:class:`~ldaporm.models.Model`
* Define a :py:class:`~ldaporm.models.Meta` class as inside itself
* Define fields as class attributes using :py:class:`~ldaporm.fields.Field`

The ``Meta`` class is used to configure the model.  It is a subclass of
:py:class:`~django.db.models.options.Options`.  See :doc:`/api/options` for
more information about how the ``Meta`` class informs your model.

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import CharField, EmailField, BooleanField

   class LDAPUser(Model):
       uid = CharField('uid', primary_key=True, max_length=50)
       cn = CharField('cn', max_length=100)
       sn = CharField('sn', max_length=100)
       givenName = CharField('givenName', max_length=100)
       mail = EmailField('mail', max_length=254)
       is_active = BooleanField('userAccountControl', default=True)

       class Meta:
           ldap_server = 'default'
           basedn = 'ou=users,dc=example,dc=com'
           objectclass = 'person'
           extra_objectclasses = ['inetOrgPerson', 'organizationalPerson']
           verbose_name = 'LDAP User'
           verbose_name_plural = 'LDAP Users'

Model Meta Options
------------------

The ``Meta`` class configures how the model interacts with LDAP.   See :py:class:`~ldaporm.options.Options` for more information about all the options that can be set here

.. code-block:: python

   class Meta:
       # LDAP server configuration
       ldap_server = 'default'  # Server name from LDAP_SERVERS
       # The base DN for searches.  If not provided, we'll use the basedn from
       # the LDAP_SERVERS configuration.
       basedn = 'ou=users,dc=example,dc=com'  # Base DN for searches
       objectclass = 'person'  # LDAP object class
       # LDAP object classes that will be added to the object when it is created
       # in addition to the objectclass.
       extra_objectclasses = ['inetOrgPerson', 'organizationalPerson']
       # Extra options used to confuigure this model
       ldap_options = ['paged_search']
       # Django admin options
       verbose_name = 'LDAP User'
       verbose_name_plural = 'LDAP Users'

       # Ordering
       ordering = ['cn']  # Default ordering


Field Types
-----------

``django-ldaporm`` provides field types that map Python types to LDAP attributes:
See :doc:`/overview/fields` for more information about the field types.

Basic Fields
^^^^^^^^^^^^

.. code-block:: python

   from ldaporm.fields import (
       CharField, EmailField, BooleanField, IntegerField,
       DateTimeField, DateField, BinaryField
   )

   class User(Model):
       # String fields
       uid = CharField('uid', primary_key=True, max_length=50)
       cn = CharField('cn', max_length=100)
       description = CharField('description', max_length=200, blank=True)

       # Email field
       mail = EmailField('mail', max_length=254)

       # Boolean field
       is_active = BooleanField('userAccountControl', default=True)

       # Integer field
       uidNumber = IntegerField('uidNumber', null=True)

       # Date/time fields
       created = DateTimeField('whenCreated', auto_now_add=True)
       modified = DateTimeField('whenChanged', auto_now=True)
       birthDate = DateField('birthDate', null=True)

       # Binary field
       photo = BinaryField('jpegPhoto', null=True)

Multi-valued Fields
^^^^^^^^^^^^^^^^^^^

Handle LDAP attributes that can have multiple values:

.. code-block:: python

   from ldaporm.fields import CharListField, IntegerListField

   class Group(Model):
       cn = CharField('cn', primary_key=True, max_length=50)

       # Multi-valued string attributes
       member = CharListField('member', max_length=100)
       memberUid = CharListField('memberUid', max_length=50)

       # Multi-valued integer attributes
       gidNumber = IntegerListField('gidNumber')

       class Meta:
          ldap_server = 'default'
          basedn = 'ou=groups,dc=example,dc=com'
          objectclass = 'groupOfNames'
          ldap_options = ['paged_search']
          verbose_name = 'LDAP Group'
          verbose_name_plural = 'LDAP Groups'
          ordering = ['cn']

Active Directory Fields
^^^^^^^^^^^^^^^^^^^^^^^

Special fields for Active Directory environments:

.. code-block:: python

   from ldaporm.fields import ActiveDirectoryTimestampField

   class ADUser(Model):
       sAMAccountName = CharField('sAMAccountName', primary_key=True, max_length=50)
       cn = CharField('cn', max_length=100)

       # AD timestamp fields
       lastLogon = ActiveDirectoryTimestampField('lastLogon', null=True)
       pwdLastSet = ActiveDirectoryTimestampField('pwdLastSet', null=True)
       accountExpires = ActiveDirectoryTimestampField('accountExpires', null=True)

       class Meta:
          ldap_server = 'default'
          basedn = 'ou=users,dc=example,dc=com'
          objectclass = 'person'
          ldap_options = ['paged_search']
          verbose_name = 'Person'
          verbose_name_plural = 'People'
          ordering = ['sAMAccountName']
          userid_attribute = 'sAMAccountName'
          password_attribute = 'unicodePwd'

Field Options
-------------

Field Configuration
^^^^^^^^^^^^^^^^^^^

Configure field behavior.  Fields mostly take all the same arguments as Django's
:py:class:`~django.db.models.Field`.  See :py:class:`~ldaporm.fields.Field` for
more information.  Subclasses of :py:class:`~ldaporm.fields.Field` can take
additional arguments, so see :doc:`/api/fields` for more information.

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import CharField, BooleanField, DateTimeField

   class User(Model):
       # Primary key field
       uid = CharField('uid', primary_key=True, max_length=50)

       # Required field
       cn = CharField('cn', max_length=100)  # Required by default

       # Optional field
       telephoneNumber = CharField('telephoneNumber', max_length=20, blank=True)

       # Nullable field
       description = CharField('description', max_length=200, null=True)

       # Field with default value
       is_active = BooleanField('userAccountControl', default=True)

       # Auto-managed fields
       created = DateTimeField('whenCreated', auto_now_add=True)
       modified = DateTimeField('whenChanged', auto_now=True)

Field Validation
^^^^^^^^^^^^^^^^

Add custom validation:

.. code-block:: python


   from ldaporm import Model
   from ldaporm.fields import CharField
   from django.core.exceptions import ValidationError

   def validate_uid_format(value):
       if not value.isalnum():
           raise ValidationError('UID must be alphanumeric')

   class User(Model):
       uid = CharField(
           'uid',
           primary_key=True,
           max_length=50,
           validators=[validate_uid_format]
       )

Model Methods
-------------

Custom Methods
^^^^^^^^^^^^^^

Add custom methods to your models:

.. code-block:: python

   class User(Model):
       uid = CharField('uid', primary_key=True, max_length=50)
       givenName = CharField('givenName', max_length=100)
       sn = CharField('sn', max_length=100)
       mail = EmailField('mail', max_length=254)

       def get_full_name(self):
           """Return the user's full name."""
           return f"{self.givenName} {self.sn}"

       def is_email_valid(self):
           """Check if the email domain is valid."""
           return '@example.com' in self.mail

       def save(self, *args, **kwargs):
           """Custom save logic."""
           # Ensure UID is lowercase
           self.uid = self.uid.lower()
           super().save(*args, **kwargs)

       class Meta:
            ...

Model Validation
^^^^^^^^^^^^^^^^

Add model-level validation:

.. code-block:: python

   from django.core.exceptions import ValidationError

   class User(Model):
       uid = CharField('uid', primary_key=True, max_length=50)
       givenName = CharField('givenName', max_length=100)
       sn = CharField('sn', max_length=100)

       def clean(self):
           """Model-level validation."""
           if self.givenName and self.sn:
               if self.givenName.lower() == self.sn.lower():
                   raise ValidationError(
                       'Given name and surname cannot be the same'
                   )

       def save(self, *args, **kwargs):
           self.full_clean()
           super().save(*args, **kwargs)

Inheritance
-----------

Model Inheritance
^^^^^^^^^^^^^^^^^

Create base models for common functionality.  There are no ``abstract`` or
``proxy`` models in ``django-ldaporm``.  Instead, you can create a base model
with the common fields and then inherit from it.

.. code-block:: python

   class BaseUser(Model):
       uid = CharField('uid', primary_key=True, max_length=50)
       cn = CharField('cn', max_length=100)
       mail = EmailField('mail', max_length=254)
       created = DateTimeField('whenCreated', auto_now_add=True)
       modified = DateTimeField('whenChanged', auto_now=True)

       class Meta:
           ...

   class LDAPUser(BaseUser):
       sn = CharField('sn', max_length=100)
       givenName = CharField('givenName', max_length=100)
       telephoneNumber = CharField('telephoneNumber', max_length=20, blank=True)

       class Meta:
           ldap_server = 'default'
           basedn = 'ou=users,dc=example,dc=com'
           objectclass = 'person'

   class ADUser(BaseUser):
       sAMAccountName = CharField('sAMAccountName', max_length=50)
       userPrincipalName = CharField('userPrincipalName', max_length=254)

       class Meta:
           ldap_server = 'ad'
           basedn = 'ou=users,dc=example,dc=com'
           objectclass = 'user'

Best Practices
--------------

Naming Conventions
^^^^^^^^^^^^^^^^^^

* Use descriptive model names (e.g., `LDAPUser`, `ADGroup`)
* Follow LDAP attribute naming conventions
* Use consistent field naming across models

Performance Considerations
^^^^^^^^^^^^^^^^^^^^^^^^^^

* Use appropriate search scopes
* Implement proper indexing on LDAP server
* Use paged searches for large result sets
* Cache frequently accessed data

Security
^^^^^^^^

* Use read-only connections when possible
* Implement proper access controls
* Validate all input data
* Use secure LDAP connections (LDAPS)

Error Handling
^^^^^^^^^^^^^^

* Handle LDAP connection errors gracefully
* Implement retry logic for transient failures
* Log LDAP operations for debugging
* Provide meaningful error messages

Example: Complete User Management Model
---------------------------------------

Here's a complete example of a user management model:

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import (
       CharField, EmailField, BooleanField, DateTimeField,
       CharListField, ActiveDirectoryTimestampField
   )
   from django.core.exceptions import ValidationError
   from django.utils import timezone

   class LDAPUser(Model):
       # Identity fields
       uid = CharField('uid', primary_key=True, max_length=50)
       cn = CharField('cn', max_length=100)
       sn = CharField('sn', max_length=100)
       givenName = CharField('givenName', max_length=100)

       # Contact information
       mail = EmailField('mail', max_length=254)
       telephoneNumber = CharField('telephoneNumber', max_length=20, blank=True)
       mobile = CharField('mobile', max_length=20, blank=True)

       # Organizational information
       title = CharField('title', max_length=100, blank=True)
       department = CharField('department', max_length=100, blank=True)
       company = CharField('company', max_length=100, blank=True)

       # Status fields
       is_active = BooleanField('userAccountControl', default=True)
       is_locked = BooleanField('lockoutTime', default=False)

       # Timestamps
       created = DateTimeField('whenCreated', auto_now_add=True)
       modified = DateTimeField('whenChanged', auto_now=True)
       last_logon = ActiveDirectoryTimestampField('lastLogon', null=True)

       # Groups
       memberOf = CharListField('memberOf', max_length=100)

       class Meta:
           ldap_server = 'default'
           basedn = 'ou=users,dc=example,dc=com'
           objectclass = 'person'
           verbose_name = 'LDAP User'
           verbose_name_plural = 'LDAP Users'
           ordering = ['cn']
           search_scope = 'subtree'

       def get_full_name(self):
           """Return the user's full name."""
           return f"{self.givenName} {self.sn}"

       def get_display_name(self):
           """Return the display name (cn or full name)."""
           return self.cn or self.get_full_name()

       def is_account_locked(self):
           """Check if the account is locked."""
           return self.is_locked or (self.last_logon and
                   self.last_logon < timezone.now() - timezone.timedelta(days=90))

       def clean(self):
           """Model-level validation."""
           if self.givenName and self.sn:
               if self.givenName.lower() == self.sn.lower():
                   raise ValidationError(
                       'Given name and surname cannot be the same'
                   )

           if self.uid and not self.uid.isalnum():
               raise ValidationError('UID must be alphanumeric')

       def save(self, *args, **kwargs):
           """Custom save logic."""
           self.full_clean()
           # Ensure UID is lowercase
           self.uid = self.uid.lower()
           super().save(*args, **kwargs)

       def __str__(self):
           return self.get_display_name()

       def __repr__(self):
           return f"<LDAPUser: {self.uid}>"