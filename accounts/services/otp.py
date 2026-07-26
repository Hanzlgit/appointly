import secrets
from datetime import UTC, datetime

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError

from accounts.services.sms import get_sms_adapter


def _otp_code_key(phone: str) -> str:
    return f"otp:code:{phone}"


def _otp_cooldown_key(phone: str) -> str:
    return f"otp:cooldown:{phone}"


def _otp_daily_key(phone: str) -> str:
    day = datetime.now(UTC).strftime("%Y%m%d")
    return f"otp:daily:{phone}:{day}"


def _otp_fail_key(phone: str) -> str:
    return f"otp:fail:{phone}"


def _otp_lock_key(phone: str) -> str:
    return f"otp:lock:{phone}"


def _generate_code() -> str:
    length = settings.OTP_CODE_LENGTH
    upper = 10**length
    return f"{secrets.randbelow(upper):0{length}d}"


def _ensure_not_locked(*, phone: str) -> None:
    if cache.get(_otp_lock_key(phone)):
        raise ValidationError("验证过于频繁，请稍后再试。")


def customer_otp_send(*, phone: str) -> None:
    _ensure_not_locked(phone=phone)

    if cache.get(_otp_cooldown_key(phone)):
        raise ValidationError("发送过于频繁，请稍后再试。")

    daily_key = _otp_daily_key(phone)
    daily_count = cache.get(daily_key) or 0
    if daily_count >= settings.OTP_DAILY_SEND_LIMIT:
        raise ValidationError("今日发送次数已达上限。")

    code = _generate_code()
    cache.set(_otp_code_key(phone), code, timeout=settings.OTP_TTL_SECONDS)
    cache.set(_otp_cooldown_key(phone), 1, timeout=settings.OTP_SEND_INTERVAL_SECONDS)

    # 日计数在跨日自然失效；TTL 给到略大于一天
    cache.set(daily_key, daily_count + 1, timeout=settings.OTP_DAILY_COUNTER_TTL_SECONDS)

    get_sms_adapter().send_otp(phone=phone, code=code)


def customer_otp_verify(*, phone: str, code: str) -> None:
    _ensure_not_locked(phone=phone)

    expected = cache.get(_otp_code_key(phone))
    if expected is None or expected != code:
        fail_key = _otp_fail_key(phone)
        fail_count = (cache.get(fail_key) or 0) + 1
        cache.set(fail_key, fail_count, timeout=settings.OTP_LOCK_SECONDS)
        if fail_count >= settings.OTP_MAX_VERIFY_FAILURES:
            cache.set(_otp_lock_key(phone), 1, timeout=settings.OTP_LOCK_SECONDS)
            cache.delete(fail_key)
            raise ValidationError("验证失败次数过多，请稍后再试。")
        raise ValidationError("验证码错误或已过期。")

    cache.delete(_otp_code_key(phone))
    cache.delete(_otp_fail_key(phone))
    cache.delete(_otp_lock_key(phone))
