from django.core.exceptions import ValidationError
from django.db import transaction

from catalog.models import Location, Stylist


@transaction.atomic
def catalog_stylist_create(
    *,
    location: Location,
    name: str,
    ticket_prefix: str = "",
    queue_status: str | None = None,
) -> Stylist:
    """在指定门店下创建理发师。

    Args:
        location (Location): 所属门店。
        name (str): 理发师名称，同门店内唯一。
        ticket_prefix (str): 取号前缀。
        queue_status (str | None): 当日接单状态。

    Returns:
        Stylist: 新创建的理发师。

    Raises:
        ValidationError: 字段无效或违反唯一约束。
    """
    stylist = Stylist(
        location=location,
        name=name,
        ticket_prefix=ticket_prefix,
    )
    if queue_status is not None:
        stylist.queue_status = queue_status
    stylist.full_clean()
    stylist.save()
    return stylist


@transaction.atomic
def catalog_stylist_update(
    *,
    stylist: Stylist,
    name: str | None = None,
    ticket_prefix: str | None = None,
    queue_status: str | None = None,
    is_active: bool | None = None,
) -> Stylist:
    """更新理发师字段。

    Args:
        stylist (Stylist): 待更新的理发师。
        name (str | None): 新名称。
        ticket_prefix (str | None): 新取号前缀。
        queue_status (str | None): 新接单状态。
        is_active (bool | None): 启用状态。

    Returns:
        Stylist: 更新后的理发师。

    Raises:
        ValidationError: 字段无效。
    """
    if name is not None:
        stylist.name = name
    if ticket_prefix is not None:
        stylist.ticket_prefix = ticket_prefix
    if queue_status is not None:
        stylist.queue_status = queue_status
    if is_active is not None:
        stylist.is_active = is_active

    stylist.full_clean()
    stylist.save()
    return stylist


@transaction.atomic
def catalog_stylist_delete(*, stylist: Stylist) -> None:
    """物理删除未被引用的理发师。

    Args:
        stylist (Stylist): 待删除理发师。

    Raises:
        ValidationError: 理发师已被业务引用。
    """
    if stylist.business_references.exists():
        raise ValidationError("该理发师已被业务引用，只能停用。")
    stylist.delete()
