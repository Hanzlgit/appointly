from django.core.exceptions import ValidationError
from django.db import transaction
from tenants.models import Tenant

from catalog.models import Resource, Service


@transaction.atomic
def catalog_service_create(
    *,
    tenant: Tenant,
    name: str,
    duration_minutes: int,
    description: str = "",
    price_cents: int = 0,
    currency: str = "CNY",
    resource_ids: list[int] | None = None,
) -> Service:
    """在租户下创建服务项目。

    Args:
        tenant (Tenant): 目标租户。
        name (str): 服务名称，租户内唯一。
        duration_minutes (int): 展示时长（分钟）。
        description (str): 服务说明。
        price_cents (int): 价格（分）。
        currency (str): 货币代码。
        resource_ids (list[int] | None): 关联资源 ID 列表。

    Returns:
        Service: 新创建的服务项目。

    Raises:
        ValidationError: 字段无效或资源不存在。
    """
    service = Service(
        tenant=tenant,
        name=name,
        description=description,
        duration_minutes=duration_minutes,
        price_cents=price_cents,
        currency=currency,
    )
    service.full_clean()
    service.save()
    if resource_ids is not None:
        catalog_service_set_resources(
            tenant=tenant,
            service=service,
            resource_ids=resource_ids,
        )
    return service


@transaction.atomic
def catalog_service_update(
    *,
    tenant: Tenant,
    service: Service,
    name: str | None = None,
    description: str | None = None,
    duration_minutes: int | None = None,
    price_cents: int | None = None,
    currency: str | None = None,
    is_active: bool | None = None,
    resource_ids: list[int] | None = None,
) -> Service:
    """更新服务项目字段与资源关联。

    Args:
        tenant (Tenant): 目标租户。
        service (Service): 待更新的服务。
        name (str | None): 新名称。
        description (str | None): 新说明。
        duration_minutes (int | None): 新展示时长。
        price_cents (int | None): 新价格。
        currency (str | None): 新货币代码。
        is_active (bool | None): 启用状态。
        resource_ids (list[int] | None): 关联资源 ID 列表。

    Returns:
        Service: 更新后的服务项目。

    Raises:
        ValidationError: 字段无效或资源不存在。
    """
    if service.tenant_id != tenant.id:
        raise ValidationError("服务不属于当前租户。")

    if name is not None:
        service.name = name
    if description is not None:
        service.description = description
    if duration_minutes is not None:
        service.duration_minutes = duration_minutes
    if price_cents is not None:
        service.price_cents = price_cents
    if currency is not None:
        service.currency = currency
    if is_active is not None:
        service.is_active = is_active

    service.full_clean()
    service.save()

    if resource_ids is not None:
        catalog_service_set_resources(
            tenant=tenant,
            service=service,
            resource_ids=resource_ids,
        )
    return service


@transaction.atomic
def catalog_service_set_resources(
    *,
    tenant: Tenant,
    service: Service,
    resource_ids: list[int],
) -> None:
    """设置服务关联的资源列表。

    Args:
        tenant (Tenant): 目标租户。
        service (Service): 服务项目。
        resource_ids (list[int]): 资源 ID 列表。

    Raises:
        ValidationError: 资源不存在或不属于当前租户。
    """
    resources = list(Resource.objects.filter(tenant=tenant, id__in=resource_ids))
    if len(resources) != len(set(resource_ids)):
        raise ValidationError("存在无效或不属于当前租户的资源。")
    service.resources.set(resources)


@transaction.atomic
def catalog_service_delete(*, tenant: Tenant, service: Service) -> None:
    """物理删除未被引用的服务项目。

    Args:
        tenant (Tenant): 目标租户。
        service (Service): 待删除服务。

    Raises:
        ValidationError: 服务不属于当前租户或已被业务引用。
    """
    if service.tenant_id != tenant.id:
        raise ValidationError("服务不属于当前租户。")
    if service.business_references.exists():
        raise ValidationError("该服务已被业务引用，只能停用。")
    service.delete()
