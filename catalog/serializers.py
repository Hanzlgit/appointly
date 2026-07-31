from rest_framework import serializers


class CatalogLocationCreateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    address = serializers.CharField(required=False, allow_blank=True, default="")


class CatalogLocationUpdateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False)
    address = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)


class CatalogLocationResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    address = serializers.CharField()
    is_active = serializers.BooleanField()
    resource_count = serializers.IntegerField()
    service_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class CatalogLocationListResponseSerializer(serializers.Serializer):
    locations = CatalogLocationResponseSerializer(many=True)


class CatalogServiceCreateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    duration_minutes = serializers.IntegerField(min_value=1)
    price_cents = serializers.IntegerField(min_value=0, required=False, default=0)
    currency = serializers.CharField(max_length=3, required=False, default="CNY")
    resource_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
    )


class CatalogServiceUpdateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    duration_minutes = serializers.IntegerField(min_value=1, required=False)
    price_cents = serializers.IntegerField(min_value=0, required=False)
    currency = serializers.CharField(max_length=3, required=False)
    is_active = serializers.BooleanField(required=False)
    resource_ids = serializers.ListField(child=serializers.IntegerField(), required=False)


class CatalogServiceResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField()
    duration_minutes = serializers.IntegerField()
    price_cents = serializers.IntegerField()
    currency = serializers.CharField()
    is_active = serializers.BooleanField()
    location_id = serializers.IntegerField()
    resource_ids = serializers.ListField(child=serializers.IntegerField())
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class CatalogServiceListResponseSerializer(serializers.Serializer):
    services = CatalogServiceResponseSerializer(many=True)


class CatalogResourceCreateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)


class CatalogResourceUpdateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False)
    is_active = serializers.BooleanField(required=False)


class CatalogResourceResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    location_id = serializers.IntegerField()
    is_active = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class CatalogResourceListResponseSerializer(serializers.Serializer):
    resources = CatalogResourceResponseSerializer(many=True)


class CatalogPublicLocationResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    address = serializers.CharField()


class CatalogPublicServiceResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField()
    duration_minutes = serializers.IntegerField()
    price_cents = serializers.IntegerField()
    currency = serializers.CharField()
    location_ids = serializers.ListField(child=serializers.IntegerField())


class CatalogPublicBrowseResponseSerializer(serializers.Serializer):
    locations = CatalogPublicLocationResponseSerializer(many=True)
    services = CatalogPublicServiceResponseSerializer(many=True)
