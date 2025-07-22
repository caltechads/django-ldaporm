Configuration Guide
===================

This guide covers all configuration options for ``django-ldaporm``.

Basic Configuration
-------------------

The main configuration is done through ``settings.LDAP_SERVERS`` in your Django
settings.  This is a dictionary of server identifiers to server configurations.

This example sets up read and write servers for an LDAP server, and will use
the read server for all operations, and the write server for all operations
that require a write.   The connections to the servers will use STARTTLS.

.. code-block:: python

   LDAP_SERVERS = {
       'default': {
           'basedn': 'dc=example,dc=com',
           'read': {
               'url': 'ldap://ldapslave.example.com',
               'user': 'cn=admin,dc=example,dc=com',
               'password': 'your-password',
               'sizelimit': 1000,
            },
            'write': {
                'url': 'ldaps://ldapmaster.example.com:636',
                'user': 'cn=admin,dc=example,dc=com',
                'password': 'your-password',
                'timeout': 30,
            }
       }
   }

Note that there are three bits of configuration here:

* The ``basedn`` is the base DN for the LDAP server.
* The ``read`` and ``write`` are the read and write servers for the LDAP server.

Inside the ``read`` and ``write`` dictionaries, we have the following options:

* The ``url`` is the URL for the LDAP server (required).
* The ``user`` is the user to bind to the LDAP server (required).
* The ``password`` is the password for the user to bind to the LDAP server (required).
* The ``use_starttls`` is a boolean indicating whether to use STARTTLS.  It is a ``bool`` and defaults to ``True``.
* The ``follow_referrals`` is a boolean indicating whether to follow referrals.  It defaults to ``False``.
* The ``timeout`` is the **network** timeout for the LDAP server.  It is a ``float`` and defaults to ``15.0``.
* The ``sizelimit`` is the size limit for the LDAP server.  It is an ``int | None`` and defaults to
  ``None``, which means whatever the server defaults to.
* The ``tls_verify`` is a boolean indicating how to verify the TLS certificate.
  It is a ``str`` which can be one of:

    - ``"never"``: never verify the certificate (default)
    - ``"always"``: always verify the certificate

* The ``tls_ca_certfile`` is the absolute path to the CA certificate file.  It
  is a ``str | None`` and defaults to ``None``.  If provided, the file must
  exist and be a file.
* The ``tls_certfile`` is the absolute path to the client certificate file.  It
  is a ``str | None`` and defaults to ``None``.  If provided, the file must
  exist and be a file.
* The ``tls_keyfile`` is the absolute path to the client private key file.  It
  is a ``str | None`` and defaults to ``None``.  If provided, the file must
  exist and be a file.

Server Configuration Options
-----------------------------

URL Configuration
^^^^^^^^^^^^^^^^^^

The `url` parameter supports both LDAP and LDAPS protocols:

.. code-block:: python

   # Standard LDAP
   'url': 'ldap://ldap.example.com:389'

   # LDAPS (encrypted)
   'url': 'ldaps://ldap.example.com:636'

   # LDAP with custom port
   'url': 'ldap://ldap.example.com:10389'

Advanced Configuration
----------------------

Connection Options
^^^^^^^^^^^^^^^^^^

Configure connection behavior:

.. code-block:: python

   LDAP_SERVERS = {
       'default': {
           'url': 'ldaps://ldap.example.com:636',
           'user': 'cn=admin,dc=example,dc=com',
           'password': 'your-password',
           'basedn': 'dc=example,dc=com',
           'timeout': 30,  # Connection timeout in seconds
           'retry_max': 3,  # Maximum retry attempts
           'retry_delay': 1,  # Delay between retries in seconds
       }
   }

TLS Configuration
^^^^^^^^^^^^^^^^^

Disable TLS/SSL:


.. code-block:: python

   LDAP_SERVERS = {
       'default': {
           'basedn': 'dc=example,dc=com',
           'read': {
               'url': 'ldap://ldapslave.example.com:389',
               'user': 'cn=admin,dc=example,dc=com',
               'password': 'your-password',
               'use_starttls': False,
           },
           'write': {
               'url': 'ldap://ldapmaster.example.com:389',
               'user': 'cn=admin,dc=example,dc=com',
               'password': 'your-password',
               'use_starttls': False,
           }
       }
   }

Configure TLS/SSL settings:

.. code-block:: python

   LDAP_SERVERS = {
       'default': {
           'basedn': 'dc=example,dc=com',
           'read': {
               'url': 'ldaps://ldapslave.example.com:636',
               'user': 'cn=admin,dc=example,dc=com',
               'password': 'your-password',
               'tls_verify': 'always',
               'tls_ca_certfile': '/path/to/ca.crt',
               'tls_certfile': '/path/to/client.crt',
               'tls_keyfile': '/path/to/client.key',
           },
           'write': {
               'url': 'ldaps://ldapmaster.example.com:636',
               'user': 'cn=admin,dc=example,dc=com',
               'password': 'your-password',
               'tls_verify': 'always',
               'tls_ca_certfile': '/path/to/ca.crt',
               'tls_certfile': '/path/to/client.crt',
               'tls_keyfile': '/path/to/client.key',
           }
       }
   }

Search Options
^^^^^^^^^^^^^^

Configure search behavior:

.. code-block:: python

   LDAP_SERVERS = {
       'default': {
           'basedn': 'dc=example,dc=com',
           'read': {
               'url': 'ldaps://ldap.example.com:636',
               'user': 'cn=admin,dc=example,dc=com',
               'password': 'your-password',
               'page_size': 1000,  # Results per page
           },
           'write': {
               'url': 'ldaps://ldap.example.com:636',
               'user': 'cn=admin,dc=example,dc=com',
               'password': 'your-password',
           }
       }
   }

Multiple Server Configuration
-----------------------------

Configure multiple LDAP servers for different purposes:

.. code-block:: python

   LDAP_SERVERS = {
       'default': {
           'basedn': 'dc=example,dc=com',
           'read': {
               'url': 'ldap://ldapslave.example.com:389',
               'user': 'cn=admin,dc=example,dc=com',
               'password': 'your-password',
           },
           'write': {
               'url': 'ldap://ldapmaster.example.com:389',
               'user': 'cn=admin,dc=example,dc=com',
               'password': 'your-password',
           }
       }
       'ad': {
           'basedn': 'dc=example,dc=com',
           'read': {
               'url': 'ldap://ad.example.com:389',
               'user': 'cn=admin,dc=example,dc=com',
               'password': 'your-password',
           },
           'write': {
               'url': 'ldap://ad.example.com:389',
               'user': 'cn=admin,dc=example,dc=com',
               'password': 'your-password',
           }
       }
   }


Security Considerations
-----------------------

* Use LDAPS (ldaps://) or STARTTLS for encrypted connections
* You must provide a bind DN and password for the LDAP server.  We don't support
  anonymous binds.
* Use read-only accounts on the read server
* Implement proper access controls on both servers
* Regularly rotate credentials
* Monitor LDAP access logs

Troubleshooting Configuration
-----------------------------

Common configuration issues:

**Connection Timeouts**
* Increase `timeout` value
* Check network connectivity
* Verify LDAP server is running

**Authentication Failures**
* Verify bind DN and password
* Check account lockouts
* Ensure proper permissions

**TLS Certificate Issues**
* Set `tls_verify=never` for testing (or unset it, since it defaults to ``never``)
* Provide proper CA certificates
* Check certificate expiration
