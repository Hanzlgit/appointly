from django.core.exceptions import ValidationError
from django.db import transaction
from tenants.models import Tenant

from catalog.models import Location


@transaction.atomic
def catalog_location_create(
    *,
    tenant: Tenant,
    name: str,
    address: str = "",
) -> Location:
    """在租户下创建服务地点。

    Args:
        tenant (Tenant): 目标租户。
        name (str): 地点名称，租户内唯一。
        address (str): 地址说明。

    Returns:
        Location: 新创建的服务地点。

    Raises:
        ValidationError: 名称无效或违反唯一约束。
    """
    location = Location(tenant=tenant, name=name, address=address)
    location.full_clean()
    location.save()
    return location


@transaction.atomic
def catalog_location_update(
    *,
    tenant: Tenant,
    location: Location,
    name: str | None = None,
    address: str | None = None,
    is_active: bool | None = None,
) -> Location:
    """更新服务地点字段。

    Args:
        tenant (Tenant): 目标租户。
        location (Location): 待更新的地点。
        name (str | None): 新名称。
        address (str | None): 新地址。
        is_active (bool | None): 启用状态。

    Returns:
        Location: 更新后的服务地点。

    Raises:
        ValidationError: 字段无效。
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
    return location


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
