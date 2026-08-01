"""站内通知创建与查询。"""

from __future__ import annotations

import uuid

from django.contrib.auth.models import User
from django.utils import timezone
from scheduling.models import Booking
from tenants.models import Tenant

from notifications.models import Notification


def notification_create(
    *,
    tenant_id: int,
    recipient: User,
    notification_type: str,
    title: str,
    body: str,
    booking: Booking | None = None,
    source_event_id: uuid.UUID | None = None,
) -> Notification:
    """创建一条站内通知。

    Args:
        tenant_id (int): 租户 ID。
        recipient (User): 接收用户。
        notification_type (str): 通知类型。
        title (str): 标题。
        body (str): 正文。
        booking (Booking | None): 关联预约。
        source_event_id (uuid.UUID | None): 源 Outbox 事件 ID。

    Returns:
        Notification: 新建通知。
    """
    return Notification.objects.create(
        tenant_id=tenant_id,
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        body=body,
        booking=booking,
        source_event_id=source_event_id,
    )


def notification_get_for_user(
    *,
    tenant: Tenant,
    user: User,
    notification_id: int,
) -> Notification:
    """获取用户可访问的单条通知。

    Args:
        tenant (Tenant): 目标租户。
        user (User): 当前用户。
        notification_id (int): 通知 ID。

    Returns:
        Notification: 匹配的通知。

    Raises:
        Notification.DoesNotExist: 通知不存在或不属于当前用户。
    """
    return Notification.objects.get(
        pk=notification_id,
        tenant=tenant,
        recipient=user,
    )


def notification_mark_read(
    *,
    tenant: Tenant,
    user: User,
    notification_id: int,
) -> Notification:
    """将单条通知标记为已读。

    Args:
        tenant (Tenant): 目标租户。
        user (User): 当前用户。
        notification_id (int): 通知 ID。

    Returns:
        Notification: 更新后的通知。
    """
    notification = notification_get_for_user(
        tenant=tenant,
        user=user,
        notification_id=notification_id,
    )
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    return notification


def notification_mark_all_read(*, tenant: Tenant, user: User) -> int:
    """将用户在该租户下的全部未读通知标记为已读。

    Args:
        tenant (Tenant): 目标租户。
        user (User): 当前用户。

    Returns:
        int: 被标记为已读的通知数量。
    """
    now = timezone.now()
    return Notification.objects.filter(
        tenant=tenant,
        recipient=user,
        read_at__isnull=True,
    ).update(read_at=now)
