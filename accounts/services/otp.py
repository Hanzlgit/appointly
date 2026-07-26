import secrets
from datetime import UTC, datetime

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError

from accounts.services.sms import sms_adapter_get

OTP_CACHE_PREFIX = "otp"


def _otp_cache_key(*, phone: str, kind: str) -> str:
    """构建 OTP 相关 cache key。

    Args:
        phone (str): 手机号。
        kind (str): 缓存类型，如 ``code``、``cooldown``、``daily``、``lock``。

    Returns:
        str: Redis / cache 使用的 key。
    """
    if kind == "daily":
        day = datetime.now(UTC).strftime("%Y%m%d")
        return f"{OTP_CACHE_PREFIX}:daily:{phone}:{day}"
    return f"{OTP_CACHE_PREFIX}:{kind}:{phone}"


def _generate_code() -> str:
    """生成指定位数的数字验证码。

    Returns:
        str: 固定长度的数字验证码字符串。
    """
    length = settings.OTP_CODE_LENGTH
    upper = 10**length
    return f"{secrets.randbelow(upper):0{length}d}"


def _ensure_not_locked(*, phone: str) -> None:
    """校验手机号未处于验证锁定状态。

    Args:
        phone (str): 手机号。

    Raises:
        ValidationError: 该手机号处于验证锁定状态。
    """
    if cache.get(_otp_cache_key(phone=phone, kind="lock")):
        raise ValidationError("验证过于频繁，请稍后再试。")


def customer_otp_send(*, phone: str) -> None:
    """向手机号发送登录验证码，并执行冷却、日限额与锁定检查。

    Args:
        phone (str): 目标手机号。

    Raises:
        ValidationError: 发送过于频繁、已达日上限或账号处于验证锁定状态。
    """
    _ensure_not_locked(phone=phone)

    if cache.get(_otp_cache_key(phone=phone, kind="cooldown")):
        raise ValidationError("发送过于频繁，请稍后再试。")

    daily_key = _otp_cache_key(phone=phone, kind="daily")
    daily_count = cache.get(daily_key) or 0
    if daily_count >= settings.OTP_DAILY_SEND_LIMIT:
        raise ValidationError("今日发送次数已达上限。")

    code = _generate_code()
    cache.set(
        _otp_cache_key(phone=phone, kind="code"),
        code,
        timeout=settings.OTP_TTL_SECONDS,
    )
    cache.set(
        _otp_cache_key(phone=phone, kind="cooldown"),
        1,
        timeout=settings.OTP_SEND_INTERVAL_SECONDS,
    )

    # 日计数在跨日自然失效；TTL 给到略大于一天
    cache.set(daily_key, daily_count + 1, timeout=settings.OTP_DAILY_COUNTER_TTL_SECONDS)

    sms_adapter_get().send_otp(phone=phone, code=code)


def customer_otp_verify(*, phone: str, code: str) -> None:
    """校验 OTP；失败累计达上限后锁定一段时间。

    Args:
        phone (str): 手机号。
        code (str): 用户提交的验证码。

    Raises:
        ValidationError: 验证码错误或已过期，或失败次数过多被锁定。
    """
    _ensure_not_locked(phone=phone)

    expected = cache.get(_otp_cache_key(phone=phone, kind="code"))
    if expected is None or expected != code:
        fail_key = _otp_cache_key(phone=phone, kind="fail")
        fail_count = (cache.get(fail_key) or 0) + 1
        cache.set(fail_key, fail_count, timeout=settings.OTP_LOCK_SECONDS)
        if fail_count >= settings.OTP_MAX_VERIFY_FAILURES:
            cache.set(
                _otp_cache_key(phone=phone, kind="lock"),
                1,
                timeout=settings.OTP_LOCK_SECONDS,
            )
            cache.delete(fail_key)
            raise ValidationError("验证失败次数过多，请稍后再试。")
        raise ValidationError("验证码错误或已过期。")

    cache.delete(_otp_cache_key(phone=phone, kind="code"))
    cache.delete(_otp_cache_key(phone=phone, kind="fail"))
    cache.delete(_otp_cache_key(phone=phone, kind="lock"))
