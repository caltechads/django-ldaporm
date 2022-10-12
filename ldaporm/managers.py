from base64 import b64encode as encode
from collections import namedtuple
from distutils.version import StrictVersion
from functools import wraps
import hashlib
import logging
import os
import re
import threading
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple, Type, Sequence, cast

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

import ldap
from ldap import modlist
from ldap.controls import SimplePagedResultsControl
from ldap_filter import Filter


from .typing import ModifyDeleteModList, AddModlist, LDAPData

if TYPE_CHECKING:
    from ldap_filter.filter import GroupAnd
    from .models import Model
    from .options import Options  # noqa:F401

LDAP24API = StrictVersion(ldap.__version__) >= StrictVersion('2.4')
logger = logging.getLogger('django-ldaporm')


# -----------------------
# Decorators
# -----------------------

def log_prefix(prefix: str) -> Callable:

    def real_decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, level, msg, args, **kwargs) -> Callable:
            msg = prefix + " " + msg
            return func(level, msg, args, **kwargs)
        return wrapper
    return real_decorator


def atomic(key: str = 'read') -> Callable:
    """
    Use this decorator to wrap methods that actually need to talk to an LDAP
    server.

    ``key`` is either "read" or "write".

    If 'key' is "read", do this operation on the LDAP server we've designated
    as our read-only server.

    If 'key' is "write", do this operation on the LDAP server we've designated
    as our read-write server.
    """
    def real_decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs) -> Callable:
            # add the LDAP server url to our logging context
            if self.has_connection():
                # Ensure we're not currently in a wrapped function
                return func(self, *args, **kwargs)
            old_log_method = logging._log
            logging._log = log_prefix(f"ldap_url={self.config[key]['url']}")(old_log_method)
            self.connect(key)
            try:
                retval = func(self, *args, **kwargs)
            finally:
                # We do this in a finally: branch so that the ldap
                # connection and logger gets cleaned up no matter what
                # happens in func()
                self.disconnect()
                logging._log = old_log_method
            return retval
        return wrapper
    return real_decorator


def substitute_pk(func: Callable) -> Callable:
    """
    Certain LdapManager() methods allow you to use the kwarg "pk".  Replace
    that with self.pk before passing into the method.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs) -> Callable:
        kw = {}
        for key, value in kwargs.items():
            if key == 'pk':
                key = self.pk
            kw[key] = value
        return func(self, *args, **kw)
    return wrapper


def needs_pk(func: Callable) -> Callable:
    """
    When we retrieve data from LDAP, in most cases we want to ensure we include
    the primary key for the object in our returned attributes so that we can
    later do .save() and .delete() on it.

    This decorator adds self.manager.pk to self._attributes before
    executing the LDAP search.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs) -> Callable:
        pk_attr = self.get_attribute(self.manager.pk)
        if pk_attr not in self._attributes:
            self._attributes.append(pk_attr)
        return func(self, *args, **kwargs)
    return wrapper


# -----------------------
# Helper Classes
# -----------------------


