from rest_framework import serializers

from catalog.models import StylistQueueStatus
from catalog.selectors import DEFAULT_CATALOG_PAGE_SIZE, MAX_CATALOG_PAGE_SIZE


class CatalogListQuerySerializer(serializers.Serializer):
    """目录列表查询参数。"""

    page = serializers.IntegerField(min_value=1, default=1, required=False)
    page_size = serializers.IntegerField(
        min_value=1,
        max_value=MAX_CATALOG_PAGE_SIZE,
        default=DEFAULT_CATALOG_PAGE_SIZE,
        required=False,
    )
    q = serializers.CharField(required=False, allow_blank=True, default="")


class CatalogLocationCreateRequestSerializer(serializers.Serializer):
    """创建门店请求。"""

    name = serializers.CharField(max_length=255)
    address = serializers.CharField(required=False, allow_blank=True, default="")


class CatalogLocationUpdateRequestSerializer(serializers.Serializer):
    """更新门店请求。"""

    name = serializers.CharField(max_length=255, required=False)
    address = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)


class CatalogLocationResponseSerializer(serializers.Serializer):
    """门店后台响应。"""

    id = serializers.IntegerField()
    name = serializers.CharField()
    address = serializers.CharField()
    is_active = serializers.BooleanField()
    stylist_count = serializers.IntegerField()
    service_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class CatalogPublicLocationResponseSerializer(serializers.Serializer):
    """门店公开响应。"""

    id = serializers.IntegerField()
    name = serializers.CharField()
    address = serializers.CharField()


class CatalogPaginatedLocationListResponseSerializer(serializers.Serializer):
    """分页门店后台列表响应。"""

    items = CatalogLocationResponseSerializer(many=True)
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()


class CatalogPaginatedPublicLocationListResponseSerializer(serializers.Serializer):
    """分页门店公开列表响应。"""

    items = CatalogPublicLocationResponseSerializer(many=True)
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()


class CatalogStylistCreateRequestSerializer(serializers.Serializer):
    """创建理发师请求。"""

    name = serializers.CharField(max_length=255)
    ticket_prefix = serializers.CharField(required=False, allow_blank=True, default="", max_length=8)
    queue_status = serializers.ChoiceField(
        choices=StylistQueueStatus.choices,
        required=False,
    )


class CatalogStylistUpdateRequestSerializer(serializers.Serializer):
    """更新理发师请求。"""

    name = serializers.CharField(max_length=255, required=False)
    ticket_prefix = serializers.CharField(required=False, allow_blank=True, max_length=8)
    queue_status = serializers.ChoiceField(choices=StylistQueueStatus.choices, required=False)
    is_active = serializers.BooleanField(required=False)


class CatalogStylistResponseSerializer(serializers.Serializer):
    """理发师后台响应。"""

    id = serializers.IntegerField()
    name = serializers.CharField()
    location_id = serializers.IntegerField()
    ticket_prefix = serializers.CharField()
    queue_status = serializers.CharField()
    is_active = serializers.BooleanField()
    service_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class CatalogPublicStylistResponseSerializer(serializers.Serializer):
    """理发师公开响应。"""

    id = serializers.IntegerField()
    name = serializers.CharField()
    ticket_prefix = serializers.CharField()
    queue_status = serializers.CharField()


class CatalogPaginatedStylistListResponseSerializer(serializers.Serializer):
    """分页理发师后台列表响应。"""

    items = CatalogStylistResponseSerializer(many=True)
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()


class CatalogPaginatedPublicStylistListResponseSerializer(serializers.Serializer):
    """分页理发师公开列表响应。"""

    items = CatalogPublicStylistResponseSerializer(many=True)
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()


class CatalogPublicServiceResponseSerializer(serializers.Serializer):
    """公开服务项目响应。"""

    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField()
    duration_minutes = serializers.IntegerField()
    price_cents = serializers.IntegerField()
    currency = serializers.CharField()
    stylist_id = serializers.IntegerField()


class CatalogPaginatedPublicServiceListResponseSerializer(serializers.Serializer):
    """公开分页服务项目列表响应。"""

    items = CatalogPublicServiceResponseSerializer(many=True)
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()


class CatalogServiceCreateRequestSerializer(serializers.Serializer):
    """创建服务项目请求。"""

    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    duration_minutes = serializers.IntegerField(min_value=1)
    price_cents = serializers.IntegerField(min_value=0, required=False, default=0)
    currency = serializers.CharField(max_length=3, required=False, default="CNY")


class CatalogServiceUpdateRequestSerializer(serializers.Serializer):
    """更新服务项目请求。"""

    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    duration_minutes = serializers.IntegerField(min_value=1, required=False)
    price_cents = serializers.IntegerField(min_value=0, required=False)
    currency = serializers.CharField(max_length=3, required=False)
    is_active = serializers.BooleanField(required=False)


class CatalogServiceResponseSerializer(serializers.Serializer):
    """服务项目响应。"""

    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField()
    duration_minutes = serializers.IntegerField()
    price_cents = serializers.IntegerField()
    currency = serializers.CharField()
    is_active = serializers.BooleanField()
    stylist_id = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class CatalogPaginatedServiceListResponseSerializer(serializers.Serializer):
    """分页服务项目列表响应。"""

    items = CatalogServiceResponseSerializer(many=True)
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
