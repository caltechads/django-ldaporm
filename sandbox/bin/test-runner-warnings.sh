#!/usr/bin/env bash
# This is test-runner.py, but with all warnings enabled except ResourceWarning. That one is disabled because
# ElasticSearch spams the crap out of them, and it's not due to anything in our own code, so we can't fix it.
DEVELOPMENT=False TESTING=True python -bb -Wall -Wignore::ResourceWarning /app/manage.py test $@
