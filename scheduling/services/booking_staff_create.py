"""后台代建预约服务。"""

from __future__ import annotations

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from tenants.models import Tenant, TenantCustomer, TenantRole

from scheduling.models import Booking, TimeSlot
from scheduling.selectors import scheduling_staff_resource_ids_for_user
from scheduling.services.audit import scheduling_audit_record
from scheduling.services.booking_create import (
    _scheduling_booking_validate_capacity,
    _scheduling_booking_validate_time_slot,
    scheduling_booking_create,
)


def _scheduling_staff_booking_resolve_customer(
    *,
    tenant: Tenant,
    customer_id: int | None,
    contact_name: str,
    contact_phone: str,
) -> TenantCustomer:
    """解析代建预约的目标客户（现有档案或临时联系人）。

    Args:
        tenant (Tenant): 目标租户。
        customer_id (int | None): 现有客户档案 ID。
        contact_name (str): 临时联系人姓名。
        contact_phone (str): 临时联系人手机号。

    Returns:
        TenantCustomer: 目标客户档案。

    Raises:
        ValidationError: 参数无效或客户不存在。
    """
    if customer_id is not None:
        try:
            return TenantCustomer.objects.select_related("user__customer_profile").get(
                tenant=tenant,
                id=customer_id,
            )
        except TenantCustomer.DoesNotExist as exc:
            raise ValidationError("客户档案不存在。") from exc

    normalized_phone = contact_phone.strip()
    if not normalized_phone:
        raise ValidationError("必须指定 customer_id 或 contact_phone。")

    from accounts.models import CustomerProfile

    user = User.objects.filter(customer_profile__phone=normalized_phone).first()
    if user is None:
        user = User.objects.create_user(username=f"walkin_{normalized_phone}")
        CustomerProfile.objects.create(user=user, phone=normalized_phone)

    customer, _created = TenantCustomer.objects.get_or_create(
        tenant=tenant,
        user=user,
        defaults={"display_name": contact_name.strip()},
    )
    if contact_name.strip() and not customer.display_name:
        customer.display_name = contact_name.strip()
        customer.save(update_fields=["display_name", "updated_at"])
    return customer


def _scheduling_staff_booking_ensure_resource_access(
    *,
    tenant: Tenant,
    operator: User,
    role: str,
    time_slot: TimeSlot,
) -> None:
    """校验操作人对时段资源有代建权限。

    Args:
        tenant (Tenant): 目标租户。
        operator (User): 操作人。
        role (str): 操作人在租户下的角色。
        time_slot (TimeSlot): 目标固定时段。

    Raises:
        ValidationError: 工作人员无权操作该资源。
    """
    if role in {TenantRole.TENANT_ADMIN, "platform_admin"}:
        return

    allowed_resource_ids = scheduling_staff_resource_ids_for_user(
        tenant=tenant,
        user=operator,
    )
    if time_slot.resource_id not in allowed_resource_ids:
        raise ValidationError("无权为该资源代建预约。")


def scheduling_booking_staff_create(
    *,
    tenant: Tenant,
    operator: User,
    role: str,
    idempotency_key: str,
    service_id: int,
    party_size: int,
    time_slot_id: int,
    customer_id: int | None = None,
    contact_name: str = "",
    contact_phone: str = "",
) -> Booking:
    """后台代建预约，跳过联系人 OTP 但写入审计。

    遵守容量、时间窗口与重复预约规则；工作人员仅限关联资源。

    Args:
        tenant (Tenant): 目标租户。
        operator (User): 操作人。
        role (str): 操作人在租户下的角色。
        idempotency_key (str): 请求幂等键。
        service_id (int): 服务项目 ID。
        party_size (int): 预约人数。
        time_slot_id (int): 固定时段 ID。
        customer_id (int | None): 现有客户档案 ID。
        contact_name (str): 临时联系人姓名。
        contact_phone (str): 临时联系人手机号。

    Returns:
        Booking: 新建或幂等重放的预约。

    Raises:
        ValidationError: 参数无效、权限不足或业务规则不满足。
    """
    customer = _scheduling_staff_booking_resolve_customer(
        tenant=tenant,
        customer_id=customer_id,
        contact_name=contact_name,
        contact_phone=contact_phone,
    )

    existing = Booking.objects.filter(
        tenant=tenant,
        customer=customer,
        idempotency_key=idempotency_key,
    ).first()
    if existing is not None:
        return existing

    with transaction.atomic():
        time_slot = (
            TimeSlot.objects.select_for_update()
            .select_related("resource", "location")
            .get(tenant=tenant, id=time_slot_id)
        )
        _scheduling_staff_booking_ensure_resource_access(
            tenant=tenant,
            operator=operator,
            role=role,
            time_slot=time_slot,
        )

        booking = scheduling_booking_create(
            tenant=tenant,
            customer=customer,
            idempotency_key=idempotency_key,
            service_id=service_id,
            party_size=party_size,
            time_slot_id=time_slot_id,
            contact_name=contact_name,
            contact_phone=contact_phone,
        )

        scheduling_audit_record(
            tenant_id=tenant.id,
            operator_id=operator.id,
            action="staff_booking_create",
            target_type="booking",
            target_id=booking.id,
            details={
                "customer_id": customer.id,
                "time_slot_id": time_slot_id,
                "contact_phone": contact_phone.strip(),
                "skipped_contact_otp": True,
            },
        )
        return booking


def scheduling_staff_booking_validate_create(
    *,
    tenant: Tenant,
    operator: User,
    role: str,
    service_id: int,
    party_size: int,
    time_slot_id: int,
) -> None:
    """预校验代建是否满足容量与规则（不写入）。

    供 View 在容量不足时返回明确错误。

    Args:
        tenant (Tenant): 目标租户。
        operator (User): 操作人。
        role (str): 操作人在租户下的角色。
        service_id (int): 服务项目 ID。
        party_size (int): 预约人数。
        time_slot_id (int): 固定时段 ID。

    Raises:
        ValidationError: 校验失败。
    """
    from catalog.models import Service

    try:
        service = Service.objects.prefetch_related("resources").get(
            tenant=tenant,
            id=service_id,
            is_active=True,
        )
    except Service.DoesNotExist as exc:
        raise ValidationError("服务项目不存在或未启用。") from exc

    time_slot = TimeSlot.objects.select_related("resource").get(tenant=tenant, id=time_slot_id)
    _scheduling_staff_booking_ensure_resource_access(
        tenant=tenant,
        operator=operator,
        role=role,
        time_slot=time_slot,
    )
    _scheduling_booking_validate_time_slot(
        time_slot=time_slot,
        service=service,
        resource_id=None,
    )
    _scheduling_booking_validate_capacity(time_slot=time_slot, party_size=party_size)