class Modlist:

    def __init__(self, manager: "LdapManager") -> None:
        self.manager = manager

    def _get_modlist(self, data: Dict[str, Any], modtype: int = ldap.MOD_REPLACE) -> ModifyDeleteModList:
        _modlist: ModifyDeleteModList = []
        for key in data:
            if modtype == ldap.MOD_DELETE:
                _modlist.append((ldap.MOD_DELETE, key, None))
            elif modtype == ldap.MOD_ADD:
                _modlist.append((key, data[key]))
            else:
                _modlist.append((cast(int, modtype), key, data[key]))
        return _modlist

    def add(self, obj: "Model") -> AddModlist:
        """
        Convert an LDAP DAO object to a modlist suitable for passing to
        `add_s` and return it.
        """
        data = obj.to_db()
        if hasattr(obj, 'objectclass'):
            data[1]['objectclass'] = obj.objectclass  # type: ignore
        else:
            raise ImproperlyConfigured("Tried to add an object with no objectclasses defined.")
        # We have to do these two casts because LdapManager.model and
        # Model._meta start out as None.  By the time we get here the metaclass
        # has filled in those two so we know they're not None, but mypy has no
        # way of knowing that
        model = cast("Model", self.manager.model)
        _meta = cast("Options", model._meta)
        _attribute_lookup = _meta.attribute_to_field_name_map
        _fields_map = _meta.fields_map
        # purge the empty fields
        new = {}
        for key, value in data[1].items():
            field = _fields_map[_attribute_lookup[key]]
            if not field.editable and not key == 'objectclass':
                continue
            if value != []:
                new[key] = value
        return modlist.addModlist(new)

    def update(self, new: "Model", old: "Model", force: bool = False) -> ModifyDeleteModList:
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
        # We have to do these two casts because LdapManager.model and
        # Model._meta start out as None.  By the time we get here the metaclass
        # has filled in those two so we know they're not None, but mypy has no
        # way of knowing that
        model = cast("Model", self.manager.model)
        _meta = cast("Options", model._meta)
        _attribute_lookup = _meta.attribute_to_field_name_map
        _fields_map = _meta.fields_map
        # first build the changed attributes
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
        deletes: Dict[str, Any] = {}
        replacements: Dict[str, Any] = {}
        for key, value in changes.items():
            if value == [] or all(x is None for x in value):
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

    def __init__(self, manager: "LdapManager", f: "F" = None) -> None:
        self.manager = manager
        self.model = cast(Type["Model"], manager.model)
        self._meta = cast("Options", self.model._meta)
        self.fields_map = self._meta.fields_map
        self.attributes_map = self._meta.attributes_map
        self.attribute_to_field_name_map = self._meta.attribute_to_field_name_map
        self.attributes = self._meta.attributes
        self._attributes = self.attributes
        self._order_by = self._meta.ordering
        if f:
            self.chain: List["F"] = f.chain
        else:
            self.chain = []

    @property
    def _filter(self) -> "GroupAnd":
        """
        Return a list of filters ready to be converted to a filter string.

        This means throwing an "(& )" around the list of filter components
        we've accrued.
        """
        if len(self.chain) == 0:
            raise self.NoFilterSpecified('You need to at least specify one filter in order to do LDAP searches.')
        if len(self.chain) == 1:
            return self.chain[0]
        return Filter.AND(self.chain).simplify()

    def __sort(self, objects: Sequence["Model"]) -> Sequence["Model"]:
        """
        This is called by methods that return lists of results.  Sort our
        ``objects``, a list of objects of class ``self.manager.model`` based
        on ``self._order_by``.

        Example::

            self.__sort(objects, ('-pub_date', 'headline',))

        The result above will be ordered by ``pub_date`` descending, then by
        ``headline ascending``. The negative sign in front of "-pub_date" indicates
        descending order.
        """
        if not self._order_by:
            return objects
        if not any(k.startswith('-') for k in self._order_by):
            # if none of the keys are reversed, just sort directly
            return sorted(objects, key=lambda obj: tuple(getattr(obj, k) for k in self._order_by))
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
            data = sorted(
                objects,
                key=lambda obj: getattr(obj, key),  # pylint: disable=cell-var-from-loop
                reverse=reverse
            )
        return data

    def __validate_positional_args(self, args: Sequence["F"]) -> List["F"]:
        if args:
            for arg in args:
                if not isinstance(arg, F):
                    raise ValueError(
                        "F.filter() positional arguments must all be F() objects."
                    )
        return list(args)

    def get_attribute(self, name: str) -> str:
        try:
            return self.attributes_map[name]
        except KeyError:
            raise self.model.InvalidField(
                '"{}" is not a valid field on model {}'.format(name, self.model.__name__)
            )

    def wildcard(self, name: str, value: str) -> "F":
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

    def filter(self, *args: "F", **kwargs) -> "F":
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

    def only(self, *names) -> "F":
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

    @needs_pk
    def first(self) -> "Model":
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
            raise self.model.DoesNotExist(
                'A {} object matching query does not exist.'.format(self.model.__name__))
        objects = self.model.from_db(self._attributes, objects)
        if not self._order_by:
            return objects[0]
        return self.__sort(objects)[0]

    @needs_pk
    def get(self) -> "Model":
        objects = self.manager.search(str(self), self._attributes)
        if len(objects) == 0:
            raise self.model.DoesNotExist(
                'A {} object matching query does not exist.'.format(self.model.__name__))
        if len(objects) > 1:
            raise self.model.MultipleObjectsReturned(
                'More than one {} object matched query.'.format(self.model.__name__))
        return cast("Model", self.model.from_db(self._attributes, objects))

    @needs_pk
    def update(self, **kwargs) -> None:
        obj = self.get()
        # FIXME: obj.dump() does not exist;
        new = self.model.from_db(self._attributes, obj.dump())
        for key, value in kwargs.items():
            if key in self.attributes:
                setattr(new, key, value)
        self.manager.modify(new, old=obj)

    def exists(self) -> bool:
        """
        Return ``True`` if the LDAP search with the filter we've built returns
        any results, ``False`` if not.

        :rtype: boolean
        """
        objects = self.manager.search(str(self), self._attributes)
        return len(objects) > 0

    @needs_pk
    def all(self) -> Sequence["Model"]:
        objects = self.model.from_db(
            self._attributes,
            self.manager.search(str(self), self._attributes),
            many=True
        )
        return self.__sort(cast(Sequence["Model"], objects))

    def delete(self) -> None:
        """
        Delete an object that matches our filters.

        .. note::

            This works differently than Django's QuerySet .delete() function in
            that it will allow you to delete one and only one object from LDAP.
            The filters you pass should uniquely identify a single LDAP object.

            We do this to protect LDAP itself from our bugs.
        """
        obj = self.get()
        self.manager.connection.delete_s(obj.dn)

    def order_by(self, *args: str) -> "F":
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
                raise self.model.InvalidField(
                    '"{}" is not a valid field on model {}'.format(_key, self.model.__name__)
                )
        self._order_by = list(args)
        return self

    def values(self, *attrs: str) -> List[Dict[str, Any]]:
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
        _attrs = []
        if not attrs:
            _attrs = self.attributes
        objects = self.model.from_db(_attrs, self.manager.search(str(self), _attrs), many=True)
        objects = self.__sort(cast(Sequence["Model"], objects))
        data = []
        for obj in objects:
            data.append({self.attribute_to_field_name_map[attr]: getattr(obj, attr) for attr in _attrs})
        return data

    def values_list(self, *attrs: str, **kwargs) -> List[Tuple[Any, ...]]:
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

        _attrs: List[str] = []
        if not attrs:
            _attrs = self.attributes
            attrs = tuple(self.attribute_to_field_name_map[attr] for attr in _attrs)
        else:
            _attrs = [self.get_attribute(attr) for attr in attrs]
        objects = self.model.from_db(_attrs, self.manager.search(str(self), _attrs), many=True)
        objects = self.__sort(cast(Sequence["Model"], objects))
        if 'flat' in kwargs and kwargs['flat']:
            if len(attrs) > 1:
                raise ValueError("Cannot use flat=True when asking for more than one field")
            return [getattr(obj, attrs[0]) for obj in objects]
        if 'named' in kwargs and kwargs['named']:
            rows: List[Any] = []
            for obj in objects:
                Row = namedtuple('Row', attrs)  # type: ignore
                # the keys here should be field names, not attribute names
                rows.append(Row(**{attr: getattr(obj, attr) for attr in attrs}))
            return rows
        data: List[Tuple[str, ...]] = []
        for obj in objects:
            data.append(tuple(getattr(obj, attr) for attr in attrs))
        return data

    def __or__(self, other: "F") -> "F":
        self.chain = Filter.OR([self._filter, other._filter])
        return F(self.manager, f=self)

    def __and__(self, other: "F") -> "F":
        self.chain = Filter.AND([self._filter, other._filter])
        return F(self.manager, f=self)

    def __str__(self) -> str:
        return self._filter.to_string()


