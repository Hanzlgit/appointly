"""站内通知查询。"""

from __future__ import annotations

from django.contrib.auth.models import User
from tenants.models import Tenant

from notifications.models import Notification


def notification_list_for_user(*, tenant: Tenant, user: User) -> list[Notification]:
    """列出用户在租户下的站内通知。

    Args:
        tenant (Tenant): 目标租户。
        user (User): 当前用户。

    Returns:
        list[Notification]: 按创建时间倒序的通知列表。
    """
    return list(
        Notification.objects.filter(tenant=tenant, recipient=user).select_related("booking")
    )
