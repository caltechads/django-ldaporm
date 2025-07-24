Troubleshooting Guide
=====================

This guide covers common issues and their solutions when using django-ldaporm.

Connection Issues
-----------------

Cannot Connect to LDAP Server
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Symptoms:**
- Connection timeout errors
- Authentication failures
- "Connection refused" errors

**Solutions:**

1. **Verify LDAP server is accessible:**
   .. code-block:: bash

      # Test basic connectivity
      telnet ldap.example.com 389
      # or for LDAPS
      telnet ldap.example.com 636

2. **Check LDAP server configuration:**
   .. code-block:: python

      LDAP_SERVERS = {
          'default': {
              'basedn': 'dc=example,dc=com',
              'read': {
                  'url': 'ldap://ldap.example.com:389',  # Verify URL and port
                  'user': 'cn=admin,dc=example,dc=com',  # Verify bind DN
                  'password': 'your-password',
                  'timeout': 30,  # Increase timeout if needed
              }
          }
      }

3. **Test with simple LDAP client:**
   .. code-block:: python

      import ldap

      # Test basic connection
      conn = ldap.initialize('ldap://ldap.example.com:389')
      conn.simple_bind_s('cn=admin,dc=example,dc=com', 'your-password')
      print("Connection successful")

Authentication Failures
^^^^^^^^^^^^^^^^^^^^^^

**Symptoms:**
- "Invalid credentials" errors
- "Insufficient access" errors

**Solutions:**

1. **Verify bind credentials:**
   - Check username/password are correct
   - Ensure the bind DN has proper permissions
   - Verify the account is not locked or expired

2. **Check LDAP server logs:**
   - Look for authentication failures in server logs
   - Check for account lockout policies

3. **Test with different bind DN:**
   .. code-block:: python

      # Try with different bind DN format
      'user': 'uid=admin,dc=example,dc=com'  # Instead of cn=admin,dc=example,dc=com

TLS/SSL Issues
^^^^^^^^^^^^^^

**Symptoms:**
- SSL certificate errors
- TLS handshake failures

**Solutions:**

1. **Disable TLS verification for testing:**
   .. code-block:: python

      LDAP_SERVERS = {
          'default': {
              'basedn': 'dc=example,dc=com',
              'read': {
                  'url': 'ldaps://ldap.example.com:636',
                  'user': 'cn=admin,dc=example,dc=com',
                  'password': 'your-password',
                  'tls_verify': 'never',  # Disable verification for testing
              }
          }
      }

2. **Provide CA certificate:**
   .. code-block:: python

      LDAP_SERVERS = {
          'default': {
              'basedn': 'dc=example,dc=com',
              'read': {
                  'url': 'ldaps://ldap.example.com:636',
                  'user': 'cn=admin,dc=example,dc=com',
                  'password': 'your-password',
                  'tls_verify': 'always',
                  'tls_ca_certfile': '/path/to/ca.crt',
              }
          }
      }

3. **Use STARTTLS instead of LDAPS:**
   .. code-block:: python

      LDAP_SERVERS = {
          'default': {
              'basedn': 'dc=example,dc=com',
              'read': {
                  'url': 'ldap://ldap.example.com:389',
                  'user': 'cn=admin,dc=example,dc=com',
                  'password': 'your-password',
                  'use_starttls': True,
              }
          }
      }

Query Issues
------------

No Results Returned
^^^^^^^^^^^^^^^^^

**Symptoms:**
- Queries return empty results
- Expected data not found

**Solutions:**

1. **Check base DN:**
   .. code-block:: python

      class User(Model):
          # ... fields ...

          class Meta:
              ldap_server = 'default'
              basedn = 'ou=users,dc=example,dc=com'  # Verify this is correct
              objectclass = 'person'

2. **Verify object classes:**
   .. code-block:: python

      class User(Model):
          # ... fields ...

          class Meta:
              objectclass = 'person'  # Verify this matches LDAP objects
              objectclasses = ['inetOrgPerson', 'organizationalPerson']

3. **Test with simple search:**
   .. code-block:: python

      # Test basic search
      users = User.objects.all()
      print(f"Found {len(users)} users")

4. **Check LDAP filters:**
   .. code-block:: python

      # Use more specific filters
      users = User.objects.filter(cn__icontains='john')
      print(f"Found {len(users)} users with 'john' in cn")

Performance Issues
------------------

Slow Queries
^^^^^^^^^^^

**Symptoms:**
- Queries take a long time to complete
- Timeout errors on large result sets

**Solutions:**

1. **Use paging for large result sets:**
   .. code-block:: python

      # Use paging for large result sets
      paged_results = User.objects.filter(is_active=True).page(page_size=100)
      for user in paged_results:
          print(user.uid)

2. **Add size limits:**
   .. code-block:: python

      LDAP_SERVERS = {
          'default': {
              'basedn': 'dc=example,dc=com',
              'read': {
                  'url': 'ldap://ldap.example.com:389',
                  'user': 'cn=admin,dc=example,dc=com',
                  'password': 'your-password',
                  'sizelimit': 1000,  # Limit results
              }
          }
      }

