from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Count, Q

from catalog.models import Location, Service, Stylist

DEFAULT_CATALOG_PAGE_SIZE = 20
MAX_CATALOG_PAGE_SIZE = 100


@dataclass(frozen=True)
class CatalogListResult[T]:
    """分页目录列表查询结果。"""

    items: list[T]
    total: int


def catalog_location_has_unfinished_scheduling_references(*, location_id: int) -> bool:
    """检查门店是否存在未完成的排班或预约引用。

    Args:
        location_id (int): 门店 ID。

    Returns:
        bool: 存在排班规则、固定时段或有效预约时返回 ``True``。
    """
    from scheduling.models import Booking, ScheduleRule, TimeSlot
    from scheduling.services.booking import ACTIVE_BOOKING_STATUSES

    if ScheduleRule.objects.filter(location_id=location_id).exists():
        return True
    if TimeSlot.objects.filter(location_id=location_id).exists():
        return True
    return Booking.objects.filter(
        status__in=ACTIVE_BOOKING_STATUSES,
        time_slot__location_id=location_id,
    ).exists()


def catalog_location_get(*, location_id: int) -> Location:
    """按 ID 查询门店。

    Args:
        location_id (int): 门店 ID。

    Returns:
        Location: 匹配的门店。

    Raises:
        Location.DoesNotExist: 门店不存在。
    """
    return Location.objects.get(id=location_id)


def catalog_location_list_paginated(
    *,
    page: int = 1,
    page_size: int = DEFAULT_CATALOG_PAGE_SIZE,
    q: str = "",
    active_only: bool = False,
) -> CatalogListResult[Location]:
    """分页列出门店，按名称排序。

    Args:
        page (int): 页码，从 1 开始。
        page_size (int): 每页条数。
        q (str): 搜索关键词，匹配名称与地址。
        active_only (bool): 是否仅返回启用门店。

    Returns:
        CatalogListResult[Location]: 分页结果。
    """
    queryset = Location.objects.all()
    if active_only:
        queryset = queryset.filter(is_active=True)
    if q:
        queryset = queryset.filter(Q(name__icontains=q) | Q(address__icontains=q))

    queryset = queryset.annotate(
        stylist_count=Count("stylists", distinct=True),
        service_count=Count("stylists__services", distinct=True),
    ).order_by("name")

    total = queryset.count()
    offset = (page - 1) * page_size
    items = list(queryset[offset : offset + page_size])
    return CatalogListResult(items=items, total=total)


def catalog_location_to_dict(*, location: Location) -> dict[str, object]:
    """将 Location 实例映射为后台 API 响应字典。

    Args:
        location (Location): 门店实例。

    Returns:
        dict[str, object]: 含 id、name、stylist_count 等字段的字典。
    """
    stylist_count = getattr(location, "stylist_count", None)
    if stylist_count is None:
        stylist_count = location.stylists.count()
    service_count = getattr(location, "service_count", None)
    if service_count is None:
        service_count = Service.objects.filter(stylist__location_id=location.id).count()

    return {
        "id": location.id,
        "name": location.name,
        "address": location.address,
        "is_active": location.is_active,
        "stylist_count": stylist_count,
        "service_count": service_count,
        "created_at": location.created_at,
        "updated_at": location.updated_at,
    }


def catalog_public_location_to_dict(*, location: Location) -> dict[str, object]:
    """将启用门店映射为公开 API 响应字典。

    Args:
        location (Location): 门店实例。

    Returns:
        dict[str, object]: 公开可见字段字典。
    """
    return {
        "id": location.id,
        "name": location.name,
        "address": location.address,
    }


def catalog_stylist_get_for_location(*, location: Location, stylist_id: int) -> Stylist:
    """按 ID 查询指定门店下的理发师。

    Args:
        location (Location): 所属门店。
        stylist_id (int): 理发师 ID。

    Returns:
        Stylist: 匹配的理发师。

    Raises:
        Stylist.DoesNotExist: 理发师不存在或不属于该门店。
    """
    return Stylist.objects.get(location=location, id=stylist_id)


def catalog_stylist_get(*, stylist_id: int) -> Stylist:
    """按 ID 查询理发师。

    Args:
        stylist_id (int): 理发师 ID。

    Returns:
        Stylist: 匹配的理发师。

    Raises:
        Stylist.DoesNotExist: 理发师不存在。
    """
    return Stylist.objects.select_related("location").get(id=stylist_id)


