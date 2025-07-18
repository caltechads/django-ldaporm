import base64
import datetime
from collections.abc import Iterable
from typing import TYPE_CHECKING, ClassVar, cast

from rest_framework import serializers
from rest_framework.pagination import BasePagination
from rest_framework.response import Response
from rest_framework.reverse import reverse

from ldaporm import fields
from ldaporm.models import Model as LdapModel

if TYPE_CHECKING:
    from ldaporm.managers import Manager as LdapManager
    from ldaporm.options import Options as LdapOptions


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
        class UserViewSet(viewsets.ModelViewSet):
            pagination_class = LdapCursorPagination
            serializer_class = UserSerializer

            def get_queryset(self):
                return User.objects.all()
    """

    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 1000
    cursor_query_param = "next_token"

    def paginate_queryset(self, queryset, request, view=None):  # noqa: ARG002
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

    def get_paginated_response(self, data):
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

    def get_page_size(self, request):
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

    def _get_next_url(self, cursor):
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
