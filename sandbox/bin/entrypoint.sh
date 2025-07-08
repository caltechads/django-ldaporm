#!/usr/bin/env bash
set -e
/app/manage.py bootstrap
exec "$@"