"""排班写操作触发的可用时段缓存失效。"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from scheduling.models import Booking, TimeSlot
from scheduling.services.availability_cache import scheduling_availability_cache_invalidate


@receiver(post_save, sender=TimeSlot)
def scheduling_timeslot_invalidate_availability_cache(
    sender,
    instance: TimeSlot,
    **kwargs,
) -> None:
    """时段创建或变更时失效租户可用性缓存。

    Args:
        sender: 信号发送方模型类。
        instance (TimeSlot): 变更的固定时段。
        **kwargs: Django 信号额外参数。
    """
    scheduling_availability_cache_invalidate(tenant_id=instance.tenant_id)


@receiver(post_delete, sender=TimeSlot)
def scheduling_timeslot_delete_invalidate_availability_cache(
    sender,
    instance: TimeSlot,
    **kwargs,
) -> None:
    """时段删除时失效租户可用性缓存。

    Args:
        sender: 信号发送方模型类。
        instance (TimeSlot): 被删除的固定时段。
        **kwargs: Django 信号额外参数。
    """
    scheduling_availability_cache_invalidate(tenant_id=instance.tenant_id)


@receiver(post_save, sender=Booking)
def scheduling_booking_invalidate_availability_cache(
    sender,
    instance: Booking,
    **kwargs,
) -> None:
    """预约创建或变更时失效租户可用性缓存。

    Args:
        sender: 信号发送方模型类。
        instance (Booking): 变更的预约。
        **kwargs: Django 信号额外参数。
    """
    scheduling_availability_cache_invalidate(tenant_id=instance.tenant_id)


@receiver(post_delete, sender=Booking)
def scheduling_booking_delete_invalidate_availability_cache(
    sender,
    instance: Booking,
    **kwargs,
) -> None:
    """预约删除时失效租户可用性缓存。

    Args:
        sender: 信号发送方模型类。
        instance (Booking): 被删除的预约。
        **kwargs: Django 信号额外参数。
    """
    scheduling_availability_cache_invalidate(tenant_id=instance.tenant_id)