3. **Use more specific filters:**
   .. code-block:: python

      # Instead of getting all users
      all_users = User.objects.all()  # Slow

      # Use specific filters
      active_users = User.objects.filter(is_active=True)  # Faster
      dept_users = User.objects.filter(department='IT')  # Even faster

4. **Enable server-side sorting:**
   .. code-block:: python

      # Use server-side sorting when available
      users = User.objects.filter(is_active=True).order_by('cn')

Memory Issues
^^^^^^^^^^^^

**Symptoms:**
- High memory usage
- Out of memory errors

**Solutions:**

1. **Use iterators for large result sets:**
   .. code-block:: python

      # Use iterator to avoid loading all objects in memory
      for user in User.objects.filter(is_active=True):
          process_user(user)

2. **Limit result sets:**
   .. code-block:: python

      # Limit number of results
      users = User.objects.filter(is_active=True)[:100]

3. **Use paging:**
   .. code-block:: python

      # Use paging to process in chunks
      paged_results = User.objects.filter(is_active=True).page(page_size=50)
      for user in paged_results:
          process_user(user)

Data Issues
-----------

Field Conversion Errors
^^^^^^^^^^^^^^^^^^^^^^

**Symptoms:**
- ValueError when accessing fields
- Incorrect data types

**Solutions:**

1. **Check field definitions:**
   .. code-block:: python

      class User(Model):
          # Ensure field types match LDAP data
          uidNumber = IntegerField('uidNumber', null=True)  # Use null=True for optional fields
          is_active = BooleanField('userAccountControl', default=True)

2. **Handle missing attributes:**
   .. code-block:: python

      class User(Model):
          telephoneNumber = CharField('telephoneNumber', max_length=20, blank=True, null=True)

3. **Use custom field conversion:**
   .. code-block:: python

      from ldaporm.fields import Field

      class CustomField(Field):
          def to_python(self, value):
              if value is None:
                  return None
              # Add custom conversion logic
              return str(value).upper()

Active Directory Issues
----------------------

Timestamp Conversion Errors
^^^^^^^^^^^^^^^^^^^^^^^^^^

**Symptoms:**
- OverflowError with Active Directory timestamps
- Incorrect date/time values

**Solutions:**

1. **Use ActiveDirectoryTimestampField:**
   .. code-block:: python

      from ldaporm.fields import ActiveDirectoryTimestampField

      class ADUser(Model):
          last_logon = ActiveDirectoryTimestampField('lastLogon', null=True)
          pwd_last_set = ActiveDirectoryTimestampField('pwdLastSet', null=True)

2. **Handle large timestamps:**
   .. code-block:: python

      # For problematic AD attributes like accountExpires
      class ADUser(Model):
          account_expires = IntegerField('accountExpires', null=True)  # Store as integer

3. **Add validation:**
   .. code-block:: python

      class ADUser(Model):
          last_logon = ActiveDirectoryTimestampField('lastLogon', null=True)

          def clean(self):
              if self.last_logon and self.last_logon.year > 2100:
                  # Handle very large timestamps
                  self.last_logon = None

Debugging Tips
--------------

Enable Debug Logging
^^^^^^^^^^^^^^^^^^

Add debug logging to see LDAP operations:

.. code-block:: python

   import logging

   # Enable LDAP debug logging
   logging.basicConfig(level=logging.DEBUG)
   logging.getLogger('ldaporm').setLevel(logging.DEBUG)

Test with Simple Script
^^^^^^^^^^^^^^^^^^^^^^

Create a simple test script to isolate issues:

.. code-block:: python

   # test_ldap.py
   from ldaporm import Model
   from ldaporm.fields import CharField

   class TestUser(Model):
       uid = CharField('uid', primary_key=True, max_length=50)
       cn = CharField('cn', max_length=100)

       class Meta:
           ldap_server = 'default'
           basedn = 'ou=test,dc=example,dc=com'
           objectclass = 'person'

   # Test basic operations
   try:
       users = TestUser.objects.all()
       print(f"Successfully connected. Found {len(users)} users.")

       if users:
           user = users[0]
           print(f"First user: {user.uid} - {user.cn}")
   except Exception as e:
       print(f"Error: {e}")
       import traceback
       traceback.print_exc()

Common Error Messages
--------------------

"Connection refused"
   - LDAP server is not running or not accessible
   - Check server URL and port
   - Verify network connectivity

"Invalid credentials"
   - Bind DN or password is incorrect
   - Account may be locked or expired
   - Check LDAP server logs

"SSL certificate verify failed"
   - TLS certificate issues
   - Use `tls_verify: 'never'` for testing
   - Provide correct CA certificate

"No such object"
   - Base DN does not exist
   - Object class mismatch
   - Check LDAP directory structure

"Size limit exceeded"
   - Result set too large
   - Use paging or add size limits
   - Use more specific filters

Getting Help
------------

If you're still experiencing issues:

1. **Check the documentation:**
   - Review the :doc:`../overview/configuration` guide
   - See the :doc:`../api/managers` for complete API reference

2. **Enable debug logging** to see detailed LDAP operations

3. **Create a minimal test case** to reproduce the issue

4. **Check your LDAP server logs** for additional error information

5. **Verify your LDAP server configuration** and permissions