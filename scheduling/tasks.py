from tenants.models import Tenant

from celery import shared_task
from scheduling.services.booking_transition import scheduling_booking_expire_overdue_pending
from scheduling.services.time_slot import scheduling_timeslots_generate_for_tenant


@shared_task(name="scheduling.expire_pending_bookings")
def scheduling_expire_pending_bookings() -> int:
    """将超时待确认预约标记为已过期并释放容量。

    Returns:
        int: 成功过期的预约数量。
    """
    return scheduling_booking_expire_overdue_pending()


@shared_task(name="scheduling.generate_timeslots_for_all_tenants")
def scheduling_generate_timeslots_for_all_tenants() -> int:
    """为所有活跃租户批量生成未来固定时段。

    Returns:
        int: 新创建的时段总数。
    """
    total_created = 0
    for tenant in Tenant.objects.filter(is_active=True):
        total_created += scheduling_timeslots_generate_for_tenant(tenant=tenant)
    return total_created
