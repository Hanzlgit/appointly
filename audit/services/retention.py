"""审计日志保留期清理服务。"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from audit.constants import AUDIT_PURGE_BATCH_SIZE, AUDIT_RETENTION_DAYS
from audit.models import AuditLog

logger = logging.getLogger(__name__)


def audit_log_purge_expired(*, batch_size: int | None = None) -> int:
    """分批删除超过保留期的审计日志。

    Args:
        batch_size (int | None): 单批删除上限；默认使用 ``AUDIT_PURGE_BATCH_SIZE``。

    Returns:
        int: 本次任务删除的记录总数。
    """
    effective_batch_size = batch_size if batch_size is not None else AUDIT_PURGE_BATCH_SIZE
    cutoff = timezone.now() - timedelta(days=AUDIT_RETENTION_DAYS)
    total_deleted = 0

    while True:
        expired_ids = list(
            AuditLog.objects.filter(created_at__lt=cutoff)
            .order_by("pk")
            .values_list("pk", flat=True)[:effective_batch_size]
        )
        if not expired_ids:
            break
        deleted_count, _deleted_details = AuditLog.objects.filter(pk__in=expired_ids).delete()
        total_deleted += deleted_count

    logger.info(
        "audit_log_purge_expired deleted=%s cutoff=%s",
        total_deleted,
        cutoff.isoformat(),
    )
    return total_deleted
