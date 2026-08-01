from django.core.exceptions import ValidationError
from django.db import transaction

from catalog.models import Service, Stylist


@transaction.atomic
def catalog_service_create(
    *,
    stylist: Stylist,
    name: str,
    duration_minutes: int,
    description: str = "",
    price_cents: int = 0,
    currency: str = "CNY",
) -> Service:
    """在指定理发师下创建服务项目。

    Args:
        stylist (Stylist): 所属理发师。
        name (str): 服务名称，同理发师内唯一。
        duration_minutes (int): 展示时长（分钟）。
        description (str): 服务说明。
        price_cents (int): 价格（分）。
        currency (str): 货币代码。

    Returns:
        Service: 新创建的服务项目。

    Raises:
        ValidationError: 字段无效或违反唯一约束。
    """
    service = Service(
        stylist=stylist,
        name=name,
        description=description,
        duration_minutes=duration_minutes,
        price_cents=price_cents,
        currency=currency,
    )
    service.full_clean()
    service.save()
    return service


@transaction.atomic
def catalog_service_update(
    *,
    service: Service,
    name: str | None = None,
    description: str | None = None,
    duration_minutes: int | None = None,
    price_cents: int | None = None,
    currency: str | None = None,
    is_active: bool | None = None,
) -> Service:
    """更新服务项目字段。

    Args:
        service (Service): 待更新的服务。
        name (str | None): 新名称。
        description (str | None): 新说明。
        duration_minutes (int | None): 新展示时长。
        price_cents (int | None): 新价格。
        currency (str | None): 新货币代码。
        is_active (bool | None): 启用状态。

    Returns:
        Service: 更新后的服务项目。

    Raises:
        ValidationError: 字段无效。
    """
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
    return service


@transaction.atomic
def catalog_service_delete(*, service: Service) -> None:
    """物理删除未被引用的服务项目。

    Args:
        service (Service): 待删除服务。

    Raises:
        ValidationError: 服务已被业务引用。
    """
    if service.business_references.exists():
        raise ValidationError("该服务已被业务引用，只能停用。")
    service.delete()