# -----------------------
# LdapManager
# -----------------------


class LdapManager:

    def __init__(self) -> None:
        """
        This class does all of the direct interactions with LDAP and should be
        the only one that calls the ``ldap`` library functions.
        """
        logging = logger
        self.pagesize: int = 100

        # These get set during contribute_to_class()
        # self.config is the part of settings.LDAP_SERVERS that we need for our Model
        self.config: Optional[Dict[str, Any]] = None
        self.model: Optional[Type["Model"]] = None
        self.pk: Optional[str] = None
        self.ldap_options: List[str] = []
        self.objectclass: Optional[str] = None
        self.extra_objectclasses: List[str] = []

        # keys in this dictionary get manipulated by .connect() and
        # .disconnect()
        self._ldap_objects: Dict[threading.Thread, ldap.ldapobject.LDAPObject] = {}

    def _get_pctrls(self, serverctrls):
        """
        Lookup an LDAP paged control object from the returned controls.
        """
        # Look through the returned controls and find the page controls.
        # This will also have our returned cookie which we need to make
        # the next search request.
        return [c for c in serverctrls if c.controlType == SimplePagedResultsControl.controlType]

    def _paged_search(
        self,
        basedn: str,
        searchfilter: str,
        attrlist: List[str] = None,
        pagesize: int = 100,
        sizelimit: int = 0,
        scope: int = ldap.SCOPE_SUBTREE
    ) -> List[LDAPData]:
        """
        Performs a pages search against the LDAP server. Code lifted from:
        https://gist.github.com/mattfahrner/c228ead9c516fc322d3a
        """
        # Initialize the LDAP controls for paging. Note that we pass ''
        # for the cookie because on first iteration, it starts out empty.
        controls = SimplePagedResultsControl(True, size=pagesize, cookie='')

        # Do searches until we run out of pages to get from the LDAP server.
        results: List[LDAPData] = []
        while True:
            # Send search request.
            msgid = self.connection.search_ext(
                basedn,
                scope,
                searchfilter,
                attrlist,
                serverctrls=[controls],
                sizelimit=sizelimit
            )
            rtype, rdata, rmsgid, serverctrls = self.connection.result3(msgid)  # pylint: disable=unused-variable
            # Each "rdata" is a tuple of the form (dn, attrs), where dn is
            # a string containing the DN (distinguished name) of the entry,
            # and attrs is a dictionary containing the attributes associated
            # with the entry. The keys of attrs are strings, and the associated
            # values are lists of strings.
            for dn, attrs in rdata:

                # AD returns an rdata at the end that is a reference that we want to ignore
                if isinstance(attrs, dict):
                    results.append((dn, attrs))

            # Get cookie for the next request.
            paged_controls = self._get_pctrls(serverctrls)
            if not paged_controls:
                msg = f'paged_search.rfc2696_control_ignored searchfilter={searchfilter} attrlist={attrlist} pagesize={pagesize} sizelimit={sizelimit}'
                logging.warning(msg)
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
                "{}: settings.LDAP_SERVERS has no key '{}'".format(
                    cls.__name__,
                    cls._meta.ldap_server,
                )
            )

        if not self.basedn:
            try:
                self.basedn = self.config['basedn']
            except KeyError:
                raise ImproperlyConfigured(
                    "{}: no ``Meta.basedn`` and settings.LDAP_SERVERS['{}'] has no 'basedn' key".format(
                        cls.__name__,
                        cls._meta.ldap_server
                    )
                )
        self.model = cls
        cls._meta.base_manager = self
        setattr(cls, accessor_name, self)

    def __get_dn_key(self, meta: "Options"):
        _attribute_lookup = meta.attribute_to_field_name_map
        dn_key = self.pk
        for k, v in _attribute_lookup.items():
            if v == self.pk:
                dn_key = k
                break
        return dn_key

    def dn(self, obj: "Model") -> Optional[str]:
        if not obj._dn:
            dn_key = self.__get_dn_key(cast("Options", obj._meta))
            pk_value = getattr(obj, cast(str, self.pk))
            if pk_value:
                obj._dn = "{}={},{}".format(dn_key, getattr(obj, cast(str, self.pk)), self.basedn)
            else:
                # If our pk_value is None or '', we're in the middle of creating a new record and haven't set
                # it yet.
                obj._dn = None
        return obj._dn

    def get_dn(self, pk: str) -> str:
        """
        Given a value for an object primary key, return what the dn for that
        object would look like.

        Args:
            pk: the value for the primary key for our model

        Returns:
            A fully qualified dn.
        """
        meta = cast("Options", cast("Model", self.model)._meta)
        dn_key = self.__get_dn_key(meta)
        return "{}={},{}".format(dn_key, pk, self.basedn)

    def disconnect(self) -> None:
        self.connection.unbind_s()
        self.remove_connection()

    def has_connection(self) -> bool:
        return threading.current_thread() in self._ldap_objects

    def set_connection(self, obj: ldap.ldapobject.LDAPObject) -> None:
        self._ldap_objects[threading.current_thread()] = obj

    def remove_connection(self) -> None:
        del self._ldap_objects[threading.current_thread()]

    def _connect(
        self,
        key: str,
        dn: str = None,
        password: str = None
    ) -> ldap.ldapobject.LDAPObject:
        config = cast(Dict[str, Any], self.config)[key]
        if not dn:
            dn = config['user']
            password = config['password']
        ldap_object: ldap.ldapobject.LDAPObject = ldap.initialize(config['url'])
        ldap_object.set_option(ldap.OPT_REFERRALS, 0)
        ldap_object.set_option(ldap.OPT_NETWORK_TIMEOUT, 15.0)
        ldap_object.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
        ldap_object.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
        ldap_object.start_tls_s()
        ldap_object.simple_bind_s(dn, password)
        return ldap_object

    def connect(
        self,
        key: str,
        dn: str = None,
        password: str = None
    ) -> None:
        """
        This is used internally to set our per-thread connection object.  It is primarily used by
        the ``@atomic`` decorator.

        Args:
            key: A key into our ``self.settings`` configuration object.  This
                holds has hostname, bind dn, password and basedn for our read-only
                and read-write servers.

        Keyword Args:
            dn: If provided, use this as our bind dn instead of the dn in our ``self.settings``
                configuration object.
            password: If provided, use this as our password instead of the
                password in our ``self.settings`` configuration object.

        """
        self._ldap_objects[threading.current_thread()] = self._connect(key, dn=dn, password=password)

    def new_connection(
        self,
        key: str = 'read',
        dn: str = None,
        password: str = None
    ) -> ldap.ldapobject.LDAPObject:
        """
        This is used internally to set our per-thread connection object.  It is primarily used by
        the ``@atomic`` decorator.

        Keyword Args:
            key: A key into our ``self.settings`` configuration object.  This
                holds has hostname, bind dn, password and basedn for our read-only
                and read-write servers.
            dn: If provided, use this as our bind dn instead of the dn in our ``self.settings``
                configuration object.
            password: If provided, use this as our password instead of the
                password in our ``self.settings`` configuration object.

        Returns:
            A properly connected python-ldap ``LDAPObject``.
        """
        return self._connect(key, dn=dn, password=password)

    @property
    def connection(self) -> ldap.ldapobject.LDAPObject:
        return self._ldap_objects[threading.current_thread()]

    def _get_ssha_hash(self, password: str) -> bytes:
        salt = os.urandom(8)
        h = hashlib.sha1(password.encode('utf-8'))
        h.update(salt)
        pwhash = "{SSHA}".encode('utf-8') + encode(h.digest() + salt)
        return pwhash

    @atomic(key='read')
    def search(
        self,
        searchfilter: str,
        attributes: List[str],
        sizelimit: int = 0,
        basedn: str = None,
        scope: int = ldap.SCOPE_SUBTREE
    ) -> List[LDAPData]:
        if basedn is None:
            basedn = self.basedn
        if 'paged_search' in self.ldap_options:
            return self._paged_search(
                basedn,
                searchfilter,
                attrlist=attributes,
                sizelimit=sizelimit,
                scope=scope
            )
        # We have to filter out and references that AD puts in
        data = self.connection.search_s(
            basedn,
            scope,
            filterstr=searchfilter,
            attrlist=attributes
        )
        objects = []
        for obj in data:
            if isinstance(obj[1], dict):
                objects.append(obj)
        return objects

    @atomic(key='write')
    def add(self, obj: "Model") -> None:
        # This is a bit weird here because the objectclass CharListField gets
        # secretly added during class construction on Model
        obj.objectclass = []  # type: ignore
        for objectclass in self.extra_objectclasses:
            obj.objectclass.append(objectclass.encode())  # type: ignore
        obj.objectclass.append(self.objectclass.encode())  # type: ignore
        _modlist = Modlist(self).add(obj)
        self.connection.add_s(self.dn(obj), _modlist)

    @atomic(key='write')
    @substitute_pk
    def delete(self, *args, **kwargs) -> None:
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
    def delete_obj(self, obj: "Model") -> None:
        """
        Delete a specified object.
        """

        self.connection.delete_s(obj.dn)

    @atomic(key='write')
    def rename(self, old_dn: str, new_dn: str) -> None:
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
    def modify(self, obj: "Model", old: "Model" = None) -> None:
        # First check to see whether we updated our primary key.  If so, we need to rename
        # the object in LDAP, and its obj._dn.  The old obj._dn should reference the old PK.
        # We'll .lower() them to deal with case for the pk in the dn
        old_pk_value = cast(str, obj.dn).split(',')[0].split('=')[1].lower()
        new_pk_value = getattr(obj, cast(str, self.pk)).lower()
        if new_pk_value != old_pk_value:
            # We need to do a modrdn_s if we change pk, to cause the dn to be updated also
            self.connection.modrdn_s(obj.dn, f'{self.pk}={new_pk_value}')
            # And update our object's _dn to the new one
            basedn = ','.join(cast(str, obj.dn).split(',')[1:])
            new_dn = f'{self.pk}={new_pk_value},{basedn}'
            obj._dn = new_dn
            # force reload old, if it was passed in so that we get the new pk value and dn
            old = None

        # Now update the non-PK attributes
        if not old:
            pk_val = cast(str, self.pk)
            old = self.get(**{pk_val: getattr(obj, pk_val)})
        _modlist = Modlist(self).update(obj, cast("Model", old))
        if _modlist:
            # Only issue the modify_s if we actually have changes
            self.connection.modify_s(obj.dn, _modlist)
        else:
            logging.debug('ldaporm.manager.modify.no-changes dn=%s', obj.dn)

    def only(self, *names: str) -> "F":
        return F(self).only(*names)

    def __filter(self) -> "F":
        f = F(self)
        if self.objectclass:
            f = f.filter(objectclass=self.objectclass)
        return f

    @substitute_pk
    def wildcard(self, name: str, value: str) -> "F":
        return self.__filter().wildcard(name, value)

    @substitute_pk
    def filter(self, *args, **kwargs) -> "F":
        return self.__filter().filter(*args, **kwargs)

    def get_by_dn(self, dn: str) -> "Model":
        """
        Get an object specifically by its DN.  To do this we do a search with
        the basedn set to the dn of the object, with scope ``ldap.SCOPE_BASE``
        and then get all objects that match.  This will be either the object
        we're looking for, or nothing.

        Args:
            dn: the dn to search for

        Raises:
            ValueError: `dn` is not in our Model's basedn
            Model.DoesNotExist: no object with this dn exist in our LDAP server
            Model.MultipleObjectsReturned: something really wrong has happened

        Returns:
            The ldap object corresponding to the dn
        """
        dn = dn.lower()
        model = cast(Type["Model"], self.model)
        options = cast("Options", model._meta)
        if options.basedn and not dn.endswith(options.basedn.lower()):
            raise ValueError(f"The requested dn '{dn}' is not in our model's basedn '{options.basedn}")
        try:
            objects = self.search(
                '(objectClass=*)',
                options.attributes,
                basedn=dn,
                scope=ldap.SCOPE_BASE
            )
        except ldap.NO_SUCH_OBJECT:    # pylint:disable=no-member
            objects = []
        if len(objects) == 0:
            raise model.DoesNotExist(
                'A {} object matching query does not exist.'.format(model.__name__))
        if len(objects) > 1:
            raise model.MultipleObjectsReturned(
                'More than one {} object matched query.'.format(model.__name__))
        return cast("Model", model.from_db(options.attributes, objects))

    @substitute_pk
    def get(self, *args, **kwargs) -> "Model":
        return self.__filter().filter(*args, **kwargs).get()

    def all(self) -> Sequence["Model"]:
        """
        .. note::

            Unlike the Django QuerySet version of this, this actually
            runs the query against LDAP and returns the result.  The Django
            version returns an iterator, I think.
        """
        return self.__filter().all()

    def values(self, *args: str) -> List[Dict[str, Any]]:
        return self.__filter().values(*args)

    def values_list(self, *args: str, **kwargs) -> List[Tuple[Any, ...]]:
        return self.__filter().values_list(*args, **kwargs)

    def order_by(self, *args: str) -> "F":
        return self.__filter().order_by(*args)

    def reset_password(self, username: str, new_password: str, attributes: Dict[str, Any] = None) -> bool:
        model = cast(Type["Model"], self.model)
        password_attribute = cast("Options", model._meta).password_attribute
        if not password_attribute:
            return False
        if not attributes:
            attributes = {}
        try:
            user = self.filter(**{'uid': username}).only('uid').get()
        except model.DoesNotExist:
            logging.warning('auth.no_such_user user=%s', username)
            return False

        pwhash = model.get_password_hash(new_password)
        attr = {password_attribute: [pwhash]}
        cast(Dict[str, Any], attributes).update(attr)

        _modlist = Modlist(self)._get_modlist(attr, ldap.MOD_REPLACE)

        self.connect('write')
        self.connection.modify_s(user.dn, _modlist)
        self.disconnect()
        service = getattr(model._meta, 'ldap_server', 'ldap')
        logging.info('%s.password_reset.success dn=%s', service, user.dn)
        return True

    def authenticate(self, username: str, password: str) -> bool:
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
        model = cast(Type["Model"], self.model)
        uid_attr = cast("Options", model._meta).userid_attribute
        try:
            user = self.filter(**{uid_attr: username}).only(uid_attr).get()
        except model.DoesNotExist:
            logging.warning('auth.no_such_user user=%s', username)
            return False
        try:
            self.connect('read', user.dn, password)
        except ldap.INVALID_CREDENTIALS:
            logging.warning('auth.invalid_credentials user=%s', username)
            return False
        self.disconnect()
        logging.info('auth.success user=%s', username)
        return True

    def create(self, **kwargs) -> "Model":
        """
        Create a model object based on **kwargs, then LDAP_ADD it to LDAP.
        """
        obj = cast(Type["Model"], self.model)(**kwargs)
        self.add(obj)
        return self.get(pk=getattr(obj, cast(str, self.pk)))
