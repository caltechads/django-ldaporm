#!/bin/bash

# Load the base LDIF data
echo "Loading LDIF data..."
ldapadd -H ldap://localhost:389 -D "cn=Directory Manager" -w password -f 01-base.ldif

echo "LDIF data loaded successfully!"