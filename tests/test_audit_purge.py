"""审计日志保留期清理任务测试。"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from audit.constants import AuditAction
from audit.models import AuditLog
from audit.services.audit_log import audit_log_record
from django.contrib.auth.models import User
from django.test import TestCase
from tenants.models import Tenant


class AuditPurgeExpiredLogsTests(TestCase):
    """审计日志过期清理 Celery 任务测试。"""

    tenant: Tenant
    operator: User
    fixed_now: datetime

    def setUp(self):
        """准备租户、操作人与固定当前时间。"""
        self.fixed_now = datetime(2026, 7, 26, 12, 0, 0, tzinfo=UTC)
        self.tenant = Tenant.objects.create(
            slug="acme",
            name="Acme Corp",
            timezone="Asia/Shanghai",
        )
        self.operator = User.objects.create_user(username="admin", password="StrongPass123!")

    def _create_log_at(self, *, created_at: datetime) -> AuditLog:
        """创建指定 ``created_at`` 的审计记录。

        Args:
            created_at (datetime): 记录时间戳。

        Returns:
            AuditLog: 新建的审计记录。
        """
        audit_log = audit_log_record(
            tenant=self.tenant,
            operator=self.operator,
            action=AuditAction.BOOKING_STATUS_CHANGE,
            target_type="booking",
            target_id=1,
        )
        AuditLog.objects.filter(pk=audit_log.pk).update(created_at=created_at)
        audit_log.refresh_from_db()
        return audit_log

    def test_purge_removes_expired_and_keeps_within_retention(self):
        """清理任务删除超过 180 天的记录，保留期内记录不受影响。"""
        from audit.tasks import audit_purge_expired_logs

        expired_log = self._create_log_at(created_at=self.fixed_now - timedelta(days=181))
        kept_log = self._create_log_at(created_at=self.fixed_now - timedelta(days=30))

        with patch("django.utils.timezone.now", return_value=self.fixed_now):
            deleted_count = audit_purge_expired_logs()

        self.assertEqual(deleted_count, 1)
        self.assertFalse(AuditLog.objects.filter(pk=expired_log.pk).exists())
        self.assertTrue(AuditLog.objects.filter(pk=kept_log.pk).exists())

    def test_retention_boundary_keeps_179_day_old_record(self):
        """保留期内边界：恰好 179 天前的记录不被删除。"""
        from audit.tasks import audit_purge_expired_logs

        boundary_log = self._create_log_at(created_at=self.fixed_now - timedelta(days=179))

        with patch("django.utils.timezone.now", return_value=self.fixed_now):
            deleted_count = audit_purge_expired_logs()

        self.assertEqual(deleted_count, 0)
        self.assertTrue(AuditLog.objects.filter(pk=boundary_log.pk).exists())

    def test_celery_beat_schedule_registers_daily_purge(self):
        """清理任务在 Celery Beat 中按日调度。"""
        from django.conf import settings

        schedule_entry = settings.CELERY_BEAT_SCHEDULE["audit-purge-expired-logs"]
        self.assertEqual(schedule_entry["task"], "audit.purge_expired_logs")
        self.assertEqual(schedule_entry["schedule"], 86400.0)

    def test_batch_purge_deletes_all_expired_records(self):
        """分批删除会循环处理直到所有过期记录被清理。"""
        from audit.services.retention import audit_log_purge_expired

        expired_at = self.fixed_now - timedelta(days=200)
        for target_id in range(1, 6):
            audit_log = audit_log_record(
                tenant=self.tenant,
                operator=self.operator,
                action=AuditAction.BOOKING_STATUS_CHANGE,
                target_type="booking",
                target_id=target_id,
            )
            AuditLog.objects.filter(pk=audit_log.pk).update(created_at=expired_at)

        with patch("django.utils.timezone.now", return_value=self.fixed_now):
            deleted_count = audit_log_purge_expired(batch_size=2)

        self.assertEqual(deleted_count, 5)
        self.assertEqual(AuditLog.objects.count(), 0)
