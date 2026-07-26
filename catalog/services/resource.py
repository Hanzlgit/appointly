from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from tenants.models import Tenant, TenantMembership

from catalog.models import Resource, ResourceType


@transaction.atomic
def catalog_resource_create(
    *,
    tenant: Tenant,
    name: str,
    resource_type: str,
    staff_user_id: int | None = None,
    location_ids: list[int] | None = None,
) -> Resource:
    """在租户下创建可预约资源。

    Args:
        tenant (Tenant): 目标租户。
        name (str): 资源名称，租户内唯一。
        resource_type (str): 资源类型。
        staff_user_id (int | None): 可选关联工作人员用户 ID。
        location_ids (list[int] | None): 关联地点 ID 列表。

    Returns:
        Resource: 新创建的资源。

    Raises:
        ValidationError: 字段无效、工作人员无效或违反唯一约束。
    """
    staff_user = catalog_resource_resolve_staff_user(
        tenant=tenant,
        staff_user_id=staff_user_id,
    )
    resource = Resource(
        tenant=tenant,
        name=name,
        resource_type=resource_type,
        staff_user=staff_user,
    )
    resource.full_clean()
    resource.save()
    if location_ids is not None:
        catalog_resource_set_locations(
            tenant=tenant,
            resource=resource,
            location_ids=location_ids,
        )
    return resource


@transaction.atomic
def catalog_resource_update(
    *,
    tenant: Tenant,
    resource: Resource,
    name: str | None = None,
    resource_type: str | None = None,
    staff_user_id: int | None = ...,  # noqa: B008
    is_active: bool | None = None,
    location_ids: list[int] | None = None,
) -> Resource:
    """更新可预约资源字段与地点关联。

    Args:
        tenant (Tenant): 目标租户。
        resource (Resource): 待更新的资源。
        name (str | None): 新名称。
        resource_type (str | None): 新资源类型。
        staff_user_id (int | None | Ellipsis): 工作人员用户 ID；``Ellipsis`` 表示不修改。
        is_active (bool | None): 启用状态。
        location_ids (list[int] | None): 关联地点 ID 列表。

    Returns:
        Resource: 更新后的资源。

    Raises:
        ValidationError: 字段无效或工作人员无效。
    """
    if resource.tenant_id != tenant.id:
        raise ValidationError("资源不属于当前租户。")

    if name is not None:
        resource.name = name
    if resource_type is not None:
        if resource_type not in ResourceType.values:
            raise ValidationError("无效的资源类型。")
        resource.resource_type = resource_type
    if staff_user_id is not ...:
        resource.staff_user = catalog_resource_resolve_staff_user(
            tenant=tenant,
            staff_user_id=staff_user_id,
        )
    if is_active is not None:
        resource.is_active = is_active

    resource.full_clean()
    resource.save()

    if location_ids is not None:
        catalog_resource_set_locations(
            tenant=tenant,
            resource=resource,
            location_ids=location_ids,
        )
    return resource


@transaction.atomic
def catalog_resource_set_locations(
    *,
    tenant: Tenant,
    resource: Resource,
    location_ids: list[int],
) -> None:
    """设置资源关联的地点列表。

    Args:
        tenant (Tenant): 目标租户。
        resource (Resource): 可预约资源。
        location_ids (list[int]): 地点 ID 列表。

    Raises:
        ValidationError: 地点不存在或不属于当前租户。
    """
    from catalog.models import Location

    locations = list(Location.objects.filter(tenant=tenant, id__in=location_ids))
    if len(locations) != len(set(location_ids)):
        raise ValidationError("存在无效或不属于当前租户的地点。")
    resource.locations.set(locations)


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


def catalog_resource_resolve_staff_user(
    *,
    tenant: Tenant,
    staff_user_id: int | None,
) -> User | None:
    """解析并校验资源可选关联的工作人员用户。

    Args:
        tenant (Tenant): 目标租户。
        staff_user_id (int | None): 工作人员用户 ID。

    Returns:
        User | None: 校验通过的用户；未指定时返回 ``None``。

    Raises:
        ValidationError: 用户不存在或不是租户成员。
    """
    if staff_user_id is None:
        return None

    try:
        user = User.objects.get(id=staff_user_id)
    except User.DoesNotExist as exc:
        raise ValidationError("工作人员用户不存在。") from exc

    if not TenantMembership.objects.filter(tenant=tenant, user=user).exists():
        raise ValidationError("工作人员必须是当前租户成员。")
    return user
