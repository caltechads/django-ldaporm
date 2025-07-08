from rest_framework import serializers
from ldaporm.models import Model as LdapModel


class LdapModelSerializer(serializers.Serializer):
    """
    A DRF Serializer for ldaporm.Model subclasses.
    Automatically introspects ldaporm fields and provides create/update methods.
    """

    def __init__(self, *args, **kwargs):
        # Dynamically add fields from the ldaporm model
        model_class = self.Meta.model
        assert issubclass(model_class, LdapModel), (
            "Meta.model must be a subclass of ldaporm.Model"
        )
        super().__init__(*args, **kwargs)
        for field in model_class._meta.fields:
            if field.name in self.fields:
                continue  # Already defined explicitly
            drf_field = self._get_drf_field(field)
            self.fields[field.name] = drf_field

    def _get_drf_field(self, ldap_field):
        # Map ldaporm field types to DRF fields (basic mapping, extend as needed)
        from ldaporm.fields import CharField, IntegerField, BooleanField

        if hasattr(ldap_field, "choices") and ldap_field.choices:
            return serializers.ChoiceField(
                choices=ldap_field.choices, required=not ldap_field.blank
            )
        if isinstance(ldap_field, CharField):
            return serializers.CharField(
                required=not ldap_field.blank, allow_blank=ldap_field.blank
            )
        if isinstance(ldap_field, IntegerField):
            return serializers.IntegerField(required=not ldap_field.blank)
        if isinstance(ldap_field, BooleanField):
            return serializers.BooleanField(required=not ldap_field.blank)
        # Fallback to CharField
        return serializers.CharField(
            required=not ldap_field.blank, allow_blank=ldap_field.blank
        )

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
            ret[field.name] = getattr(instance, field.name)
        if hasattr(instance, "dn"):
            ret["dn"] = instance.dn
        return ret

    class Meta:
        model = (
            None  # Set this to your ldaporm.Model subclass in your serializer subclass
        )
