"""审计相关 Celery 定时任务。"""

from audit.services.retention import audit_log_purge_expired
from celery import shared_task


@shared_task(name="audit.purge_expired_logs")
def audit_purge_expired_logs() -> int:
    """删除超过 ``AUDIT_RETENTION_DAYS`` 的审计日志。

    Returns:
        int: 本次任务删除的记录总数。
    """
    return audit_log_purge_expired()
