from base64 import b64encode as encode
from collections import namedtuple
from distutils.version import StrictVersion
from functools import wraps
import hashlib
import logging
import os
import re
import threading

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

import ldap
from ldap import modlist
from ldap.controls import SimplePagedResultsControl
from ldap_filter import Filter


LDAP24API = StrictVersion(ldap.__version__) >= StrictVersion('2.4')
logger = logging.getLogger('django-ldaporm')


# -----------------------
# Decorators
# -----------------------

def log_prefix(prefix):

    def real_decorator(func):
        @wraps(func)
        def wrapper(self, level, msg, args, **kwargs):
            msg = prefix + " " + msg
            return func(level, msg, args, **kwargs)
        return wrapper
    return real_decorator


def atomic(key='read'):
    """
    Use this decorator to wrap methods that actually need to talk to an LDAP
    server.

    ``key`` is either "read" or "write".

    If 'key' is "read", do this operation on the LDAP server we've designated
    as our read-only server.

    If 'key' is "write", do this operation on the LDAP server we've designated
    as our read-write server.
    """
    def real_decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # add the LDAP server url to our logging context
            if self.has_connection():
                # Ensure we're not currently in a wrapped function
                return func(self, *args, **kwargs)
            else:
                old_log_method = self.logger._log
                self.logger._log = log_prefix(f"ldap_url={self.config[key]['url']}")(old_log_method)
                self.connect(key)
                try:
                    retval = func(self, *args, **kwargs)
                finally:
                    # We do this in a finally: branch so that the ldap
                    # connection and logger gets cleaned up no matter what
                    # happens in func()
                    self.disconnect()
                    self.logger._log = old_log_method
                return retval
        return wrapper
    return real_decorator


def substitute_pk(func):
    """
    Certain LdapManager() methods allow you to use the kwarg "pk".  Replace
    that with self.pk before passing into the method.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        kw = {}
        for key, value in kwargs.items():
            if key == 'pk':
                key = self.pk
            kw[key] = value
        return func(self, *args, **kw)
    return wrapper


def needs_manager(func):
    """
    Certain F() methods need an LdapManager class in order to function correctly.

    Raise an exception if we our F() instance has no LdapManager class.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.manager:
            raise self.UnboundFilter('This F() instance is not bound to an LdapManager.')
        return func(self, *args, **kwargs)
    return wrapper


