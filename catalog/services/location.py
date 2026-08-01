from django.core.exceptions import ValidationError
from django.db import transaction

from catalog.models import Location
from catalog.selectors import catalog_location_has_unfinished_scheduling_references


@transaction.atomic
def catalog_location_create(
    *,
    name: str,
    address: str = "",
) -> Location:
    """创建门店。

    Args:
        name (str): 门店名称，全局唯一。
        address (str): 地址说明。

    Returns:
        Location: 新创建的门店。

    Raises:
        ValidationError: 名称无效或违反唯一约束。
    """
    location = Location(name=name, address=address)
    location.full_clean()
    location.save()
    return location


@transaction.atomic
def catalog_location_update(
    *,
    location: Location,
    name: str | None = None,
    address: str | None = None,
    is_active: bool | None = None,
) -> Location:
    """更新门店字段。

    Args:
        location (Location): 待更新的门店。
        name (str | None): 新名称。
        address (str | None): 新地址。
        is_active (bool | None): 启用状态。

    Returns:
        Location: 更新后的门店。

    Raises:
        ValidationError: 字段无效。
    """
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
def catalog_location_delete(*, location: Location) -> None:
    """物理删除未被引用的门店。

    Args:
        location (Location): 待删除门店。

    Raises:
        ValidationError: 门店已被业务或排班引用。
    """
    if location.business_references.exists():
        raise ValidationError("该门店已被业务引用，只能停用。")
    if catalog_location_has_unfinished_scheduling_references(location_id=location.id):
        raise ValidationError("该门店存在排班或未完成预约，只能停用。")
    location.delete()
