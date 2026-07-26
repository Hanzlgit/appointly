from django.core.exceptions import ValidationError
from django.db import transaction
from tenants.models import Tenant

from catalog.models import Location, Resource


@transaction.atomic
def catalog_location_create(
    *,
    tenant: Tenant,
    name: str,
    address: str = "",
    resource_ids: list[int] | None = None,
) -> Location:
    """在租户下创建服务地点。

    Args:
        tenant (Tenant): 目标租户。
        name (str): 地点名称，租户内唯一。
        address (str): 地址说明。
        resource_ids (list[int] | None): 关联资源 ID 列表。

    Returns:
        Location: 新创建的服务地点。

    Raises:
        ValidationError: 名称无效、资源不存在或违反唯一约束。
    """
    location = Location(tenant=tenant, name=name, address=address)
    location.full_clean()
    location.save()
    if resource_ids is not None:
        catalog_location_set_resources(
            tenant=tenant,
            location=location,
            resource_ids=resource_ids,
        )
    return location


@transaction.atomic
def catalog_location_update(
    *,
    tenant: Tenant,
    location: Location,
    name: str | None = None,
    address: str | None = None,
    is_active: bool | None = None,
    resource_ids: list[int] | None = None,
) -> Location:
    """更新服务地点字段与资源关联。

    Args:
        tenant (Tenant): 目标租户。
        location (Location): 待更新的地点。
        name (str | None): 新名称。
        address (str | None): 新地址。
        is_active (bool | None): 启用状态。
        resource_ids (list[int] | None): 关联资源 ID 列表。

    Returns:
        Location: 更新后的服务地点。

    Raises:
        ValidationError: 字段无效或资源不存在。
    """
    if location.tenant_id != tenant.id:
        raise ValidationError("地点不属于当前租户。")

    if name is not None:
        location.name = name
    if address is not None:
        location.address = address
    if is_active is not None:
        location.is_active = is_active

    location.full_clean()
    location.save()

    if resource_ids is not None:
        catalog_location_set_resources(
            tenant=tenant,
            location=location,
            resource_ids=resource_ids,
        )
    return location


@transaction.atomic
def catalog_location_set_resources(
    *,
    tenant: Tenant,
    location: Location,
    resource_ids: list[int],
) -> None:
    """设置地点关联的资源列表。

    Args:
        tenant (Tenant): 目标租户。
        location (Location): 服务地点。
        resource_ids (list[int]): 资源 ID 列表。

    Raises:
        ValidationError: 资源不存在或不属于当前租户。
    """
    resources = list(Resource.objects.filter(tenant=tenant, id__in=resource_ids))
    if len(resources) != len(set(resource_ids)):
        raise ValidationError("存在无效或不属于当前租户的资源。")
    location.resources.set(resources)


@transaction.atomic
def catalog_location_delete(*, tenant: Tenant, location: Location) -> None:
    """物理删除未被引用的服务地点。

    Args:
        tenant (Tenant): 目标租户。
        location (Location): 待删除地点。

    Raises:
        ValidationError: 地点不属于当前租户或已被业务引用。
    """
    if location.tenant_id != tenant.id:
        raise ValidationError("地点不属于当前租户。")
    if location.business_references.exists():
        raise ValidationError("该地点已被业务引用，只能停用。")
    location.delete()
