#!/usr/bin/env python
from setuptools import setup, find_packages

with open("README.md", "r", encoding='utf-8') as fh:
    long_description = fh.read()

setup(
    name='django-ldaporm',
    version='1.0.20',
    description='A Django ORM-like interface for ldap objectclasses',
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords=['django', 'ldap'],
    author="Caltech IMSS ADS",
    author_email="imss-ads-staff@caltech.edu",
    url='https://github.com/caltechads/django-ldaporm',
    packages=find_packages(exclude=['bin']),
    include_package_data=True,
    package_data={'ldaporm': ["py.typed"]},
    install_requires=[
        'pytz',
        'ldap_filter',
        'python-ldap',
    ],
    classifiers=[
        "Programming Language :: Python :: 3"
    ],
)
