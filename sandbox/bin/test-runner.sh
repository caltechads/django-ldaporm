#!/usr/bin/env bash
# This script exists to simplify running the tests. Just like normal testing, you can pass a dotted path to it to
# run a specific subset of tests.
DEVELOPMENT=False TESTING=True python /app/manage.py test $@
