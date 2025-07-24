Frequently Asked Questions
==========================

This section answers common questions about django-ldaporm.

Installation & Setup
--------------------

Q: How do I install django-ldaporm?
   The recommended way is using pip: ``pip install django-ldaporm``. For alternative methods, see the :doc:`installation guide <overview/installation>`.

Q: What are the system requirements?
   ``django-ldaporm`` requires Python 3.10+ and Django 4.2+. You also need access to an LDAP server.  See the :doc:`compatibility guide <compatibility>` for details.

Q: How do I configure my LDAP connection?
   Configure your LDAP servers in Django settings using the ``LDAP_SERVERS`` setting. See the :doc:`configuration guide <overview/configuration>` for details.

Q: Can I use django-ldaporm with Active Directory?
   Yes! django-ldaporm has excellent Active Directory support, including specialized fields for AD timestamps. See the :doc:`fields guide <overview/fields>` for details.

Models & Fields
---------------

Q: How do I create an LDAP model?
   Create a model by subclassing :py:class:`~ldaporm.models.Model` and defining fields that map to LDAP attributes. See the :doc:`quickstart guide <overview/quickstart>` for an example.

Q: What field types are available?
   django-ldaporm provides field types for strings, integers, booleans, dates, emails, and more. See the :doc:`fields guide <overview/fields>` for usage patterns and :doc:`api/fields` for complete documentation.

Q: How do I handle multi-valued LDAP attributes?  How do I handle binary data?
   Use :py:class:`~ldaporm.fields.CharField` for multi-valued string attributes. See the :doc:`fields guide <overview/fields>` for examples.

Q: Can I use different field names than LDAP attribute names?
   Yes! Use the ``db_column`` parameter to specify the LDAP attribute name while using a different Python field name.

Q: How do I set a primary key for my LDAP model?
   Use the ``primary_key=True`` parameter on any field. This field will be used as the RDN (Relative Distinguished Name) for the LDAP entry.  Every LDAP model must have a primary key.

Querying & Managers
-------------------

Q: How do I query LDAP data?
   Use the Django QuerySet-like interface: ``User.objects.filter(is_active=True)``. See the :doc:`managers guide <overview/managers>` for details.

Q: Can I use Django's filtering syntax?
   Yes! django-ldaporm supports most Django filtering operations like ``filter()``, ``exclude()``, ``get()``, etc.

Q: How do I handle large result sets?
   ``django-ldaporm`` will implicitly use the Paged Results control to do paging for you.   If you want to do it yourself, use the ``page()`` method: ``User.objects.filter(is_active=True).page(page_size=100)``. See the :doc:`managers guide <overview/managers>` for details.

Q: Can I use slicing and indexing?
   Yes! You can use Python slicing: ``User.objects.filter(is_active=True)[:10]``. This automatically uses VLV when supported.

Q: How do I count results efficiently?
   Use the ``count()`` method: ``User.objects.filter(is_active=True).count()``.

Performance & Optimization
--------------------------

Q: How can I improve query performance?

   - Use specific filters instead of getting all objects
   - Ensure your LDAP server is configured to support paging
   - Enable server-side sorting when available
   - Add size limits to your LDAP server configuration

Q: How do I handle memory usage with large datasets?

   - Use iterators: ``for user in User.objects.filter(is_active=True):``
   - Use paging to process data in chunks
   - Limit result sets with slicing

Q: Can I use connection pooling?

  ``django-ldaporm`` does not yet support connection pooling.  You can configure connection timeouts and retry settings in your LDAP server configuration.

Security
--------

Q: How do I secure my LDAP connection?

   - Use LDAPS (port 636) or STARTTLS
   - Configure proper TLS certificate verification
   - Use strong authentication credentials
   - Limit access permissions on your LDAP server

Q: How do I handle passwords securely?

   - Store passwords in environment variables and have Django read them from there
   - Never hardcode passwords in your code

