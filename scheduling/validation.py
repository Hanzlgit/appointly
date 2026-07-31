from datetime import date, datetime, time, timedelta

from django.core.exceptions import ValidationError

from scheduling.constants import ALLOWED_SLOT_INTERVAL_MINUTES


def scheduling_window_minutes(*, start_time: time, end_time: time) -> int:
    """计算营业窗口的分钟数。

    Args:
        start_time (time): 窗口开始时间。
        end_time (time): 窗口结束时间。

    Returns:
        int: 窗口时长（分钟）。
    """
    start_dt = datetime.combine(date.min, start_time)
    end_dt = datetime.combine(date.min, end_time)
    return int((end_dt - start_dt).total_seconds() // 60)


def scheduling_slot_interval_validate(*, slot_interval_minutes: int) -> None:
    """校验时段间隔是否为允许值。

    Args:
        slot_interval_minutes (int): 时段间隔（分钟）。

    Raises:
        ValidationError: 间隔不在允许范围内。
    """
    if slot_interval_minutes not in ALLOWED_SLOT_INTERVAL_MINUTES:
        raise ValidationError("时段间隔必须为 15、30、45 或 60 分钟。")


def scheduling_schedule_rule_window_validate(
    *,
    start_time: time,
    end_time: time,
    slot_interval_minutes: int,
) -> None:
    """校验营业窗口可被时段间隔整除。

    Args:
        start_time (time): 窗口开始时间。
        end_time (time): 窗口结束时间。
        slot_interval_minutes (int): 时段间隔（分钟）。

    Raises:
        ValidationError: 窗口无效或无法整除。
    """
    scheduling_slot_interval_validate(slot_interval_minutes=slot_interval_minutes)
    if start_time >= end_time:
        raise ValidationError("结束时间必须晚于开始时间。")
    window_minutes = scheduling_window_minutes(start_time=start_time, end_time=end_time)
    if window_minutes % slot_interval_minutes != 0:
        raise ValidationError("营业窗口时长必须能被时段间隔整除。")


def scheduling_slot_times_in_window(
    *,
    start_time: time,
    end_time: time,
    slot_interval_minutes: int,
) -> list[tuple[time, time]]:
    """按间隔将营业窗口切分为完整时段起止时间对。

    Args:
        start_time (time): 窗口开始时间。
        end_time (time): 窗口结束时间。
        slot_interval_minutes (int): 时段间隔（分钟）。

    Returns:
        list[tuple[time, time]]: 各时段的本地起止时间。
    """
    scheduling_schedule_rule_window_validate(
        start_time=start_time,
        end_time=end_time,
        slot_interval_minutes=slot_interval_minutes,
    )
    slots: list[tuple[time, time]] = []
    current = datetime.combine(date.min, start_time)
    end_dt = datetime.combine(date.min, end_time)
    step = timedelta(minutes=slot_interval_minutes)
    while current + step <= end_dt:
        slot_end = current + step
        slots.append((current.time(), slot_end.time()))
        current = slot_end
    return slots
