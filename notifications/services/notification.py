"""站内通知创建与查询。"""

from __future__ import annotations

import uuid

from django.contrib.auth.models import User
from scheduling.models import Booking

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
