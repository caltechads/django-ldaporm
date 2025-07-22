Fields Guide
============

This guide covers the field types available in ``django-ldaporm`` and how to use them.

Field Types Overview
--------------------

``django-ldaporm`` provides field types that handle the conversion between Python
data types and LDAP attribute formats. Each field type maps to specific LDAP
attribute syntaxes and handles validation and conversion automatically.

Field names and LDAP attribute names
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The field name is the python symbol for the field in the Python code.  The LDAP
attribute name is the name of the attribute in the LDAP server.  The field name
is used to access the field in the Python code.  The LDAP attribute name is used
to access read and write the attribute in the LDAP server.

If you want to use a field name that is not the same as the LDAP attribute name
(because for instance your linter hates the non-pythonic names or you want it to
be more clear to you and your fellow developers what exactly this field is), you
can use the ``db_column`` parameter to specify the LDAP attribute name.  This is
supported by every field type.

.. code-block:: python

   class User(Model):
       uid = CharField('uid', primary_key=True, max_length=50, db_column='sAMAccountName')

       class Meta:
            ...

Field Arguments
^^^^^^^^^^^^^^^

See :py:class:`~ldaporm.fields.Field` for arguments that all fields take, and
the docs for each field type for additional arguments.


Basic Field Types
-----------------

CharField
^^^^^^^^^

Maps to LDAP string attributes:

.. code-block:: python

   from ldaporm.fields import CharField

   class User(Model):
       uid = CharField('uid', primary_key=True, max_length=50)
       cn = CharField('cn', max_length=100)
       description = CharField('description', max_length=200, blank=True)

       class Meta:
            ...

   # Usage
   user = User(uid='john.doe', cn='John Doe')
   user.save()

EmailField
^^^^^^^^^^

Maps to LDAP email attributes with email validation:

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import EmailField

   class User(Model):
       mail = EmailField('mail', max_length=254)
       altMail = EmailField('altMail', max_length=254, blank=True)

       class Meta:
            ...

   # Usage
   user = User(mail='john.doe@example.com')
   user.save()

BooleanField
^^^^^^^^^^^^

Maps to LDAP boolean attributes:

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import BooleanField

   class User(Model):
       is_active = BooleanField('userAccountControl', default=True)
       is_locked = BooleanField('lockoutTime', default=False)

       class Meta:
            ...

   # Usage
   user = User(is_active=True, is_locked=False)
   user.save()

IntegerField
^^^^^^^^^^^^

Maps to LDAP integer attributes:

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import IntegerField

   class User(Model):
       uidNumber = IntegerField('uidNumber', null=True)
       gidNumber = IntegerField('gidNumber', null=True)

       class Meta:
            ...

   # Usage
   user = User(uidNumber=1000, gidNumber=100)
   user.save()

DateTimeField
^^^^^^^^^^^^^

Maps to LDAP timestamp attributes:

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import DateTimeField
   from django.utils import timezone

   class User(Model):
       created = DateTimeField('whenCreated', auto_now_add=True)
       modified = DateTimeField('whenChanged', auto_now=True)
       lastLogin = DateTimeField('lastLogin', null=True)

       class Meta:
            ...

   # Usage
   user = User(lastLogin=timezone.now())
   user.save()

DateField
^^^^^^^^^

Maps to LDAP date attributes:

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import DateField
   from datetime import date

   class User(Model):
       birthDate = DateField('birthDate', null=True)
       hireDate = DateField('hireDate', null=True)

       class Meta:
            ...

   # Usage
   user = User(birthDate=date(1990, 1, 1))
   user.save()

BinaryField
^^^^^^^^^^^

Maps to LDAP binary attributes:

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import BinaryField

   class User(Model):
       photo = BinaryField('jpegPhoto', null=True)
       certificate = BinaryField('userCertificate', null=True)

       class Meta:
            ...

   # Usage
   with open('photo.jpg', 'rb') as f:
       photo_data = f.read()
   user = User(photo=photo_data)
   user.save()

Multi-valued Fields
-------------------

CharListField
^^^^^^^^^^^^^

Handles LDAP attributes that can have multiple string values:

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import CharListField

   class Group(Model):
       cn = CharField('cn', primary_key=True, max_length=50)
       member = CharListField('member', max_length=100)
       memberUid = CharListField('memberUid', max_length=50)

       class Meta:
            ...

   # Usage
   group = Group(
       cn='developers',
       member=['cn=john,ou=users,dc=example,dc=com', 'cn=jane,ou=users,dc=example,dc=com'],
       memberUid=['john.doe', 'jane.smith']
   )
   group.save()

   # Accessing values
   print(group.member)  # ['cn=john,ou=users,dc=example,dc=com', 'cn=jane,ou=users,dc=example,dc=com']
   print(len(group.member))  # 2

IntegerListField
^^^^^^^^^^^^^^^^

