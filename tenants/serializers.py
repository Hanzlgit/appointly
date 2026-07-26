from rest_framework import serializers


class TenantContextRetrieveResponseSerializer(serializers.Serializer):
    slug = serializers.SlugField()
    name = serializers.CharField()
    timezone = serializers.CharField()
    is_active = serializers.BooleanField()


class TenantMembershipRetrieveResponseSerializer(serializers.Serializer):
    role = serializers.CharField()


class TenantScopedRecordResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    label = serializers.CharField()
    created_at = serializers.DateTimeField()


class TenantScopedRecordListResponseSerializer(serializers.Serializer):
    records = TenantScopedRecordResponseSerializer(many=True)


class TenantScopedRecordCreateRequestSerializer(serializers.Serializer):
    label = serializers.CharField()


class TenantScopedRecordCreateResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    label = serializers.CharField()
    created_at = serializers.DateTimeField()


class TenantCustomerMeRetrieveResponseSerializer(serializers.Serializer):
    tenant_slug = serializers.SlugField()
    phone = serializers.CharField()
    display_name = serializers.CharField()
    notes = serializers.CharField()
    tags = serializers.JSONField()


class TenantSettingsUpdateRequestSerializer(serializers.Serializer):
    timezone = serializers.CharField(max_length=64)


class TenantSettingsUpdateResponseSerializer(serializers.Serializer):
    slug = serializers.SlugField()
    name = serializers.CharField()
    timezone = serializers.CharField()
    is_active = serializers.BooleanField()
