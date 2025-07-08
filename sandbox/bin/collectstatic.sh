#!/usr/bin/env bash
# This script exists to simplify the repeated task of re-running collectstatic while developing css/js.
python /app/manage.py collectstatic --no-input -v0 --link
