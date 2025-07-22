import base64
import datetime
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, ClassVar, cast

from rest_framework import Request, View, serializers
from rest_framework.filters import BaseFilterBackend
from rest_framework.pagination import BasePagination
from rest_framework.response import Response
from rest_framework.reverse import reverse

from ldaporm import fields
from ldaporm.managers import F
from ldaporm.models import Model as LdapModel

if TYPE_CHECKING:
    from ldaporm.managers import Manager as LdapManager
    from ldaporm.options import Options as LdapOptions


class BinaryField(serializers.Field):
    """
    A custom serializer field for handling binary data.

    This field handles the conversion between base64-encoded strings in JSON
    and Python bytes objects for LDAP binary attributes.
    """

    def to_internal_value(self, data):
        """
        Convert base64-encoded string to bytes.

        Args:
            data: Base64-encoded string data.

        Returns:
            Decoded bytes data.

        Raises:
            ValidationError: If the data cannot be decoded.

        """
        if data is None:
            return None

        if isinstance(data, bytes):
            return data

        if isinstance(data, str):
            try:
                return base64.b64decode(data.encode("utf-8"))
            except Exception as e:
                msg = f"Invalid base64 data: {e}"
                raise serializers.ValidationError(msg) from e

        msg = "Binary field must be a base64-encoded string or bytes"
        raise serializers.ValidationError(msg)

    def to_representation(self, value):
        """
        Convert bytes to base64-encoded string.

        Args:
            value: Bytes data.

        Returns:
            Base64-encoded string.

        """
        if value is None:
            return None

        if isinstance(value, bytes):
            return base64.b64encode(value).decode("utf-8")

        return value


class LdapModelSerializer(serializers.Serializer):
    """
    A DRF Serializer for ldaporm.Model subclasses.
    Automatically introspects ldaporm fields and provides create/update methods.
    """

    def __init__(self, *args, **kwargs):
        # Dynamically add fields from the ldaporm model
        model_class = self.Meta.model
        assert issubclass(model_class, LdapModel), (  # noqa: S101
            "Meta.model must be a subclass of ldaporm.Model"
        )
        super().__init__(*args, **kwargs)
        for field in model_class._meta.fields:
            if field.name in self.fields:
                continue  # Already defined explicitly
            drf_field = self._get_drf_field(field)
            self.fields[field.name] = drf_field

    def _get_drf_field(self, ldap_field: fields.Field) -> serializers.Field:  # noqa: PLR0912
        # Determine required/optional logic
        # Primary key fields should always be required
        is_pk = getattr(ldap_field, "primary_key", False)
        if is_pk:
            is_required = True
        else:
            # For non-primary key fields, check blank and null attributes
            is_blank = getattr(ldap_field, "blank", False)
            allow_null = getattr(ldap_field, "null", False)

            # A field is required if it's not blank and not null
            is_required = not is_blank and not allow_null

        allow_null = getattr(ldap_field, "null", False)

        # Map ldaporm field types to DRF fields (basic mapping, extend as needed)
        if isinstance(ldap_field, fields.CharListField):
            field = serializers.ListField(
                child=serializers.CharField(),
                required=is_required,
                allow_null=allow_null,
            )
        elif hasattr(ldap_field, "choices") and ldap_field.choices:
            field = serializers.ChoiceField(
                choices=ldap_field.choices, required=is_required, allow_null=allow_null
            )
        elif isinstance(ldap_field, (fields.EmailField, fields.EmailForwardField)):
            field = serializers.EmailField(required=is_required, allow_null=allow_null)
        elif isinstance(ldap_field, fields.CaseInsensitiveSHA1Field):
            # Read-only field for hashed values
            field = serializers.CharField(
                read_only=True,
                style={"input_type": "password"},
            )
        elif isinstance(ldap_field, (fields.LDAPPasswordField, fields.ADPasswordField)):
            # Password fields should be read-only and styled as password
            field = serializers.CharField(
                read_only=True,
                style={"input_type": "password"},
            )
        elif isinstance(ldap_field, fields.CharField):
            field = serializers.CharField(
                required=is_required,
                allow_blank=getattr(ldap_field, "blank", False),
                allow_null=allow_null,
            )
        elif isinstance(ldap_field, fields.IntegerField):
            field = serializers.IntegerField(
                required=is_required, allow_null=allow_null
            )
        elif isinstance(ldap_field, (fields.BooleanField, fields.AllCapsBooleanField)):
            field = serializers.BooleanField(
                required=is_required, allow_null=allow_null
            )
        elif isinstance(
            ldap_field, (fields.DateTimeField, fields.ActiveDirectoryTimestampField)
        ):
            field = serializers.DateTimeField(
                required=is_required, allow_null=allow_null
            )
        elif isinstance(ldap_field, fields.DateField):
            field = serializers.DateField(required=is_required, allow_null=allow_null)
        elif isinstance(ldap_field, fields.BinaryField):
            field = BinaryField(
                required=is_required,
                allow_null=allow_null,
            )
        else:
            field = serializers.CharField(
                required=is_required,
                allow_blank=getattr(ldap_field, "blank", False),
                allow_null=allow_null,
            )
        return field

    def create(self, validated_data):
        model_class = self.Meta.model
        instance = model_class(**validated_data)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

    def to_representation(self, instance):
        # Convert model instance to dict for DRF
        ret = {}
        for field in instance._meta.fields:
            value = getattr(instance, field.name)
            # Convert date objects to ISO format strings for JSON serialization
            if isinstance(value, datetime.date):
                ret[field.name] = value.isoformat()
            # Convert binary data to base64 for JSON serialization
            elif isinstance(field, fields.BinaryField) and value is not None:
                ret[field.name] = base64.b64encode(value).decode("utf-8")
            else:
                ret[field.name] = value
        if hasattr(instance, "dn"):
            ret["dn"] = instance.dn
        return ret

    class Meta:
        model = (
            None  # Set this to your ldaporm.Model subclass in your serializer subclass
        )