def needs_pk(func):
    """
    When we retrieve data from LDAP, in most cases we want to ensure we include
    the primary key for the object in our returned attributes so that we can
    later do .save() and .delete() on it.

    This decorator adds self.manager.pk to self._attributes before
    executing the LDAP search.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        pk_attr = self.get_attribute(self.manager.pk)
        if pk_attr not in self._attributes:
            self._attributes.append(pk_attr)
        return func(self, *args, **kwargs)
    return wrapper


# -----------------------
# Helper Classes
# -----------------------


class Modlist:

    def __init__(self, manager):
        self.manager = manager

    def _get_modlist(self, data, modtype=ldap.MOD_REPLACE):
        modlist = []
        for key in data.keys():
            if modtype == ldap.MOD_DELETE:
                val = None
            else:
                val = data[key]
            if modtype == ldap.MOD_ADD:
                ntup = tuple([key, val])
            else:
                ntup = tuple([modtype, key, val])
            modlist.append(ntup)
        return modlist

    def add(self, obj):
        """
        Convert an LDAP DAO object to a modlist suitable for passing to
        `add_s` and return it.
        """
        data = obj.to_db()
        if hasattr(obj, 'objectclass'):
            data[1]['objectclass'] = obj.objectclass
        else:
            raise ImproperlyConfigured("Tried to add an object with no objectclasses defined.")
        # purge the empty fields
        _attribute_lookup = self.manager.model._meta.attribute_to_field_name_map
        _fields_map = self.manager.model._meta.fields_map
        new = {}
        for key, value in data[1].items():
            field = _fields_map[_attribute_lookup[key]]
            if not field.editable and not key == 'objectclass':
                continue
            if value != []:
                new[key] = value
        # return modlist.addModlist((data[0], new))
        return modlist.addModlist(new)

    def update(self, new, old, force=False):
        """
        We do our own implementation of `ldap.modify.modifyModlist` here because
        python-ldap explicitly says:

            Replacing attribute values is always done with a
            ldap.MOD_DELETE/ldap.MOD_ADD pair instead of ldap.MOD_REPLACE to
            work-around potential issues with attributes for which no EQUALITY
            matching rule are defined in the server’s subschema.

            (see https://www.python-ldap.org/en/latest/reference/ldap-modlist.html)

        Our version figures out whether to ldap.MOD_DELETE or ldap.MOD_REPLACE
        based on whether the value is empty.  This is needed by the 389 family
        servers because they now enforce rules for attributes that are optional
        but can't have a null value.

        :param new: the data for the object we have
        :type new: an LDAP ORM object

        :param old: the data for the object currently in LDAP
        :type old: an LDAP ORM object

        :rtype: list
        """
        # first build the changed attributes
        _attribute_lookup = self.manager.model._meta.attribute_to_field_name_map
        _fields_map = self.manager.model._meta.fields_map
        old_data = old.to_db()
        new_data = new.to_db()
        changes = {}
        for key, value in new_data[1].items():
            field = _fields_map[_attribute_lookup[key]]
            if not field.editable:
                continue

            if old_data[1][key] != value:
                changes[key] = value

        # Now build the ldap.MOD_DELETE and ldap.MOD_REPLACE modlists
        deletes = {}
        replacements = {}
        for key, value in changes.items():
            if value == []:
                deletes[key] = None
            else:
                replacements[key] = value
        d_modlist = self._get_modlist(deletes, ldap.MOD_DELETE)
        r_modlist = self._get_modlist(replacements, ldap.MOD_REPLACE)
        return r_modlist + d_modlist


# ========================================
# The LDAP search filter QuerySet analog
# ========================================


class F:

    # need to be able to specify field name and lookup db_column in LDAP

    class NoFilterSpecified(Exception):
        pass

    class UnknownSuffix(Exception):
        pass

    class UnboundFilter(Exception):
        pass

    def __init__(self, manager=None, f=None):
        self.manager = manager
        self.model = manager.model
        self.fields_map = self.manager.model._meta.fields_map
        self.attributes_map = self.manager.model._meta.attributes_map
        self.attribute_to_field_name_map = self.manager.model._meta.attribute_to_field_name_map
        self.attributes = self.manager.model._meta.attributes
        self._attributes = self.attributes
        self._order_by = self.manager.model._meta.ordering
        if f:
            self.chain = f.chain
        else:
            self.chain = []

    @property
    def _filter(self):
        """
        Return a list of filters ready to be converted to a filter string.

        This means throwing an "(& )" around the list of filter components
        we've accrued.
        """
        if len(self.chain) == 0:
            raise self.NoFilterSpecified('You need to at least specify one filter in order to do LDAP searches.')
        elif len(self.chain) == 1:
            return self.chain[0]
        else:
            return Filter.AND(self.chain).simplify()

    @needs_manager
    def __sort(self, objects):
        """
        This is called by methods that return lists of results.  Sort our
        ``objects``, a list of objects of class ``self.mangaer.model`` based
        on ``self._order_by``.

        Example::

            self.__sort(objects, ('-pub_date', 'headline',))

        The result above will be ordered by ``pub_date`` descending, then by
        ``headline ascending``. The negative sign in front of "-pub_date" indicates
        descending order.
        """
        if not self._order_by:
            return objects
        if not any([k.startswith('-') for k in self._order_by]):
            # if none of the keys are reversed, just sort directly
            return sorted(objects, key=lambda obj: tuple(getattr(obj, k) for k in self._order_by))
        else:
            # At least one key was reversed. now we have to do it the hard way,
            # with sequential sorts, starting from the last sort key and working
            # our way back to the first
            keys = list(self._order_by)
            keys.reverse()
            for k in keys:
                key = k
                reverse = False
                if key.startswith('-'):
                    key = k[1:]
                    reverse = True
                data = sorted(objects, key=lambda obj: getattr(obj, key), reverse=reverse)
            return data

    def __validate_positional_args(self, args):
        if args:
            for arg in args:
                if not isinstance(arg, F):
                    raise ValueError(
                        "F.filter() positional arguments must all be F() objects.".format(self.manager.model.__name__)
                    )
            steps = all(args)
        else:
            steps = []
        return steps

    def get_attribute(self, name):
        try:
            return self.attributes_map[name]
        except KeyError:
            raise self.manager.model.InvalidField(
                '"{}" is not a valid field on model {}'.format(name, self.manager.model.__name__)
            )

    def wildcard(self, name, value):
        """
        Convert ``value`` with some "*" in it (beginning, end or both) to
        appropriate LDAP filters ("__iendswith", "__istartswith" or
        "__icontains"), apply the the filter to our current state and return the
        result.

        If there are no "*" characters at the beginning or end of ``value`` do
        an "__iexact"" filter.

        :param name: the the name of one of the fields on our model
        :type name: string

        :param value: the keyword to look for
        :type value: string

        :rtype: a core.ldap.managers.F object
        """
        value = value.strip()
        f = self
        if value:
            if value.startswith('*') and value.endswith('*'):
                qualifier = "{}__icontains".format(name)
            elif value.startswith('*'):
                qualifier = "{}__iendswith".format(name)
            elif value.endswith('*'):
                qualifier = "{}__istartswith".format(name)
            else:
                qualifier = "{}__iexact".format(name)
            d = {qualifier: re.sub(r'[*]', '', value)}
            f = self.filter(**d)
        return f

    def filter(self, *args, **kwargs):
        """
        If there are positional arguments, they must all be F() objects.  This
        allows us to preconstruct an unbound filter and then use it later.

        Of the Django filter suffixes we support the following:

            * ``__iexact``
            * ``__istartswith``
            * ``__iendswith``
            * ``__icontains``
            * ``__in``

        Note that only the case insensitive versions of these filters are supported.
        LDAP searches are case insensitive, so we make you use ``__i*`` versions to
        remind you of that.

        We do support one additional LDAP specific filter: ``__exists``.  This
        will cause a filter to be added that just ensures that the returned
        objects have the associated attribute.  Unlike in SQL, where every row
        contains all available columns, in LDAP, attributes can be absent
        entirely from the record.
        """
        steps = self.__validate_positional_args(args)
        for key, value in kwargs.items():
            if isinstance(value, str):
                value = value.strip()
            if key.endswith('__istartswith'):
                steps.append(Filter.attribute(self.get_attribute(key[:-13])).starts_with(value))
            elif key.endswith('__iendswith'):
                steps.append(Filter.attribute(self.get_attribute(key[:-11])).ends_with(value))
            elif key.endswith('__icontains'):
                steps.append(Filter.attribute(self.get_attribute(key[:-11])).contains(value))
            elif key.endswith('__in'):
                if not isinstance(value, list):
                    raise ValueError('When using the "__in" filter you must supply a list')
                in_steps = []
                for v in value:
                    in_steps.append(Filter.attribute(self.get_attribute(key[:-4])).equal_to(v))
                steps.append(Filter.OR(in_steps))
            elif key.endswith('__exists'):
                # This one doesn't exist as a Django field lookup
                steps.append(Filter.attribute(self.get_attribute(key[:-8])).present())
            elif key.endswith('__iexact') or '__' not in key:
                # no suffix means do an __exact
                if '__' in key:
                    key = key[:-8]
                if value is None:
                    # If value is None, we search for the absence of that
                    # attribute
                    steps.append(Filter.NOT(Filter.attribute(self.get_attribute(key))))
                else:
                    steps.append(Filter.attribute(self.get_attribute(key)).equal_to(value))
            else:
                raise F.UnknownSuffix('The search filter "{}" uses an unknown filter suffix')
        self.chain.append(Filter.AND(steps))
        return self

    def only(self, *names):
        """
        Return an object with only these attributes.  Any attribute in the list which
        is not in the set of known attributes for our model will cause us to raise
        self.manager.model.InvalidField.

        For multiple calls to .only(), the last call wins.

        :param names: list of field names to retrieve from LDAP for this object
        :type names: list ot strings
        """
        self._attributes = [self.get_attribute(name) for name in names]
        return self

    @needs_manager
    @needs_pk
    def first(self):
        """
        The difference between .first() and .get() is that with .first() we know
        we might get more than one result, but we just want the first one.

        With .get() we expect that there should only be only one result and so if
        our search returns more, we want to know.

        .. note::

            If you'll don't have an .order_by() filter in your stack of filters,
            you'll get the first object from the search directly from LDAP.
            LDAP orders objects internally by insertion order, so you'll just
            get whatever the oldest object in LDAP is that matches your filters.
            But, this allows us to ask LDAP for just one object, which is fast.

            If you do have an .order_by() filter, you'll get the first object after
            sorting.  But LDAP servers won't do any sorting for you, so in this
            case we retrieve all objects matching our search filters and just return
            the first one, which may be expensive.
        """
        sizelimit = 0
        if not self._order_by:
            # We can just take the default LDAP ordering, so just take the first
            # result in whatever order the LDAP server keeps it in.
            sizelimit = 1
        objects = self.manager.search(str(self), self._attributes, sizelimit=sizelimit)
        if len(objects) == 0:
            raise self.manager.model.DoesNotExist(
                'A {} object matching query does not exist.'.format(self.manager.model.__name__))
        else:
            objects = self.manager.model.from_db(self._attributes, objects)
        if not self._order_by:
            return objects[0]
        else:
            return self.__sort(objects)[0]

    @needs_manager
    @needs_pk
    def get(self):
        objects = self.manager.search(str(self), self._attributes)
        if len(objects) == 0:
            raise self.manager.model.DoesNotExist(
                'A {} object matching query does not exist.'.format(self.manager.model.__name__))
        if len(objects) > 1:
            raise self.model.MultipleObjectsReturned(
                'More than one {} object matched query.'.format(self.model.__name__))
        return(self.manager.model.from_db(self._attributes, objects))

    @needs_manager
    @needs_pk
    def update(self, **kwargs):
        obj = self.get()
        new = self.manager.model.from_db(self._attributes, obj.dump())
        for key, value in kwargs.items():
            if key in self.manager.model.attributes:
                setattr(new, key, value)
        self.manager.modify(new, old=obj)

    @needs_manager
    def exists(self):
        """
        Return ``True`` if the LDAP search with the filter we've built returns
        any results, ``False`` if not.

        :rtype: boolean
        """
        objects = self.manager.search(str(self), self._attributes)
        if len(objects) > 0:
            return True
        else:
            return False

    @needs_manager
    @needs_pk
    def all(self):
        objects = self.manager.model.from_db(
            self._attributes,
            self.manager.search(str(self), self._attributes),
            many=True
        )
        return self.__sort(objects)

    @needs_manager
    def delete(self):
        """
        Delete an object that matches our filters.

        .. note::

            This works differently than Django's QuerySet .delete() function in
            that it will allow you to delete one and only one object from LDAP.
            The filters you pass should uniquely identify a single LDAP object.

            We do this to protect LDAP itself from our bugs.
        """
        obj = self.get()
        self.connection.delete_s(obj.dn)

    @needs_manager
    def order_by(self, *args):
        """
        When we return results, order them by the positional arguments
        Example::

            Entry.objects.order_by('-pub_date', 'headline').all()

        The result above will be ordered by ``pub_date`` descending, then by
        ``headline ascending``. The negative sign in front of "-pub_date" indicates
        descending order.
        """
        for key in args:
            _key = key[1:] if key.startswith('-') else key
            if _key not in self.attributes_map:
                raise self.manager.model.InvalidField(
                    '"{}" is not a valid field on model {}'.format(_key, self.manager.model.__name__)
                )
        self._order_by = args
        return self

    def values(self, *attrs):
        """
        Returns a a list of dictionaries, rather than of model instances.  Each
        of those dictionaries represents an object, with the keys corresponding
        to the attribute names of model objects.

            >>> Entry.objects.values('uid', 'sn')
            [{'uid': 'Barney', 'sn': 'Rubble'}, {'uid': 'Fred', 'sn': 'Flintstone'}, ...]

        The ``values()`` method takes optional positional arguments, ``*attrs``,
        which specify attribute names should be included in the dictionaries.
        If you specify the attributes, each dictionary will contain only the
        attribute keys/values for the fields you specify. If you don’t specify
        the attribute, each dictionary will contain a key and value for every
        attribute defined on the model.

        .. note::

            I'm trying to model how the Django ORM works here, so ``.values()``
            is not compatible with ``.only()``.  If previously in your filter
            chain you have an ``.only()``, you'll get  a ``NotImplementedError``
            exception.

        """
        if self._attributes != self.attributes:
            raise NotImplementedError("Don't use .only() with .values()")
        if not attrs:
            attrs = self.attributes
        objects = self.manager.model.from_db(attrs, self.manager.search(str(self), attrs), many=True)
        objects = self.__sort(objects)
        data = []
        for obj in objects:
            data.append({self.attribute_to_field_name_map[attr]: getattr(obj, attr) for attr in attrs})
        return data

    def values_list(self, *attrs, **kwargs):
        """
        This is similar to values() except that instead of returning
        dictionaries, it returns a list of tuples.  Each tuple contains
        the value from the respective field or expression passed into the
        ``values_list()`` call — so the first item is the first field, etc. For
        example::

            >>> Entry.objects.values_list('uid', 'sn')
            [('Barney', 'Rubble'), ('Fred', 'Flintstone'), ...]

        If you only pass in a single field, you can also pass in the ``flat``
        parameter. If ``True``, this will mean the returned results are a list
        of single values, rather than a list of one-tuples.

            >>> Entry.objects.values_list('uid', flat=True)
            ['barney', 'fred', ...]

        It is an error to pass in flat when there is more than one field.

        You can pass named=True to get results as a ``namedtuple()``.

            >>> Entry.objects.values_list('uid', named=True)
            [Row(uid='barney'), Row(uid='fred'), ...]

        .. note::

            I'm trying to model how the Django ORM works here, so ``.values()``
            is not compatible with ``.only()``.  If previously in your filter
            chain you have an ``.only()``, you'll get  a ``NotImplementedError``
            exception.
        """
        if self._attributes != self.attributes:
            raise NotImplementedError("Don't use .only() with .values_list()")
        if not attrs:
            attrs = self.attributes
        objects = self.manager.model.from_db(attrs, self.manager.search(str(self), attrs), many=True)
        objects = self.__sort(objects)
        data = []
        if 'flat' in kwargs and kwargs['flat']:
            if len(attrs) > 1:
                raise ValueError("Cannot use flat=True when asking for more than one field")
            else:
                return [getattr(obj, attrs[0]) for obj in objects]
        elif 'named' in kwargs and kwargs['named']:
            for obj in objects:
                Row = namedtuple('Row', attrs)
                # the keys here should be field names, not attribute names

                data.append(Row(**{self.attribute_to_field_name_map[attr]: getattr(obj, attr) for attr in attrs}))
            return data
        else:
            for obj in objects:
                data.append(tuple(getattr(obj, attr) for attr in attrs))
        return data

    def __or__(self, other):
        self.chain = Filter.OR([self._filter, other._filter])
        return F(manager=self.manager, f=self)

    def __and__(self, other):
        self.chain = Filter.AND([self._filter, other._filter])
        return F(manager=self.manager, f=self)

    def __str__(self):
        return self._filter.to_string()


# -----------------------
# LdapManager
# -----------------------


class LdapManager:

    def __init__(self):
        """
        This class does all of the direct interactions with LDAP and should be
        the only one that calls the ``ldap`` library functions.
        """
        self.logger = logger
        self.pagesize = 100

        # These get set during contribute_to_class()
        self.config = None
        self.model = None
        self.pk = None
        self.ldap_options = []
        self.objectclass = None
        self.extra_objectclasses = []

        # keys in this dictionary get manipulated by .connect() and
        # .disconnect()
        self._ldap_objects = {}

    def _get_pctrls(self, serverctrls):
        """
        Lookup an LDAP paged control object from the returned controls.
        """
        # Look through the returned controls and find the page controls.
        # This will also have our returned cookie which we need to make
        # the next search request.
        return [c for c in serverctrls if c.controlType == SimplePagedResultsControl.controlType]

    def _paged_search(self, basedn, searchfilter, attrlist=None, pagesize=100, sizelimit=0):
        """
        Performs a pages search against the LDAP server. Code lifted from:
        https://gist.github.com/mattfahrner/c228ead9c516fc322d3a
        """
        # Initialize the LDAP controls for paging. Note that we pass ''
        # for the cookie because on first iteration, it starts out empty.
        controls = SimplePagedResultsControl(True, size=pagesize, cookie='')

        # Do searches until we run out of pages to get from the LDAP server.
        results = []
        while True:
            # Send search request.
            msgid = self.connection.search_ext(
                basedn,
                ldap.SCOPE_SUBTREE,
                searchfilter,
                attrlist,
                serverctrls=[controls],
                sizelimit=sizelimit
            )
            rtype, rdata, rmsgid, serverctrls = self.connection.result3(msgid)
            # Each "rdata" is a tuple of the form (dn, attrs), where dn is
            # a string containing the DN (distinguished name) of the entry,
            # and attrs is a dictionary containing the attributes associated
            # with the entry. The keys of attrs are strings, and the associated
            # values are lists of strings.
            for dn, attrs in rdata:

                # AD returns an rdata at the end that is a reference that we want to ignore
                if type(attrs) == dict:
                    results.append((dn, attrs))


            # Get cookie for the next request.
            paged_controls = self._get_pctrls(serverctrls)
            if not paged_controls:
                self.logger.warning(
                    f'paged_search.rfc2696_control_ignored searchfilter={searchfilter}'
                    f'attrlist={",".join(attrlist)} pagesize={pagesize} sizelimit={sizelimit}'
                )
                break

            # Push cookie back into the main controls.
            controls.cookie = paged_controls[0].cookie

            # If there is no cookie, we're done!
            if not paged_controls[0].cookie:
                break
        return results

    def contribute_to_class(self, cls, accessor_name):
        self.pk = cls._meta.pk.name
        self.basedn = cls._meta.basedn
        self.objectclass = cls._meta.objectclass
        self.extra_objectclasses = cls._meta.extra_objectclasses
        self.ldap_options = cls._meta.ldap_options
        try:
            self.config = settings.LDAP_SERVERS[cls._meta.ldap_server]
        except AttributeError:
            raise ImproperlyConfigured("settings.LDAP_SERVERS does not exist!")
        except KeyError:
            raise ImproperlyConfigured(
                "'{}::{}': settings.LDAP_SERVERS has no key '{}', which was named by {}.service".format(
                    cls.__name__,
                    self.__name__,
                    self.service,
                    self.__name__
                )
            )

        if not self.basedn:
            try:
                self.basedn = self.config['basedn']
            except KeyError:
                raise ImproperlyConfigured(
                    "'{}::{}': no ``Meta.basedn`` and settings.LDAP_SERVERS['{}'] has no 'basedn' key".format(
                        cls.__name__,
                        self.__name__,
                        self.service
                    )
                )
        self.model = cls
        cls._meta.base_manager = self
        setattr(cls, accessor_name, self)

    def dn(self, obj):
        if not obj._dn:
            _attribute_lookup = obj._meta.attribute_to_field_name_map
            dn_key = self.pk
            for k, v in _attribute_lookup.items():
                if v == self.pk:
                    dn_key = k
                    break
            pk_value = getattr(obj, self.pk)
            if pk_value:
                obj._dn = "{}={},{}".format(dn_key, getattr(obj, self.pk), self.basedn)
            else:
                # If our pk_value is None or '', we're in the middle of creating a new record and haven't set
                # it yet.
                obj._dn = None
        return obj._dn

    def disconnect(self):
        self.connection.unbind_s()
        self.remove_connection()

    def has_connection(self):
        return threading.current_thread() in self._ldap_objects

    def set_connection(self, obj):
        self._ldap_objects[threading.current_thread()] = obj

    def remove_connection(self):
        del self._ldap_objects[threading.current_thread()]

    def connect(self, key, dn=None, password=None):
        config = self.config[key]
        if not dn:
            dn = config['user']
            password = config['password']
        ldap_object = ldap.initialize(config['url'])
        ldap_object.set_option(ldap.OPT_REFERRALS, 0)
        ldap_object.set_option(ldap.OPT_NETWORK_TIMEOUT, 15.0)
        ldap.set_option(ldap.OPT_X_TLS, ldap.OPT_X_TLS_ALLOW)
        ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
        ldap_object.start_tls_s()
        ldap_object.simple_bind_s(dn, password)
        self._ldap_objects[threading.current_thread()] = ldap_object

    @property
    def connection(self):
        return self._ldap_objects[threading.current_thread()]

    def _get_ssha_hash(self, password):
        salt = os.urandom(8)
        h = hashlib.sha1(password)
        h.update(salt)
        pwhash = "{SSHA}" + encode(h.digest() + salt)
        return pwhash

    @atomic(key='read')
    def search(self, searchfilter, attributes, sizelimit=0):
        if 'paged_search' in self.ldap_options:
            return self._paged_search(
                self.basedn,
                searchfilter,
                attrlist=attributes,
                sizelimit=sizelimit
            )
        else:
            # We have to filter out and references that AD puts in
            data = self.connection.search_s(
                self.basedn,
                ldap.SCOPE_SUBTREE,
                filterstr=searchfilter,
                attrlist=attributes
            )
            objects = []
            for obj in data:
                if type(obj[1]) == dict:
                    objects.append(obj)
            return objects

    @atomic(key='write')
    def add(self, obj):
        obj.objectclass = []
        for objectclass in self.extra_objectclasses:
            obj.objectclass.append(objectclass.encode())
        obj.objectclass.append(self.objectclass.encode())
        modlist = Modlist(self).add(obj)
        self.connection.add_s(self.dn(obj), modlist)

    @atomic(key='write')
    @substitute_pk
    def delete(self, *args, **kwargs):
        """
        Delete an object that matches our filters.

        .. note::

            This works differently than Django's QuerySet .delete() function in
            that it will allow you to delete one and only one object from LDAP.
            The filters you pass should uniquely identify a single LDAP object.

            We do this to protect LDAP itself from our bugs.
        """
        obj = self.filter(*args, **kwargs).only(self.pk).get()
        self.connection.delete_s(obj.dn)

    @atomic(key='write')
    def delete_obj(self, obj):
        """
        Delete a specified object.
        """

        self.connection.delete_s(obj.dn)

    @atomic(key='write')
    def rename(self, old_dn, new_dn):
        """
        Update an object's dn, keeping it within the same basedn.
        """
        newrdn = new_dn.split(',')[0]
        old_basedn = ','.join(old_dn.split(',')[1:])
        new_basedn = ','.join(new_dn.split(',')[1:])
        newsuperior = None
        if old_basedn != new_basedn:
            newsuperior = new_basedn
        self.connection.rename_s(old_dn, newrdn, newsuperior)

    @atomic(key='write')
    def modify(self, obj, old=None):
        # First check to see whether we updated our primary key.  If so, we need to rename
        # the object in LDAP, and its obj._dn.  The old obj._dn should reference the old PK.
        old_pk_value = obj.dn.split(',')[0].split('=')[1]
        new_pk_value = getattr(obj, self.pk)
        if new_pk_value != old_pk_value:
            # We need to do a modrdn_s if we change pk, to cause the dn to be updated also
            self.connection.modrdn_s(obj.dn, f'{self.pk}={new_pk_value}')
            # And update our object's _dn to the new one
            basedn = ','.join(obj.dn.split(',')[1:])
            new_dn = f'{self.pk}={new_pk_value},{basedn}'
            obj._dn = new_dn
            # force reload old, if it was passed in so that we get the new pk value and dn
            old = None

        # Now update the non-PK attributes
        if not old:
            old = self.get(**{self.pk: getattr(obj, self.pk)})
        modlist = Modlist(self).update(obj, old)
        if modlist:
            # Only issue the modify_s if we actually have changes
            self.connection.modify_s(obj.dn, modlist)
        else:
            self.logger.debug(f'ldaporm.manager.modify.no-changes dn={obj.dn}')

    def only(self, *names):
        return F(manager=self).attributes(names)

    def __filter(self):
        f = F(manager=self)
        if self.objectclass:
            f = f.filter(objectclass=self.objectclass)
        return f

    @substitute_pk
    def wildcard(self, name, value):
        if value:
            return self.__filter().wildcard(name, value)
        else:
            return self

    @substitute_pk
    def filter(self, *args, **kwargs):
        return self.__filter().filter(*args, **kwargs)

    @substitute_pk
    def get(self, *args, **kwargs):
        return self.__filter().filter(*args, **kwargs).get()

    def all(self):
        """
        .. note::

            Unlike the Django QuerySet version of this, this actually
            runs the query against LDAP and returns the result.  The Django
            version returns an iterator, I think.
        """
        return self.__filter().all()

    def values(self, *args):
        return self.__filter().values(*args)

    def values_list(self, *args, **kwargs):
        return self.__filter().values_list(*args, **kwargs)

    def order_by(self, *args):
        return self.__filter().order_by(*args)

    def reset_password(self, username, new_password, attributes={}):
        try:
            user = self.filter(**{'uid': username}).only('uid').get()
        except self.model.DoesNotExist:
            self.logger.warning(f'auth.no_such_user user={username}')
            return False

        if not attributes:
            attributes = self.model.get_reset_password_extra_attributes()

        password_attribute = getattr(self.model, 'password_attribute', None)
        if not password_attribute:
            return

        pwhash = self.model.get_password_hash(new_password)
        attr = {password_attribute: [pwhash]}
        attributes.update(attr)

        modlist = Modlist(self)._get_modlist(attr, ldap.MOD_REPLACE)

        self.connect('write')
        self.connection.modify_s(user.dn, modlist)
        self.disconnect()
        service = getattr(self.model._meta, 'ldap_server', 'ldap')
        self.logger.info(f'{service}.password_reset.success dn={user.dn}')
        return True

    def authenticate(self, username, password):
        """
        Try to authenticate a username/password vs our LDAP server.

        If the user does not exist in LDAP, return False.
        If the user exists, but the bind fails, return False.
        Else, return True.

        :param username: a bare username for the person trying to authenticate e.g. 'fred'
        :type username: string

        :param password: the password to try to authenticate with
        :type password: string

        :param remote_ip: if provided, include this IP address in our log messages
        :type remote_ip: string

        :rtype: boolean
        """

        try:
            # user = self.filter(**{self.pk: username}).only(self.pk).get()
            user = self.filter(**{'uid': username}).only('uid').get()
        except self.model.DoesNotExist:
            self.logger.warning(f'auth.no_such_user user={username}')
            return False
        try:
            self.connect('read', user.dn, password)
        except ldap.INVALID_CREDENTIALS:
            self.logger.warning('auth.invalid_credentials user={username}')
            return False
        self.disconnect()
        self.logger.info('auth.success user={username}')
        return True

    def create(self, **kwargs):
        """
        This differs from Django's QuerySet .create() in that it does not actually save
        the object to LDAP before returning it.
        """
        return self.model(**kwargs)