Handles LDAP attributes that can have multiple integer values:

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import IntegerListField

   class Group(Model):
       cn = CharField('cn', primary_key=True, max_length=50)
       gidNumber = IntegerListField('gidNumber')

       class Meta:
            ...

   # Usage
   group = Group(cn='admins', gidNumber=[1000, 1001, 1002])
   group.save()

Active Directory Fields
-----------------------

ActiveDirectoryTimestampField
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Special field for Active Directory timestamp attributes.  Unlike normal LDAP
servers, which typically use either unix epoch time or a string representation
of the time, Active Directory uses a different format.  This format, called
either Active Directory timestamp, 'Windows NT time format', 'Win32 FILETIME or
SYSTEMTIME' or NTFS file time, is an 18 digit number that represents the number
of 100-nanosecond intervals since January 1, 1601 (UTC).  This field type will
convert the LDAP value to a Python datetime object.

.. warning::
    This field type can store really large dates (thousands of years in the
    future) which will cause :py:class:`OverflowError` when converting to a
    Python :py:class:`datetime.datetime` object.  This can be especially true
    for the ``accountExpires`` AD attribute on user objects, which is used to
    store the date and time when the account will expire.

    If you have this problem in your organization, you might have to simply
    store that field as an :py:class:`~ldaporm.fields.IntegerField`.

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import ActiveDirectoryTimestampField

   class ADUser(Model):
       sAMAccountName = CharField('sAMAccountName', primary_key=True, max_length=50)
       lastLogon = ActiveDirectoryTimestampField('lastLogon', null=True)
       pwdLastSet = ActiveDirectoryTimestampField('pwdLastSet', null=True)
       accountExpires = ActiveDirectoryTimestampField('accountExpires', null=True)

       class Meta:
            ...

   # Usage
   user = ADUser(
       sAMAccountName='john.doe',
       lastLogon=timezone.now(),
       pwdLastSet=timezone.now()
   )
   user.save()

Field Options
-------------

Common Field Parameters
^^^^^^^^^^^^^^^^^^^^^^^

All fields support these common parameters:

.. code-block:: python

   class User(Model):
       # Primary key field
       uid = CharField('uid', primary_key=True, max_length=50)

       # Required field (default)
       cn = CharField('cn', max_length=100)

       # Optional field
       description = CharField('description', max_length=200, blank=True)

       # Nullable field
       telephoneNumber = CharField('telephoneNumber', max_length=20, null=True)

       # Field with default value
       is_active = BooleanField('userAccountControl', default=True)

       # Auto-managed fields
       created = DateTimeField('whenCreated', auto_now_add=True)
       modified = DateTimeField('whenChanged', auto_now=True)

Field Validation
^^^^^^^^^^^^^^^^

Add custom validators to fields:

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import CharField, EmailField
   from django.core.exceptions import ValidationError

   def validate_uid_format(value):
       if not value.isalnum():
           raise ValidationError('UID must be alphanumeric')
       if len(value) < 3:
           raise ValidationError('UID must be at least 3 characters')

   def validate_domain_email(value):
       if not value.endswith('@example.com'):
           raise ValidationError('Email must be from example.com domain')

   class User(Model):
       uid = CharField(
           'uid',
           primary_key=True,
           max_length=50,
           validators=[validate_uid_format]
       )
       mail = EmailField(
           'mail',
           max_length=254,
           validators=[validate_domain_email]
       )

       class Meta:
            ...

Custom Field Types
------------------

Creating Custom Fields
^^^^^^^^^^^^^^^^^^^^^^

You can create custom field types for special LDAP attributes:

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import Field, CharField, EmailField
   from django.core.exceptions import ValidationError

   class PhoneNumberField(Field):
       """Custom field for phone number formatting."""

       def __init__(self, ldap_attribute, max_length=20, **kwargs):
           super().__init__(ldap_attribute, **kwargs)
           self.max_length = max_length

       def to_python(self, value):
           """Convert LDAP value to Python."""
           if value is None:
               return None
           if isinstance(value, list):
               value = value[0] if value else None
           if isinstance(value, bytes):
               value = value.decode('utf-8')
           return value

       def to_db_value(self, value):
           """Convert Python value to LDAP format."""
           if value is None:
               return {}

           # Format phone number
           import re
           cleaned = re.sub(r'[^\d+]', '', str(value))
           if not cleaned.startswith('+'):
               cleaned = '+1' + cleaned  # Add country code

           return {self.ldap_attribute: [cleaned.encode('utf-8')]}

       def validate(self, value):
           """Validate phone number format."""
           if value and not re.match(r'^\+[\d\s\-\(\)]+$', str(value)):
               raise ValidationError('Invalid phone number format')

   # Usage
   class User(Model):
       phone = PhoneNumberField('telephoneNumber', max_length=20)
       mobile = PhoneNumberField('mobile', max_length=20, blank=True)

       class Meta:
            ...

Field Inheritance
^^^^^^^^^^^^^^^^^