Q: Can I use different authentication methods?

   ``django-ldaporm`` supports simple authentication. For advanced authentication methods, you may need to configure your LDAP server appropriately.

Integration
-----------

Q: Can I use django-ldaporm with Django forms?

   Yes! LDAP models work seamlessly with Django forms. See the :doc:`quickstart guide <overview/quickstart>` for examples.

Q: Can I use django-ldaporm with Django admin?
   Yes! Register your LDAP models with Django admin just like regular Django models.

Q: Can I use django-ldaporm with Django REST Framework?

   Yes! ``django-ldaporm`` has excellent DRF integration. See the :doc:`REST Framework guide <overview/restframework/restframework>` for details.

Q: Can I use django-ldaporm with django-wildewidgets?

   Yes! ``django-ldaporm`` integrates with `django-wildewidgets <https://github.com/wildewidgets/django-wildewidgets>`_ for building web interfaces. See the :doc:`wildewidgets guide <overview/wildewidgets>` for details.

Troubleshooting
---------------

Q: I'm getting connection errors. What should I check?
   - Verify your LDAP server is accessible
   - Check your LDAP server configuration
   - Ensure proper authentication credentials
   - See the :doc:`troubleshooting guide <runbook/troubleshooting>` for detailed help.

Q: My queries return no results. What's wrong?
   - Check your base DN configuration
   - Verify object classes match your LDAP data
   - Test with simple searches first
   - Check LDAP filters and search scope

Q: I'm getting field conversion errors. How do I fix them?
   - Ensure field types match your LDAP data
   - Use ``null=True`` for optional fields
   - Check for missing attributes in your LDAP entries

Q: How do I enable debug logging?
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   logging.getLogger('ldaporm').setLevel(logging.DEBUG)
   ```

Advanced Topics
---------------

Q: Can I create custom field types?
   Yes! You can subclass ``ldaporm.fields.Field`` to create custom field types. See the :doc:`fields guide <overview/fields>` for examples.

Q: How do I handle Active Directory timestamps?
   Use ``ActiveDirectoryTimestampField`` for AD timestamp attributes. See the :doc:`fields guide <overview/fields>` for details.

Q: Can I use Virtual List View (VLV)?
   Yes! django-ldaporm automatically uses VLV when supported by your LDAP server for efficient slicing operations.

Q: How do I handle LDAP referrals?
   Configure the ``follow_referrals`` option in your LDAP server configuration.

Q: Can I use multiple LDAP servers?
   Yes! Configure multiple servers in your ``LDAP_SERVERS`` setting and specify which server to use in your model's Meta class.

Migration & Compatibility
-------------------------

Q: How do I migrate from other LDAP libraries?
   django-ldaporm provides a familiar Django ORM interface, making migration straightforward. Start with simple models and gradually add complexity.

Q: Is django-ldaporm compatible with my LDAP server?
   django-ldaporm works with most LDAP servers including OpenLDAP, Active Directory, Apache Directory Server, and others.

Q: Can I use django-ldaporm with existing LDAP data?
   Yes! django-ldaporm is designed to work with existing LDAP directories. Just configure your models to match your existing LDAP schema.

Q: How do I handle schema differences between LDAP servers?
   Use the ``db_column`` parameter to map your model fields to different LDAP attribute names, or create separate models for different servers.

Getting Help
------------

Q: Where can I get more help?
   - Check the :doc:`troubleshooting guide <runbook/troubleshooting>`
   - Review the :doc:`configuration guide <overview/configuration>`
   - See the :doc:`API reference <api/models>`
   - Check the :doc:`glossary <glossary>` for LDAP terminology

Q: How do I report bugs or request features?
   Please report issues through the project's issue tracker with detailed information about your environment and the problem you're experiencing.

Q: Can I contribute to django-ldaporm?
   Yes! Contributions are welcome. Please check the project's contribution guidelines for details.