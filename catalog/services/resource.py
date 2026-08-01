from django.core.exceptions import ValidationError
from django.db import transaction
from tenants.models import Tenant

from catalog.models import Location, Resource
from scheduling.services.availability_cache import scheduling_availability_cache_invalidate


@transaction.atomic
def catalog_resource_create(
    *,
    tenant: Tenant,
    location: Location,
    name: str,
) -> Resource:
    """在指定地点下创建可预约资源。

    Args:
        tenant (Tenant): 目标租户。
        location (Location): 所属地点。
        name (str): 资源名称，同地点内唯一。

    Returns:
        Resource: 新创建的资源。

    Raises:
        ValidationError: 字段无效或违反唯一约束。
    """
    if location.tenant_id != tenant.id:
        raise ValidationError("地点不属于当前租户。")

    resource = Resource(
        tenant=tenant,
        location=location,
        name=name,
    )
    resource.full_clean()
    resource.save()
    return resource


@transaction.atomic
def catalog_resource_update(
    *,
    tenant: Tenant,
    resource: Resource,
    name: str | None = None,
    is_active: bool | None = None,
) -> Resource:
    """更新可预约资源字段。

    Args:
        tenant (Tenant): 目标租户。
        resource (Resource): 待更新的资源。
        name (str | None): 新名称。
        is_active (bool | None): 启用状态。

    Returns:
        Resource: 更新后的资源。

    Raises:
        ValidationError: 字段无效。
    """
    if resource.tenant_id != tenant.id:
        raise ValidationError("资源不属于当前租户。")

    if name is not None:
        resource.name = name
    if is_active is not None:
        resource.is_active = is_active

    resource.full_clean()
    resource.save()
    if is_active is not None:
        scheduling_availability_cache_invalidate(tenant_id=tenant.id)
    return resource


@transaction.atomic
def catalog_resource_delete(*, tenant: Tenant, resource: Resource) -> None:
    """物理删除未被引用的可预约资源。

    Args:
        tenant (Tenant): 目标租户。
        resource (Resource): 待删除资源。

    Raises:
        ValidationError: 资源不属于当前租户或已被业务引用。
    """
    if resource.tenant_id != tenant.id:
        raise ValidationError("资源不属于当前租户。")
    if resource.business_references.exists():
        raise ValidationError("该资源已被业务引用，只能停用。")
    resource.delete()