class HyperlinkedModelSerializer(LdapModelSerializer):
    """
    A hyperlinked serializer for ldaporm.Model subclasses.

    This serializer provides URL-based identification and hyperlinked relationships
    for LDAP ORM models, similar to Django REST Framework's HyperlinkedModelSerializer.

    The serializer automatically includes a 'url' field that points to the detail
    view for each instance, and can handle hyperlinked relationships to other
    LDAP ORM models.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add the url field if not already present
        if "url" not in self.fields:
            # Get extra kwargs for the url field if specified
            extra_kwargs = getattr(self.Meta, "extra_kwargs", {})
            url_kwargs = extra_kwargs.get("url", {})

            self.fields["url"] = serializers.HyperlinkedIdentityField(
                view_name=url_kwargs.get("view_name", self._get_detail_view_name()),
                lookup_field=url_kwargs.get("lookup_field", self._get_lookup_field()),
            )

    def _get_detail_view_name(self) -> str:
        """
        Get the view name for the detail endpoint.

        Returns:
            The view name for the detail endpoint, constructed from the model name.

        """
        meta = cast("LdapOptions", cast("LdapModel", self.Meta.model)._meta)
        name = cast("str", meta.object_name)
        return f"{name.lower()}-detail"

    def _get_lookup_field(self) -> str:
        """
        Get the lookup field for URL construction.

        For LDAP ORM models, we typically use 'dn' as the lookup field
        since it's the unique identifier in LDAP.

        Returns:
            The lookup field name, defaults to 'dn'.

        """
        return getattr(self.Meta, "lookup_field", "dn")

    def _get_drf_field(self, ldap_field: fields.Field) -> serializers.Field:
        """
        Get DRF field with support for hyperlinked relationships.

        Args:
            ldap_field: The LDAP ORM field to convert.

        Returns:
            A DRF serializer field.

        """
        # Check if this field should be a hyperlinked relationship
        if self._is_relationship_field(ldap_field):
            return self._get_hyperlinked_relationship_field(ldap_field)
        # Use parent's field mapping for regular fields
        return super()._get_drf_field(ldap_field)

    def _is_relationship_field(self, ldap_field: fields.Field) -> bool:
        """
        Check if a field should be treated as a relationship field.

        Args:
            ldap_field: The LDAP ORM field to check.

        Returns:
            True if the field should be a relationship, False otherwise.

        """
        # Check if field name suggests a relationship (ends with '_dn' or '_id')
        if ldap_field.name and ldap_field.name.endswith(("_dn", "_id")):
            return True

        # Check if field has a related model specified in Meta
        if hasattr(self.Meta, "relationship_fields"):
            if ldap_field.name in self.Meta.relationship_fields:  # type: ignore[operator]
                return True

        # Check if field is in relationship_models mapping
        if hasattr(self.Meta, "relationship_models"):
            if ldap_field.name in self.Meta.relationship_models:  # type: ignore[operator]
                return True

        return False

    def _get_hyperlinked_relationship_field(
        self, ldap_field: fields.Field
    ) -> serializers.Field:
        """
        Create a hyperlinked relationship field.

        Args:
            ldap_field: The LDAP ORM field representing the relationship.

        Returns:
            A DRF HyperlinkedRelatedField.

        """
        # Determine the related model and view name
        related_model = cast(
            "type[LdapModel] | None", self._get_related_model(ldap_field)
        )
        if related_model:
            meta = cast("LdapOptions", related_model._meta)
            name = cast("str", meta.object_name)
            default_view_name = f"{name.lower()}-detail"

            # Get extra kwargs for this field if specified
            extra_kwargs = getattr(self.Meta, "extra_kwargs", {})
            field_kwargs = extra_kwargs.get(cast("str", ldap_field.name), {})

            return serializers.HyperlinkedRelatedField(
                view_name=field_kwargs.get("view_name", default_view_name),
                lookup_field=field_kwargs.get("lookup_field", "dn"),
                queryset=cast("LdapManager", related_model.objects),
                required=not ldap_field.blank,
                allow_null=ldap_field.null,
            )

        # Fallback to regular field if we can't determine the relationship
        return super()._get_drf_field(ldap_field)

    def _get_related_model(self, ldap_field: fields.Field) -> type[LdapModel] | None:
        """
        Get the related model for a relationship field.

        Args:
            ldap_field: The LDAP ORM field representing the relationship.

        Returns:
            The related model class or None if not found.

        """
        # Check if relationship mapping is defined in Meta
        if hasattr(self.Meta, "relationship_models"):
            try:
                return cast(
                    "type[LdapModel]",
                    self.Meta.relationship_models[cast("str", ldap_field.name)],
                )
            except KeyError:
                # Return None instead of raising KeyError
                return None

        # Return None if no relationship_models configured
        return None

    def to_representation(self, instance):
        """
        Convert model instance to dict with hyperlinked URLs.

        Args:
            instance: The LDAP ORM model instance.

        Returns:
            A dictionary representation with hyperlinked URLs.

        """
        ret = super().to_representation(instance)

        # Add hyperlinked relationships
        for field in instance._meta.fields:
            if self._is_relationship_field(field):
                related_value = getattr(instance, field.name)
                if related_value:
                    # Try to get the related object and create a URL
                    try:
                        related_model = self._get_related_model(field)
                        if related_model:
                            # This is a simplified approach - you might need to
                            # implement proper LDAP querying here
                            related_obj = related_model.objects.get(dn=related_value)
                            view_name = (
                                f"{related_model._meta.object_name.lower()}-detail"
                            )
                            ret[field.name] = reverse(
                                view_name,
                                kwargs={"dn": related_obj.dn},
                                request=self.context.get("request"),
                                format=self.context.get("format"),
                            )
                    except (related_model.DoesNotExist, AttributeError):
                        # If we can't resolve the relationship, just include the DN
                        ret[field.name] = related_value

        return ret

    class Meta:
        #: The model to serialize.
        model: ClassVar[type[LdapModel] | None] = (
            None  # Set this to your ldaporm.Model subclass
        )
        #: The field to use for URL lookups.
        lookup_field: ClassVar[str] = "dn"  # The field to use for URL lookups
        #: A list of relationship fields.
        relationship_fields: ClassVar[Iterable[str]] = ()
        #: A dictionary of relationship fields to their related models.
        relationship_models: ClassVar[dict[str, LdapModel]] = {}
        #: Extra keyword arguments for field configuration.
        extra_kwargs: ClassVar[dict[str, dict[str, str]]] = {}


class LdapCursorPagination(BasePagination):
    """
    LDAP cursor-based pagination for REST framework views.

    This pagination class uses LDAP's SimplePagedResultsControl to provide
    efficient server-side paging. It uses base64-encoded cookies as cursors
    to maintain pagination state.

    Example usage:

        .. code-block:: python

            from rest_framework import viewsets
            from ldaporm.restframework import LdapCursorPagination

            from .models import User

            class UserSerializer(LdapModelSerializer):
                class Meta:
                    model = User
                    fields = '__all__'

            class UserViewSet(viewsets.ModelViewSet):
                pagination_class = LdapCursorPagination
                serializer_class = UserSerializer

                def get_queryset(self):
                    return User.objects.all()

    """

    #: The default page size.
    page_size = 100
    #: The query parameter name for the page size.
    page_size_query_param = "page_size"
    #: The maximum page size.
    max_page_size = 1000
    #: The query parameter name for the cursor.
    cursor_query_param = "next_token"

    def paginate_queryset(
        self,
        queryset: F,
        request: Request,
        view: View | None = None,  # noqa: ARG002
    ) -> list[LdapModel]:
        """
        Paginate the queryset using LDAP paging.

        Args:
            queryset: The LDAP ORM queryset to paginate.
            request: The HTTP request.
            view: The view instance.

        Returns:
            A PagedResultSet containing the current page of results.

        """
        # Get page size from request
        page_size = self.get_page_size(request)

        # Get cursor from request
        cursor = request.query_params.get(self.cursor_query_param, "")

        # Decode cursor if provided
        cookie = ""
        if cursor:
            try:
                cookie = base64.b64decode(cursor.encode()).decode()
            except Exception:  # noqa: BLE001
                # Invalid cursor, start from beginning
                cookie = ""

        # Perform paged search
        paged_results = queryset.page(page_size=page_size, cookie=cookie)

        # Store pagination info for response
        self.paged_results = paged_results
        self.request = request

        return paged_results.results

    def get_paginated_response(self, data: list[Any]) -> Response:
        """
        Return a paginated response with cursor-based navigation.

        Args:
            data: The serialized data for the current page.

        Returns:
            A Response with pagination metadata.

        """
        response_data = {
            "results": data,
            "has_more": self.paged_results.has_more,
        }

        # Add next cursor if there are more results
        if self.paged_results.has_more and self.paged_results.next_cookie:
            next_cursor = base64.b64encode(
                self.paged_results.next_cookie.encode()
            ).decode()
            response_data["next"] = self._get_next_url(next_cursor)

        return Response(response_data)

    def get_page_size(self, request: Request) -> int:
        """
        Get the page size from the request.

        Args:
            request: The HTTP request.

        Returns:
            The page size to use.

        """
        if self.page_size_query_param:
            try:
                # Handle both Django test requests and DRF requests
                if hasattr(request, "query_params"):
                    # DRF request
                    page_size = int(
                        request.query_params.get(
                            self.page_size_query_param, self.page_size
                        )
                    )
                else:
                    # Django test request
                    page_size = int(
                        request.GET.get(self.page_size_query_param, self.page_size)
                    )
                return min(page_size, self.max_page_size)
            except (KeyError, ValueError):
                pass
        return self.page_size

    def _get_next_url(self, cursor: str) -> str:
        """
        Generate the URL for the next page.

        Args:
            cursor: The base64-encoded cursor for the next page.

        Returns:
            The URL for the next page.

        """
        from urllib.parse import parse_qs, urlencode, urlparse

        # Parse the current URL
        parsed_url = urlparse(self.request.build_absolute_uri())
        query_params = parse_qs(parsed_url.query)

        # Update or add the cursor parameter
        query_params[self.cursor_query_param] = [cursor]

        # Preserve all other query parameters (including page_size)
        # Remove the cursor parameter from the original URL to avoid duplication
        if self.cursor_query_param in query_params:
            # Ensure we have the latest cursor value
            pass

        # Rebuild the query string
        new_query = urlencode(query_params, doseq=True)

        # Reconstruct the URL
        new_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
        if new_query:
            new_url = f"{new_url}?{new_query}"

        return new_url


class LdapOrderingFilter(BaseFilterBackend):
    """
    A filter backend that provides ordering for LDAP ORM models.

    This filter leverages LDAP ORM's built-in ordering capabilities, which use
    server-side sorting when available and fall back to client-side sorting
    when the LDAP server doesn't support server-side sorting.

    The filter supports:

    - Single and multiple field ordering
    - Ascending and descending ordering (using '-' prefix)
    - Field validation against the LDAP model's available fields
    - Fallback to model's default ordering when no ordering is specified

    Example usage:

        .. code-block:: python

            from ldaporm.restframework import LdapOrderingFilter
            from rest_framework import viewsets

            from .models import User

            class UserViewSet(viewsets.ModelViewSet):
                filter_backends = [LdapOrderingFilter]
                ordering_fields = ['uid', 'cn', 'mail', 'created']
                ordering = ['uid']  # Default ordering

                def get_queryset(self):
                    return User.objects.all()

    Query parameters:
        ``?ordering=uid,-cn,mail``  # Order by uid ascending, cn descending,
        mail ascending
    """

    #: The query parameter name for ordering
    ordering_param = "ordering"
    #: The fields that can be used for ordering (None means all fields)
    ordering_fields = None
    #: The default ordering to use when no ordering is specified
    ordering = None

    def get_ordering(self, request, queryset, view):
        """
        Get the ordering from the request and validate it.

        Args:
            request: The HTTP request
            queryset: The LDAP ORM queryset
            view: The view instance

        Returns:
            A list of ordering fields (with '-' prefix for descending)

        """
        params = request.query_params.get(self.ordering_param)
        if not params:
            return self.get_default_ordering(view, queryset)

        fields = [param.strip() for param in params.split(",")]
        ordering = []

        for field in fields:
            if not field:
                continue

            # Check if field is valid
            if self._is_valid_field(field, queryset, view):
                ordering.append(field)
            # If field is invalid, just ignore it instead of raising an error

        return ordering

    def filter_queryset(self, request, queryset, view):
        """
        Apply ordering to the LDAP ORM queryset.

        This method leverages LDAP ORM's built-in ordering capabilities,
        which automatically use server-side sorting when available and
        fall back to client-side sorting when needed.

        Args:
            request: The HTTP request
            queryset: The LDAP ORM queryset
            view: The view instance

        Returns:
            The ordered LDAP ORM queryset

        """
        ordering = self.get_ordering(request, queryset, view)
        if ordering:
            return queryset.order_by(*ordering)
        return queryset

    def get_default_ordering(self, view, queryset=None):
        """
        Get the default ordering from the view or model.

        Args:
            view: The view instance
            queryset: The LDAP ORM queryset (optional)

        Returns:
            A list of default ordering fields

        """
        # Check view's ordering attribute first
        if hasattr(view, "ordering") and view.ordering is not None:
            return view.ordering

        # Check filter's default ordering
        if self.ordering is not None:
            return self.ordering

        # Use provided queryset or get from view
        if queryset is None and hasattr(view, "get_queryset"):
            queryset = view.get_queryset()

        # Fall back to model's default ordering
        if queryset and hasattr(queryset, "model") and hasattr(queryset.model, "_meta"):
            return getattr(queryset.model._meta, "ordering", [])

        return []

    def _is_valid_field(self, field, queryset, view):
        """
        Check if a field is valid for ordering.

        Args:
            field: The field name (with or without '-' prefix)
            queryset: The LDAP ORM queryset
            view: The view instance

        Returns:
            True if the field is valid, False otherwise

        """
        # Remove '-' prefix for validation
        field_name = field.lstrip("-")

        # Check against view's ordering_fields if specified
        ordering_fields = self._get_ordering_fields(view)
        if ordering_fields is not None:
            return field_name in ordering_fields

        # Check against model's available fields
        if hasattr(queryset, "model") and hasattr(queryset.model, "_meta"):
            model_fields = queryset.model._meta.fields
            return field_name in [f.name for f in model_fields]

        return True

    def _get_ordering_fields(self, view):
        """
        Get the allowed ordering fields from the view.

        Args:
            view: The view instance

        Returns:
            A list of allowed ordering fields, or None if all fields are allowed

        """
        # Check view's ordering_fields attribute
        if hasattr(view, "ordering_fields") and view.ordering_fields is not None:
            return view.ordering_fields

        # Check filter's ordering_fields attribute
        return self.ordering_fields

    def _get_available_fields(self, queryset, view):
        """
        Get the list of available fields for ordering.

        Args:
            queryset: The LDAP ORM queryset
            view: The view instance

        Returns:
            A list of available field names

        """
        ordering_fields = self._get_ordering_fields(view)
        if ordering_fields is not None:
            return ordering_fields

        if hasattr(queryset, "model") and hasattr(queryset.model, "_meta"):
            return [f.name for f in queryset.model._meta.fields]

        return []

    def get_schema_operation_parameters(self, view):
        """
        Get the schema operation parameters for OpenAPI documentation.

        Args:
            view: The view instance

        Returns:
            A list of parameter definitions for OpenAPI

        """
        available_fields = []
        if hasattr(view, "get_queryset"):
            queryset = view.get_queryset()
            available_fields = self._get_available_fields(queryset, view)

        return [
            {
                "name": self.ordering_param,
                "required": False,
                "in": "query",
                "description": (
                    "Ordering field(s). Use '-' prefix for descending order. "
                    f"Available fields: {', '.join(available_fields)}"
                ),
                "schema": {
                    "type": "string",
                    "example": "uid,-cn,mail",
                },
            }
        ]


class LdapFilterBackend(BaseFilterBackend):
    """
    Base class for LDAP model filtering backends.

    This class provides a foundation for creating custom filter backends
    that work with LDAP ORM models. It handles common filtering patterns
    and provides a consistent interface for LDAP-specific filtering.

    Subclasses should override:

    - filter_fields: Define the fields that can be filtered.  There should
      be a dictionary of field names to their configurations.  The
      configurations should include:

      - lookup: The lookup type to use for the field.  This should be one of
        the following:

        - iexact: case-insensitive exact match
        - icontains: case-insensitive contains
        - istartswith: starts with
        - iendswith: ends with
        - gt: greater than (numeric)
        - gte: greater than or equal to (numeric)
        - lt: less than (numeric)
        - lte: less than or equal to (numeric)

      - type: The field type to use for the field.  This should be one of the
        following:

        - string: string
        - integer: integer
        - boolean: boolean
        - binary: binary

    Example usage:

        .. code-block:: python

            from rest_framework import viewsets
            from ldaporm.restframework import LdapFilterBackend
            from .models import User

            class UserFilterBackend(LdapFilterBackend):
                filter_fields = {
                    'uid': {'lookup': 'iexact', 'type': 'string'},
                    'mail': {'lookup': 'icontains', 'type': 'string'},
                    'employee_number': {'lookup': 'iexact', 'type': 'integer'},
                }

            class UserViewSet(viewsets.ModelViewSet):
                model = User
                filter_backends = [UserFilterBackend]

    """

    #: Dictionary defining filterable fields and their configurations
    filter_fields: ClassVar[dict[str, dict[str, str]]] = {}

    def filter_queryset(self, request, queryset, view):
        """
        Filter the queryset based on query parameters.

        Args:
            request: The HTTP request
            queryset: The LDAP ORM queryset
            view: The view instance

        Returns:
            The filtered LDAP ORM queryset

        """
        return self.get_filter_queryset(request, queryset, view)

    def get_filter_queryset(self, request: Request, queryset: F, view: View) -> F:  # noqa: ARG002
        """
        Apply filters to the queryset. Override this method in subclasses.  This
        method is called by :py:meth:`filter_queryset` and should return the
        filtered queryset.

        Args:
            request: The HTTP request
            queryset: The LDAP ORM queryset
            view: The view instance

        Returns:
            The filtered LDAP ORM queryset

        """
        return self.apply_filters(request, queryset)

    def apply_filters(self, request: Request, queryset: F) -> F:
        """
        Apply filters based on the filter_fields configuration.  This method is
        called by :py:meth:`get_filter_queryset` and should return the filtered
        queryset.

        Args:
            request: The HTTP request
            queryset: The LDAP ORM queryset

        Returns:
            The filtered LDAP ORM queryset

        """
        for field_name, field_config in self.filter_fields.items():
            value = request.query_params.get(field_name)
            if value is not None:
                lookup = field_config.get("lookup", "iexact")
                field_type = field_config.get("type", "string")

                # Convert value based on field type
                if field_type == "integer":
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        continue  # Skip invalid integer values
                elif field_type == "boolean":
                    if value.lower() in ("true", "1", "yes", "on"):
                        value = True
                    elif value.lower() in ("false", "0", "no", "off"):
                        value = False
                    else:
                        continue  # Skip invalid boolean values
                elif field_type == "binary":
                    try:
                        # Decode base64-encoded binary data
                        value = base64.b64decode(value.encode("utf-8"))
                    except Exception:  # noqa: BLE001, S112
                        continue  # Skip invalid base64 values

                # Apply the filter
                filter_kwargs = {f"{field_name}__{lookup}": value}
                queryset = queryset.filter(**filter_kwargs)

        return queryset

    def get_schema_operation_parameters(self, view: View) -> list[dict[str, Any]]:  # noqa: ARG002
        """
        Return schema operation parameters for OpenAPI documentation.

        Args:
            view: The view instance

        Returns:
            A list of parameter definitions for OpenAPI

        """
        parameters = []
        for field_name, field_config in self.filter_fields.items():
            field_type = field_config.get("type", "string")
            lookup = field_config.get("lookup", "iexact")

            # Generate description based on lookup type
            lookup_descriptions = {
                "iexact": "case-insensitive exact match",
                "icontains": "case-insensitive contains",
                "exact": "exact match",
                "contains": "contains",
                "startswith": "starts with",
                "endswith": "ends with",
            }
            lookup_desc = lookup_descriptions.get(lookup, lookup)

            # Map field type to OpenAPI schema type
            schema_type = {
                "string": "string",
                "integer": "integer",
                "boolean": "boolean",
                "float": "number",
                "binary": "string",  # Binary data is transmitted as base64 string
            }.get(field_type, "string")

            parameters.append(
                {
                    "name": field_name,
                    "required": False,
                    "in": "query",
                    "description": f"Filter by {field_name} ({lookup_desc})",
                    "schema": {"type": schema_type},
                }
            )

        return parameters
