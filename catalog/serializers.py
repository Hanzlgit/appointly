from rest_framework import serializers


class CatalogLocationCreateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    address = serializers.CharField(required=False, allow_blank=True, default="")
    resource_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
    )


class CatalogLocationUpdateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False)
    address = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    resource_ids = serializers.ListField(child=serializers.IntegerField(), required=False)


class CatalogLocationResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    address = serializers.CharField()
    is_active = serializers.BooleanField()
    resource_ids = serializers.ListField(child=serializers.IntegerField())
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
    resource_ids = serializers.ListField(child=serializers.IntegerField())
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class CatalogServiceListResponseSerializer(serializers.Serializer):
    services = CatalogServiceResponseSerializer(many=True)


class CatalogResourceCreateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    resource_type = serializers.ChoiceField(
        choices=["staff", "room", "venue", "equipment"],
    )
    staff_user_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    location_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
    )


class CatalogResourceUpdateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False)
    resource_type = serializers.ChoiceField(
        choices=["staff", "room", "venue", "equipment"],
        required=False,
    )
    staff_user_id = serializers.IntegerField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False)
    location_ids = serializers.ListField(child=serializers.IntegerField(), required=False)


class CatalogResourceResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    resource_type = serializers.CharField()
    staff_user_id = serializers.IntegerField(allow_null=True)
    is_active = serializers.BooleanField()
    location_ids = serializers.ListField(child=serializers.IntegerField())
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
