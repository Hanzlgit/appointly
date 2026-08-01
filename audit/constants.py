"""审计与看板相关常量。"""

AUDIT_RETENTION_DAYS = 180
AUDIT_PURGE_BATCH_SIZE = 1000
DASHBOARD_CACHE_TTL_SECONDS = 60
DASHBOARD_TREND_DAYS = 30


class AuditAction:
    """审计操作类型。"""

    BOOKING_STATUS_CHANGE = "booking_status_change"
    CAPACITY_ADJUST = "capacity_adjust"
    SCHEDULE_CHANGE = "schedule_change"
    SENSITIVE_VIEW = "sensitive_view"
    STAFF_BOOKING_CREATE = "staff_booking_create"
