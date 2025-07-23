Running the Demo Application
============================

This guide covers how to build, run, and access the ``django-ldaporm`` demo
application, which showcases the library's features with a complete web
interface.

Prerequisites
-------------

Before running the demo, ensure you have:

1. **Docker and Docker Compose**: Required for running the demo with LDAP services

   .. code-block:: bash

      docker --version
      docker-compose --version

3. **Dependencies**: Install all required dependencies

   .. code-block:: bash

      uv sync --group=demo --dev

2. **Python Environment**: Activate the project's virtual environment

   .. code-block:: bash

      source .venv/bin/activate

Demo Overview
-------------

The demo application provides:

- **User Management**: Create, edit, and delete LDAP users
- **REST API**: Full CRUD operations via API endpoints
- **LDAP Integration**: Real LDAP server connectivity

Demo Architecture
-----------------

The demo consists of several components:

- **Django Application**: Main web application
- **LDAP Server**: 389 Directory Server for user data
- **Database**: MySQL for Django models
- **Web Server**: Nginx for static file serving
- **Application Server**: Gunicorn for Django application

Quick Start with Docker
-----------------------

The easiest way to run the demo is using Docker Compose:

1. **Navigate to the sandbox directory**:

   .. code-block:: bash

      cd sandbox

2. **Build the demo application**:

   .. code-block:: bash

      # tars up ../ldaporm into a tar file in the sandbox directory
      make package
      # builds the docker image from the tar file
      make build

3. **Run the LDAP server and load the data**:

   .. code-block:: bash

      docker-compose up -d ldap
      docker exec -ti ldap bash
      > dsconf localhost backend create --suffix "o=example,c=us" --be-name example
      > ^D
      cd data/ldap/init
      ./load_data.sh
      docker-compose down ldap

    The data will be loaded into the LDAP server, and saved to the volume
    ``django_ldaporm_demo_ldap_data`` for persistence.

4. **Run the demo application**:

   .. code-block:: bash

      make dev

   This will run the demo application and automatically run all the
   migrations and load the initial fixture data, including Django user data.

6. **Access the demo**:

   - **Main Application**: https://localhost
   - **API Endpoints**: https://localhost/api/

   Since this is a development demo, there is no authentication. You can just
   browse the application and API endpoints.

Docker Services
---------------

The demo includes several Docker services:

**Web Application** (``django_ldaporm_demo``)

   - Nginx reverse proxy
   - Gunicorn WSGI server
   - Port: 443
   - Mounts the ``./demo`` folder over ``/ve/lib/python3.13/site-packages/sandbox/demo``
   - Also mounts ``../ldaporm`` folder over ``/ve/lib/python3.13/site-packages/ldaporm``

**LDAP Server** (``ldap``)

   - 389 Directory Server
   - Port: 389 (LDAP), 636 (LDAPS)
   - Admin DN: ``cn=Directory Manager``
   - Admin Password: ``password``
   - Data is persisted in the ``django_ldaporm_demo_ldap_data`` volume

.. note::
   After following the instructions above, this LDAP server will be configured
   to use the ``o=example,c=us`` suffix.  This is the default suffix for the
   demo data.

    For whatever reason, I could not get ``nsRole`` attributes to appear on the
    users inside the 389-ds server. I checked many things:

    - The "Roles Plugin" is installed and enabled
    - The roles we create have the proper object classes
    - The ``nsslapd-ignore-virtual-attrs`` is automatically set to ``off`` (enabling ``nsRole``, a virtual attribute, to be populated) when we load the role objects (you can see this in the ldap startup logs)
    - The roles assigned to ``nsRoleDN`` on each user each have a ``dn`` that corresponds to an actual role object
    - The ``nsFilteredRoleDefinition`` objects just don't seem to do anything

    I assure you that in our production environment, all this works fine.

**Database** (``mysql``)

   - MySQL database
   - Port: 3306
   - Database: ``demo``
   - User: ``demo_u``
   - Password: ``password``
   - Root Password: ``root_password``
   - Data is persisted in the ``django_ldaporm_demo_data`` volume


Configuration
-------------

The demo uses different settings files for different environments:

**Docker Settings** (`settings_docker.py`)

   - Used when building the Docker image

**Development Settings** (`settings.py`)

   - Local development configuration
   - Debug mode enabled
   - MySQL database

**Test Settings** (`settings_test.py`)

   - Test-specific configuration
   - In-memory database
   - Mock LDAP connections

Demo Features
-------------

**User Management**

   - Browse all LDAP users
   - Create new users
   - Edit user attributes
   - Delete users
   - Search and filter users

**Group Management**

   - Browse all LDAP groups
   - Create new groups
   - Edit group attributes
   - Delete groups
   - Search and filter groups

**Role Management**

   - Browse all LDAP roles
   - Search and filter roles

**REST API**
   - Full CRUD operations
   - JSON responses
   - Filtering and pagination
   - Authentication support


API Endpoints
-------------

The demo provides REST API endpoints for managing users, groups, and roles:

**Users API**

   - `GET /api/users/` - List all users
   - `POST /api/users/` - Create new user
   - `GET /api/users/{username}/` - Get user details
   - `PUT /api/users/{username}/` - Update user
   - `PATCH /api/users/{username}/` - Partial update user
   - `DELETE /api/users/{username}/` - Delete user

**Groups API**

   - `GET /api/groups/` - List all groups
   - `POST /api/groups/` - Create new group
   - `GET /api/groups/{group_name}/` - Get group details
   - `PUT /api/groups/{group_name}/` - Update group
   - `PATCH /api/groups/{group_name}/` - Partial update group
   - `DELETE /api/groups/{group_name}/` - Delete group

**Roles API**

   - `GET /api/roles/` - List all roles
   - `POST /api/roles/` - Create new role
   - `GET /api/roles/{role_name}/` - Get role details
   - `PUT /api/roles/{role_name}/` - Update role
   - `PATCH /api/roles/{role_name}/` - Partial update role
   - `DELETE /api/roles/{role_name}/` - Delete role

Example API Usage
-----------------

Since this is a development demo, there is no authentication. You can just
browse the application and API endpoints.

Here are some example API calls:

**List all users**:

   .. code-block:: bash

      curl --insecure https://localhost/api/users/

**Filter users**:

   .. code-block:: bash

      curl --insecure https://localhost/api/users/?employee_type=manager

**Create a new user**:

   .. code-block:: bash

      curl --insecure -X POST -H "Content-Type: application/json" \
           -d '{"uid": "newuser", "first_name": "New", "last_name": "User", "employee_type": "developer", "full_name": "New User", "mail": ["newuser@example.com"]}' \
           https://localhost/api/users/

**Update just the first name of a user**:

   .. code-block:: bash

      curl --insecure -X PATCH -H "Content-Type: application/json" \
           -d '{"first_name": "Updated"}' \
           https://localhost/api/users/newuser/

**Delete a user**:

   .. code-block:: bash

      curl --insecure -X DELETE https://localhost/api/users/newuser/

Troubleshooting
---------------

**Docker Issues**

*Service won't start*:

   .. code-block:: bash

      # Check service logs
      docker-compose logs django_ldaporm_demo
      docker-compose logs ldap
      docker-compose logs db

      # Restart services
      docker-compose down
      docker-compose up -d

*Port conflicts*:

   - Ensure ports 443, 389, 636 and 3306 are available
   - Change ports in docker-compose.yml if needed

**LDAP Connection Issues**

*Cannot connect to LDAP server*:

   .. code-block:: bash

      # Test LDAP connection
      ldapsearch -H ldap://localhost:389 -D "cn=admin,ou=example,c=us" -w password123 -b "ou=example,c=us"

      # Check LDAP server status
      docker-compose exec ldap ldapsearch -x -b "ou=example,c=us"

*Authentication failures*:

   - Verify LDAP_BIND_DN and LDAP_BIND_PASSWORD
   - Check LDAP server logs
   - Ensure user exists in LDAP

**Database Issues**

*Migration errors*:

   .. code-block:: bash

      # Start the demo stack
      make dev

      # In another terminal
      make exec
      ./manage.py migrate

*Connection refused*:

   - Wait for database to fully start
   - Check database logs: `docker-compose logs db`

Development Workflow
--------------------

**Making Changes**

1. **Edit code** in the appropriate directory
2. **Test changes** locally or with Docker
3. **Run tests** to ensure nothing is broken
4. **Commit changes** with descriptive messages

**Adding New Features**

1. **Create models** in `demo/core/models.py`
2. **Add views** in `demo/core/views/`
3. **Create templates** in `demo/core/templates/`
4. **Add URL patterns** in `demo/core/urls.py`
5. **Write tests** in `demo/core/tests/`

**Database Changes**

1. **Create migrations**:

   .. code-block:: bash

      python manage.py makemigrations

2. **Apply migrations**:

   .. code-block:: bash

      python manage.py migrate

3. **For Docker**:

   .. code-block:: bash

      docker-compose exec web python manage.py makemigrations
      docker-compose exec web python manage.py migrate

Performance Tuning
------------------

**Database Optimization**

- Use database indexes for frequently queried fields
- Optimize LDAP queries with proper filters
- Use connection pooling for LDAP connections

**Caching**

- Enable Django caching for frequently accessed data
- Cache LDAP query results where appropriate
- Use Redis for session storage in production

**Monitoring**

- Monitor LDAP connection performance
- Track database query performance
- Monitor application response times

Security Considerations
-----------------------

**Production Deployment**

- Use HTTPS in production
- Secure LDAP connections with LDAPS
- Implement proper authentication and authorization
- Use environment variables for sensitive data
- Regular security updates

**LDAP Security**

- Use strong passwords for LDAP bind accounts
- Implement LDAP access controls
- Monitor LDAP access logs
- Use LDAPS for encrypted connections

**Application Security**

- Keep Django and dependencies updated
- Use Django's security middleware
- Implement proper input validation
- Use HTTPS for all communications

Cleanup
-------

**Stop Docker services**:

   .. code-block:: bash

      cd sandbox
      make docker-clean