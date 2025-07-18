# Sphinx Hosting Demo

This django application exists to test the `django-sphinx-hosting` module.

## Setting up to run the demo

## Set up your local virtualenv

The demo runs in Docker, so you will need Docker Desktop or equivalent installed
on your development machine.

### Build the Docker image

```bash
make build
```

### Run the service, and initialize the database

```bash
make exec
> ./manage.py migrate
```

### Initialize the LDAP server

```bash
make dev
# Wait for the LDAP server to configure itself, then Cntrl-D
make dev-detached
# The Django app will be unhappy because our basedn doesn't exist, so we need to do this
# and then load the data
docker exec -ti ldap bash
> dsconf localhost backend create --suffix "o=example,c=us" --be-name example
> ^D

# Now load the data
cd data/ldap/init
./load_data.sh

# Now restart the docker stack
make dev-down
make dev
```

#### Caveat

For whatever reason, I could not get `nsRole` attributes to appear on the user inside the 389-ds server.   I checked many things:

- The "Roles Plugin" is installed and enabled
- The roles we create have the proper object classes
- The `nsslapd-ignore-virtual-attrs` is automatically set to `off` (enabling `nsRole`, a virtual attribute, to be populated) when we load the role objects (you can see this in the ldap startup logs)
- The roles assigned to `nsRoleDN` on each user each have a `dn` that corresponds to an actual role object
- The `nsFilteredRoleDefinition` objects just don't seem to do anything

I assure you that in our production environment, all this works fine.

### Getting to the demo app in your browser

You should now be able to browse to the demo app on https://localhost/ .