Extend existing field types:

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import EmailField
   from django.core.exceptions import ValidationError

   class DomainEmailField(EmailField):
       """Email field that only accepts specific domains."""

       def __init__(self, ldap_attribute, allowed_domains=None, **kwargs):
           super().__init__(ldap_attribute, **kwargs)
           self.allowed_domains = allowed_domains or ['example.com']

       def validate(self, value):
           super().validate(value)
           if value:
               domain = value.split('@')[-1]
               if domain not in self.allowed_domains:
                   raise ValidationError(
                       f'Email domain must be one of: {", ".join(self.allowed_domains)}'
                   )

   # Usage
   class User(Model):
       work_email = DomainEmailField('mail', allowed_domains=['company.com'])
       personal_email = DomainEmailField('altMail', allowed_domains=['gmail.com', 'yahoo.com'])

       class Meta:
            ...

Field Conversion Examples
-------------------------

First, it is important to understand that ``python-ldap`` will return the
values for every attribute in the format of a list of bytes, whether that attribute is
multi-valued or not.

Thus in the examples below, the ``ldap_value`` will properly be represented as a
list of bytes.


LDAP to Python Conversion
^^^^^^^^^^^^^^^^^^^^^^^^^

Here's how different LDAP attribute types are converted:

.. code-block:: python

   # String attributes
   ldap_value = [b'John Doe']
   python_value = CharField('cn').to_python(ldap_value)  # 'John Doe'

   # Boolean attributes
   ldap_value = [b'TRUE']
   python_value = BooleanField('isActive').to_python(ldap_value)  # True

   # Integer attributes
   ldap_value = [b'1000']
   python_value = IntegerField('uidNumber').to_python(ldap_value)  # 1000

   # Multi-valued attributes
   ldap_value = [b'group1', b'group2', b'group3']
   python_value = CharListField('memberOf').to_python(ldap_value)  # ['group1', 'group2', 'group3']

Python to LDAP Conversion
^^^^^^^^^^^^^^^^^^^^^^^^^

Here's how Python values are converted back to LDAP format:

.. code-block:: python

   # String to LDAP
   python_value = 'John Doe'
   ldap_value = CharField('cn').to_db_value(python_value)  # {'cn': [b'John Doe']}

   # Boolean to LDAP
   python_value = True
   ldap_value = BooleanField('isActive').to_db_value(python_value)  # {'isActive': [b'TRUE']}

   # Integer to LDAP
   python_value = 1000
   ldap_value = IntegerField('uidNumber').to_db_value(python_value)  # {'uidNumber': [b'1000']}

   # List to LDAP
   python_value = ['group1', 'group2', 'group3']
   ldap_value = CharListField('memberOf').to_db_value(python_value)  # {'memberOf': [b'group1', b'group2', b'group3']}

Best Practices
--------------

Field Naming
^^^^^^^^^^^^

* If you want to use a different name for the python field than for the LDAP
  attribute, use the `db_column` parameter.  This can be useful if you want your
  field names to by pythonic.
* Use Python-friendly names for the field name
* Be consistent with naming conventions across your models

Validation
^^^^^^^^^^

* Add appropriate validators for your use case.
* Validate data at the field level when possible using field validators.
* Use model-level validation for complex business rules by implementing the :py:meth:`~ldaporm.models.Model.clean` method.

Example: Complete Field Usage
-----------------------------

Here's a complete example showing various field types:

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import (
       CharField,
       EmailField,
       BooleanField,
       IntegerField,
       DateTimeField,
       DateField,
       BinaryField,
       CharListField,
       ActiveDirectoryTimestampField,
   )
   from django.core.exceptions import ValidationError
   from django.utils import timezone
   from datetime import date

   class Employee(Model):
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
       employeeNumber = IntegerField('employeeNumber', null=True)

       # Status and dates
       is_active = BooleanField('userAccountControl', default=True)
       hireDate = DateField('hireDate', null=True)
       birthDate = DateField('birthDate', null=True)
       created = DateTimeField('whenCreated', auto_now_add=True)
       modified = DateTimeField('whenChanged', auto_now=True)

       # Active Directory specific
       lastLogon = ActiveDirectoryTimestampField('lastLogon', null=True)
       pwdLastSet = ActiveDirectoryTimestampField('pwdLastSet', null=True)

       # Multi-valued attributes
       memberOf = CharListField('memberOf', max_length=100)
       skills = CharListField('skills', max_length=50, blank=True)

       # Binary data
       photo = BinaryField('jpegPhoto', null=True)

       class Meta:
           ldap_server = 'default'
           basedn = 'ou=employees,dc=example,dc=com'
           objectclass = 'person'

       def clean(self):
           """Model-level validation."""
           if self.hireDate and self.birthDate:
               if self.hireDate < self.birthDate:
                   raise ValidationError('Hire date cannot be before birth date')

       def get_full_name(self):
           """Return the employee's full name."""
           return f"{self.givenName} {self.sn}"

       def get_years_of_service(self):
           """Calculate years of service."""
           if self.hireDate:
               return (date.today() - self.hireDate).days // 365
           return 0

       def __str__(self):
           return self.get_full_name()