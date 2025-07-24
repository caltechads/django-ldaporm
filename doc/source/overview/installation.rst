Installation Guide
==================

This guide covers the complete installation and setup process for django-ldaporm.
For a quick start, see the :doc:`quickstart guide <quickstart>`.

Requirements
------------

* Python 3.10 or higher
* Django 4.2 or higher (demo requires 5.2 or higher)
* Access to an LDAP server

Installing django-ldaporm
-------------------------

Using pip (recommended):

.. code-block:: bash

   pip install django-ldaporm

For development installation:

.. code-block:: bash

   git clone https://github.com/your-repo/django-ldaporm.git
   cd django-ldaporm
   pip install -e .

Using uv (modern Python package manager):

.. code-block:: bash

   uv add django-ldaporm

Django Configuration
--------------------

Add django-ldaporm to your Django settings:

.. code-block:: python

   INSTALLED_APPS = [
       'django.contrib.admin',
       'django.contrib.auth',
       'django.contrib.contenttypes',
       'django.contrib.sessions',
       'django.contrib.messages',
       'django.contrib.staticfiles',
       'ldaporm',  # Add this line
       # ... your other apps
   ]

LDAP Server Configuration
-------------------------

Configure your LDAP servers via the ``LDAP_SERVERS`` setting in your Django
settings. For complete configuration options, see the :doc:`configuration guide <configuration>`.

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

Troubleshooting
---------------

Common Installation Issues
^^^^^^^^^^^^^^^^^^^^^^^^^^

**python-ldap installation fails**

See `python-ldap build prerequisites <https://www.python-ldap.org/en/python-ldap-3.4.3/installing.html#build-prerequisites>`_.

**Connection issues**

* Verify your LDAP server is accessible
* Check your LDAP server configuration
* Ensure proper authentication credentials
* Review the :doc:`configuration guide <configuration>` for advanced settings

Testing Your Installation
-------------------------

Create a simple test to verify your installation:

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

   # Test the connection
   try:
       users = TestUser.objects.all()
       print(f"Successfully connected to LDAP. Found {len(users)} users.")
   except Exception as e:
       print(f"Connection failed: {e}")

Run the test:

.. code-block:: bash

   python test_ldap.py

Next Steps
----------

* Read the :doc:`quickstart guide <quickstart>` for basic usage
* Explore the :doc:`configuration guide <configuration>` for advanced setup
* Check out the :doc:`models guide <models>` for creating LDAP models