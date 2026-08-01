"""站内通知查询。"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth.models import User
from django.db.models import Q

from notifications.models import Notification


@dataclass(frozen=True)
class NotificationListResult:
    """分页通知列表查询结果。"""

    items: list[Notification]
    total: int
    unread_count: int


def notification_unread_count_for_user(*, user: User) -> int:
    """统计用户未读通知数。

    Args:
        user (User): 当前用户。

    Returns:
        int: 未读通知数量。
    """
    return Notification.objects.filter(recipient=user, read_at__isnull=True).count()


def notification_list_for_user(
    *,
    user: User,
    page: int = 1,
    page_size: int = 10,
    q: str = "",
    unread_only: bool = False,
    notification_type: str = "",
) -> NotificationListResult:
    """分页列出用户的站内通知。

    Args:
        user (User): 当前用户。
        page (int): 页码，从 1 开始。
        page_size (int): 每页条数。
        q (str): 搜索关键词，匹配标题与正文。
        unread_only (bool): 是否仅返回未读通知。
        notification_type (str): 按通知类型筛选。

    Returns:
        NotificationListResult: 分页结果与未读总数。
    """
    queryset = Notification.objects.filter(recipient=user).select_related("queue_ticket")

    if unread_only:
        queryset = queryset.filter(read_at__isnull=True)
    if notification_type:
        queryset = queryset.filter(notification_type=notification_type)
    if q:
        queryset = queryset.filter(Q(title__icontains=q) | Q(body__icontains=q))

    unread_count = notification_unread_count_for_user(user=user)
    total = queryset.count()
    offset = (page - 1) * page_size
    items = list(queryset[offset : offset + page_size])
    return NotificationListResult(items=items, total=total, unread_count=unread_count)
