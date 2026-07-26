from tenants.models import Tenant

from catalog.models import Location, Resource, Service


def catalog_location_get_for_tenant(*, tenant: Tenant, location_id: int) -> Location:
    """按 ID 查询租户下的服务地点。

    Args:
        tenant (Tenant): 目标租户。
        location_id (int): 地点 ID。

    Returns:
        Location: 匹配的服务地点。

    Raises:
        Location.DoesNotExist: 地点不存在或不属于租户。
    """
    return Location.objects.get(tenant=tenant, id=location_id)


def catalog_location_list_for_tenant(*, tenant: Tenant) -> list[Location]:
    """列出租户下的服务地点，按名称排序。

    Args:
        tenant (Tenant): 目标租户。

    Returns:
        list[Location]: 服务地点列表。
    """
    return list(
        Location.objects.filter(tenant=tenant).prefetch_related("resources").order_by("name"),
    )


def catalog_location_list_active_for_tenant(*, tenant: Tenant) -> list[Location]:
    """列出租户下启用的服务地点。

    Args:
        tenant (Tenant): 目标租户。

    Returns:
        list[Location]: 启用的服务地点列表。
    """
    return list(
        Location.objects.filter(tenant=tenant, is_active=True).order_by("name"),
    )


def catalog_location_to_dict(*, location: Location) -> dict[str, object]:
    """将 Location 实例映射为 API 响应字典。

    Args:
        location (Location): 服务地点实例。

    Returns:
        dict[str, object]: 含 id、name、resource_ids 等字段的字典。
    """
    return {
        "id": location.id,
        "name": location.name,
        "address": location.address,
        "is_active": location.is_active,
        "resource_ids": list(location.resources.values_list("id", flat=True)),
        "created_at": location.created_at,
        "updated_at": location.updated_at,
    }


def catalog_service_get_for_tenant(*, tenant: Tenant, service_id: int) -> Service:
    """按 ID 查询租户下的服务项目。

    Args:
        tenant (Tenant): 目标租户。
        service_id (int): 服务 ID。

    Returns:
        Service: 匹配的服务项目。

    Raises:
        Service.DoesNotExist: 服务不存在或不属于租户。
    """
    return Service.objects.get(tenant=tenant, id=service_id)


def catalog_service_list_for_tenant(*, tenant: Tenant) -> list[Service]:
    """列出租户下的服务项目，按名称排序。

    Args:
        tenant (Tenant): 目标租户。

    Returns:
        list[Service]: 服务项目列表。
    """
    return list(
        Service.objects.filter(tenant=tenant).prefetch_related("resources").order_by("name"),
    )


def catalog_service_list_active_for_tenant(*, tenant: Tenant) -> list[Service]:
    """列出租户下启用的服务项目。

    Args:
        tenant (Tenant): 目标租户。

    Returns:
        list[Service]: 启用的服务项目列表。
    """
    return list(
        Service.objects.filter(tenant=tenant, is_active=True)
        .prefetch_related("resources__locations")
        .order_by("name"),
    )


def catalog_service_to_dict(*, service: Service) -> dict[str, object]:
    """将 Service 实例映射为 API 响应字典。

    Args:
        service (Service): 服务项目实例。

    Returns:
        dict[str, object]: 含 id、name、resource_ids 等字段的字典。
    """
    return {
        "id": service.id,
        "name": service.name,
        "description": service.description,
        "duration_minutes": service.duration_minutes,
        "price_cents": service.price_cents,
        "currency": service.currency,
        "is_active": service.is_active,
        "resource_ids": list(service.resources.values_list("id", flat=True)),
        "created_at": service.created_at,
        "updated_at": service.updated_at,
    }


def catalog_resource_get_for_tenant(*, tenant: Tenant, resource_id: int) -> Resource:
    """按 ID 查询租户下的可预约资源。

    Args:
        tenant (Tenant): 目标租户。
        resource_id (int): 资源 ID。

    Returns:
        Resource: 匹配的资源。

    Raises:
        Resource.DoesNotExist: 资源不存在或不属于租户。
    """
    return Resource.objects.get(tenant=tenant, id=resource_id)


def catalog_resource_list_for_tenant(*, tenant: Tenant) -> list[Resource]:
    """列出租户下的可预约资源，按名称排序。

    Args:
        tenant (Tenant): 目标租户。

    Returns:
        list[Resource]: 资源列表。
    """
    return list(
        Resource.objects.filter(tenant=tenant).prefetch_related("locations").order_by("name"),
    )


def catalog_resource_to_dict(*, resource: Resource) -> dict[str, object]:
    """将 Resource 实例映射为 API 响应字典。

    Args:
        resource (Resource): 可预约资源实例。

    Returns:
        dict[str, object]: 含 id、name、location_ids 等字段的字典。
    """
    return {
        "id": resource.id,
        "name": resource.name,
        "resource_type": resource.resource_type,
        "staff_user_id": resource.staff_user_id,
        "is_active": resource.is_active,
        "location_ids": list(resource.locations.values_list("id", flat=True)),
        "created_at": resource.created_at,
        "updated_at": resource.updated_at,
    }


def catalog_public_location_to_dict(*, location: Location) -> dict[str, object]:
    """将启用地点映射为公开目录响应字典。

    Args:
        location (Location): 服务地点实例。

    Returns:
        dict[str, object]: 公开可见字段字典。
    """
    return {
        "id": location.id,
        "name": location.name,
        "address": location.address,
    }


def catalog_public_service_location_ids(*, service: Service) -> list[int]:
    """计算服务项目在哪些启用地点可预约。

    通过服务关联的启用资源及其所属启用地点推导。

    Args:
        service (Service): 服务项目实例。

    Returns:
        list[int]: 可预约地点 ID 列表（升序）。
    """
    location_ids: set[int] = set()
    for resource in service.resources.all():
        if not resource.is_active:
            continue
        for location in resource.locations.all():
            if location.is_active:
                location_ids.add(location.id)
    return sorted(location_ids)


def catalog_public_service_to_dict(*, service: Service) -> dict[str, object]:
    """将启用服务映射为公开目录响应字典。

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
        "location_ids": catalog_public_service_location_ids(service=service),
    }
