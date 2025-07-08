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
make dev-detached
make exec
> ./manage.py migrate
```

### Getting to the demo app in your browser

You should now be able to browse to the demo app on https://localhost/ .