def catalog_stylist_list_for_location_paginated(
    *,
    location: Location,
    page: int = 1,
    page_size: int = DEFAULT_CATALOG_PAGE_SIZE,
    q: str = "",
    active_only: bool = False,
) -> CatalogListResult[Stylist]:
    """分页列出指定门店下的理发师，按名称排序。

    Args:
        location (Location): 所属门店。
        page (int): 页码，从 1 开始。
        page_size (int): 每页条数。
        q (str): 搜索关键词，匹配名称与取号前缀。
        active_only (bool): 是否仅返回启用理发师。

    Returns:
        CatalogListResult[Stylist]: 分页结果。
    """
    queryset = Stylist.objects.filter(location=location)
    if active_only:
        queryset = queryset.filter(is_active=True)
    if q:
        queryset = queryset.filter(Q(name__icontains=q) | Q(ticket_prefix__icontains=q))

    queryset = queryset.annotate(
        service_count=Count("services", distinct=True),
    ).order_by("name")

    total = queryset.count()
    offset = (page - 1) * page_size
    items = list(queryset[offset : offset + page_size])
    return CatalogListResult(items=items, total=total)


def catalog_stylist_to_dict(*, stylist: Stylist) -> dict[str, object]:
    """将 Stylist 实例映射为后台 API 响应字典。

    Args:
        stylist (Stylist): 理发师实例。

    Returns:
        dict[str, object]: 含 id、name、queue_status 等字段的字典。
    """
    service_count = getattr(stylist, "service_count", None)
    if service_count is None:
        service_count = stylist.services.count()

    return {
        "id": stylist.id,
        "name": stylist.name,
        "location_id": stylist.location_id,
        "ticket_prefix": stylist.ticket_prefix,
        "queue_status": stylist.queue_status,
        "is_active": stylist.is_active,
        "service_count": service_count,
        "created_at": stylist.created_at,
        "updated_at": stylist.updated_at,
    }


def catalog_public_stylist_to_dict(*, stylist: Stylist) -> dict[str, object]:
    """将启用理发师映射为公开 API 响应字典。

    Args:
        stylist (Stylist): 理发师实例。

    Returns:
        dict[str, object]: 公开可见字段字典。
    """
    return {
        "id": stylist.id,
        "name": stylist.name,
        "ticket_prefix": stylist.ticket_prefix,
        "queue_status": stylist.queue_status,
    }


def catalog_public_service_to_dict(*, service: Service) -> dict[str, object]:
    """将启用服务映射为公开 API 响应字典。

    Args:
        service (Service): 服务项目实例。

    Returns:
        dict[str, object]: 公开可见字段字典。
    """
    return {
        "id": service.id,
        "name": service.name,
        "description": service.description,
        "duration_minutes": service.duration_minutes,
        "price_cents": service.price_cents,
        "currency": service.currency,
        "stylist_id": service.stylist_id,
    }


def catalog_service_get_for_stylist(*, stylist: Stylist, service_id: int) -> Service:
    """按 ID 查询指定理发师下的服务项目。

    Args:
        stylist (Stylist): 所属理发师。
        service_id (int): 服务 ID。

    Returns:
        Service: 匹配的服务项目。

    Raises:
        Service.DoesNotExist: 服务不存在或不属于该理发师。
    """
    return Service.objects.get(stylist=stylist, id=service_id)


def catalog_service_list_for_stylist_paginated(
    *,
    stylist: Stylist,
    page: int = 1,
    page_size: int = DEFAULT_CATALOG_PAGE_SIZE,
    q: str = "",
    active_only: bool = False,
) -> CatalogListResult[Service]:
    """分页列出指定理发师下的服务项目，按名称排序。

    Args:
        stylist (Stylist): 所属理发师。
        page (int): 页码，从 1 开始。
        page_size (int): 每页条数。
        q (str): 搜索关键词，匹配名称与说明。
        active_only (bool): 是否仅返回启用服务。

    Returns:
        CatalogListResult[Service]: 分页结果。
    """
    queryset = Service.objects.filter(stylist=stylist)
    if active_only:
        queryset = queryset.filter(is_active=True)
    if q:
        queryset = queryset.filter(Q(name__icontains=q) | Q(description__icontains=q))

    queryset = queryset.order_by("name")
    total = queryset.count()
    offset = (page - 1) * page_size
    items = list(queryset[offset : offset + page_size])
    return CatalogListResult(items=items, total=total)


def catalog_service_to_dict(*, service: Service) -> dict[str, object]:
    """将 Service 实例映射为 API 响应字典。

    Args:
        service (Service): 服务项目实例。

    Returns:
        dict[str, object]: 含 id、name、stylist_id 等字段的字典。
    """
    return {
        "id": service.id,
        "name": service.name,
        "description": service.description,
        "duration_minutes": service.duration_minutes,
        "price_cents": service.price_cents,
        "currency": service.currency,
        "is_active": service.is_active,
        "stylist_id": service.stylist_id,
        "created_at": service.created_at,
        "updated_at": service.updated_at,
    }
