Glossary
========

This glossary defines LDAP-specific terms used throughout the django-ldaporm documentation.

.. glossary::

   LDAP
      Lightweight Directory Access Protocol. A protocol for accessing and managing directory information services.

   DN (Distinguished Name)
      A unique identifier for an entry in an LDAP directory. Example: ``cn=john.doe,ou=users,dc=example,dc=com``

   RDN (Relative Distinguished Name)
      The leftmost component of a DN. Example: ``cn=john.doe`` in ``cn=john.doe,ou=users,dc=example,dc=com``

   Base DN
      The root of the LDAP directory tree. Example: ``dc=example,dc=com``

   Bind DN
      The DN used to authenticate to the LDAP server. Example: ``cn=admin,dc=example,dc=com``

   Object Class
      A schema definition that specifies the attributes an LDAP entry can have.
      Example: ``person``, ``organizationalPerson``.  Schemas define the object
      classes that are allowed in an LDAP directory, and which MUST be present
      on all entries, and which MAY optionallybe present on some entries.  A
      single object in LDAP may have multiple object classes.

   Attribute
      A property of an LDAP entry. Example: ``cn`` (Common Name), ``sn`` (Surname), ``mail``

   Multi-valued Attribute
      An attribute that can have multiple values. Example: ``member`` in a group
      entry.  Note that while all attributes are returned as lists, the LDAP
      schema for that attribute will indicate if the attribute is multi-valued.

   LDAPS
      LDAP over SSL/TLS. Encrypted LDAP communication using port 636.

   STARTTLS
      A protocol that upgrades a plain text connection to an encrypted connection.

   Active Directory
      Microsoft's implementation of LDAP, commonly used in Windows environments.

   Active Directory Timestamp
      A special timestamp format used by Active Directory representing 100-nanosecond intervals since January 1, 1601.

   VLV (Virtual List View)
      An LDAP control that allows efficient paging through large result sets.

   Server-Side Sorting
      An LDAP control that allows the server to sort results before returning them to the client.

   Referral
      A pointer to another LDAP server that may contain the requested information.

   Schema
      The set of rules that define the structure and content of an LDAP directory.

   Entry
      A single record in an LDAP directory, consisting of a DN and a set of attributes.

   Filter
      A search criteria used to find entries in an LDAP directory. Example: ``(cn=john*)``

   Search Scope
      The depth of an LDAP search:

      * **Base**: Search only the specified entry
      * **One Level**: Search immediate children of the specified entry
      * **Subtree**: Search the specified entry and all its descendants

   Modlist
      A list of modifications to be applied to an LDAP entry.

   Atomic Operation
      An operation that either completes entirely or not at all, with no partial state.

   Bind
      The process of authenticating to an LDAP server.

   Unbind
      The process of disconnecting from an LDAP server.

   Search
      The process of querying an LDAP directory for entries that match certain criteria.

   Add
      The process of creating a new entry in an LDAP directory.

   Modify
      The process of updating an existing entry in an LDAP directory.

   Delete
      The process of removing an entry from an LDAP directory.

   Compare
      The process of checking if an entry has a specific attribute value.

   Extended Operation
      An `LDAP extended operation <https://tools.ietf.org/html/rfc4511>`_ is a
      custom LDAP operation that extends the standard LDAP protocol.

   LDAP Control
      An `LDAP control <https://tools.ietf.org/html/rfc2696>`_ is additional
      information sent with an LDAP operation to modify its behavior.

   Certificate
      A digital document used to verify the identity of an LDAP server or client.

   CA (Certificate Authority)
      An entity that issues digital certificates.

   CRL (Certificate Revocation List)
      A list of certificates that have been revoked by the CA.

   OCSP (Online Certificate Status Protocol)
      A protocol for checking the revocation status of certificates.

   ACI (Access Control Instruction)
      Rules that control access to LDAP entries and attributes.

   ACL (Access Control List)
      A list of permissions associated with an LDAP entry.

   Changelog
      A log of changes made to an LDAP directory, used for replication.

   Referential Integrity
      The consistency of references between related entries in an LDAP directory.

   Operational Attributes
      LDAP attributes that are managed by the server and cannot be modified by clients.

   User Attributes
      LDAP attributes that contain user data and can be modified by clients.

   Schema Attributes
      LDAP attributes that define the structure of the directory.

   Subschema
      A subset of the LDAP schema that applies to a specific part of the directory.

   Matching Rule
      A rule that defines how attribute values are compared during searches.

   Syntax
      The format and constraints for attribute values.

   OID (Object Identifier)
      A globally unique identifier for LDAP schema elements.

   LDIF (LDAP Data Interchange Format)
      A text format for representing LDAP entries and modifications.

   LDAP URL
      A URL format for specifying LDAP servers and operations.  Examples:

      * ``ldap://ldap.example.com``
      * ``ldaps://ldap.example.com``
      * ``ldap://[2001:db8::1]:389``
      * ``ldap://[2001:db8::1]:636``
      * ``ldap://[2001:db8::1]:389/ou=users,dc=example,dc=com``
      * ``ldap://[2001:db8::1]:636/ou=users,dc=example,dc=com``
      * ``ldap://[2001:db8::1]:389/ou=users,dc=example,dc=com?cn``

   Timeout
      The maximum time to wait for an LDAP operation to complete.

   Caching
      The process of storing frequently accessed LDAP data locally to improve performance.

   Index
      A data structure that improves the performance of LDAP searches.  These
      are implemented by the LDAP server, and are not part of the LDAP protocol.

   Database
      The underlying storage system used by an LDAP server.

   Lock
      A mechanism that prevents multiple operations from modifying the same data simultaneously.