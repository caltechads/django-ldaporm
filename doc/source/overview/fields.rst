Fields Guide
============

This guide covers the field types available in ``django-ldaporm`` and how to use them.
For complete field API documentation, see :doc:`../api/fields`.

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
   user = User(is_active=True)
   user.save()

IntegerField
^^^^^^^^^^^

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
   user = User(uidNumber=1000, gidNumber=1000)
   user.save()

DateTimeField
^^^^^^^^^^^^

Maps to LDAP timestamp attributes:

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import DateTimeField

   class User(Model):
       created = DateTimeField('whenCreated', auto_now_add=True)
       modified = DateTimeField('whenChanged', auto_now=True)

       class Meta:
            ...

   # Usage
   user = User()
   user.save()  # created and modified will be set automatically

DateField
^^^^^^^^^

Maps to LDAP date attributes:

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import DateField
   from datetime import date

   class User(Model):
       birthDate = DateField('birthDate', null=True)

       class Meta:
            ...

   # Usage
   user = User(birthDate=date(1990, 1, 1))
   user.save()

Advanced Field Types
--------------------

ActiveDirectoryTimestampField
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Specialized field for Active Directory timestamp attributes:

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import ActiveDirectoryTimestampField

   class ADUser(Model):
       last_logon = ActiveDirectoryTimestampField('lastLogon', null=True)
       pwd_last_set = ActiveDirectoryTimestampField('pwdLastSet', null=True)

       class Meta:
            ...

   # Usage
   user = ADUser()
   user.save()

CharListField
^^^^^^^^^^^^^

Handles multi-valued LDAP attributes:

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import CharListField

   class Group(Model):
       cn = CharField('cn', primary_key=True, max_length=50)
       member = CharListField('member', max_length=100)

       class Meta:
            ...

   # Usage
   group = Group(cn='admins', member=['user1', 'user2', 'user3'])
   group.save()

BinaryField
^^^^^^^^^^^

Handles binary LDAP attributes:

.. code-block:: python

   from ldaporm import Model
   from ldaporm.fields import BinaryField

   class User(Model):
       userCertificate = BinaryField('userCertificate', null=True)

       class Meta:
            ...

   # Usage
   with open('cert.pem', 'rb') as f:
       cert_data = f.read()
   user = User(userCertificate=cert_data)
   user.save()

Field Usage Patterns
--------------------

Default Values
^^^^^^^^^^^^^

Set default values for fields:

.. code-block:: python

   class User(Model):
       is_active = BooleanField('userAccountControl', default=True)
       description = CharField('description', max_length=200, default='')

       class Meta:
            ...

Nullable Fields
^^^^^^^^^^^^^^

Allow fields to be null:

.. code-block:: python

   class User(Model):
       telephoneNumber = CharField('telephoneNumber', max_length=20, null=True)
       uidNumber = IntegerField('uidNumber', null=True)

       class Meta:
            ...

Blank Fields
^^^^^^^^^^^^

Allow fields to be blank (empty string):

.. code-block:: python

   class User(Model):
       description = CharField('description', max_length=200, blank=True)
       altMail = EmailField('altMail', max_length=254, blank=True)

       class Meta:
            ...

Auto Fields
^^^^^^^^^^^

Use auto_now and auto_now_add for timestamp fields:

.. code-block:: python

   class User(Model):
       created = DateTimeField('whenCreated', auto_now_add=True)
       modified = DateTimeField('whenChanged', auto_now=True)

       class Meta:
            ...

Field Validation
----------------

Field validation works just like Django ORM fields:

.. code-block:: python

   class User(Model):
       mail = EmailField('mail', max_length=254)
       uidNumber = IntegerField('uidNumber', null=True)

       class Meta:
            ...

   # This will raise a validation error
   try:
       user = User(mail='invalid-email')
       user.full_clean()
   except ValidationError as e:
       print(f"Validation error: {e}")

Next Steps
----------

* See :doc:`../api/fields` for complete field API documentation
* Explore the :doc:`models guide <models>` for model configuration
* Check out the :doc:`managers guide <managers>` for querying options