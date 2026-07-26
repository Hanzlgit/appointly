import logging
from typing import Protocol

from django.conf import settings

logger = logging.getLogger(__name__)

_SENT_MESSAGES: list[dict[str, str]] = []


class SmsAdapter(Protocol):
    def send_otp(self, *, phone: str, code: str) -> None:
        """发送 OTP 短信。

        Args:
            phone (str): 目标手机号。
            code (str): 验证码。
        """
        ...

    def send_booking_notification(self, *, phone: str, message: str) -> None:
        """发送预约相关通知短信。

        Args:
            phone (str): 目标手机号。
            message (str): 短信正文。
        """
        ...


class MockSmsAdapter:
    """开发环境使用的 Mock 短信适配器。"""

    def send_otp(self, *, phone: str, code: str) -> None:
        """记录 Mock 短信发送内容供开发与测试使用。

        Args:
            phone (str): 目标手机号。
            code (str): 验证码。
        """
        message = f"您的验证码是 {code}"
        payload = {"kind": "otp", "phone": phone, "code": code, "message": message}
        _SENT_MESSAGES.append(payload)
        logger.info("mock_sms_send phone=%s code=%s", phone, code)

    def send_booking_notification(self, *, phone: str, message: str) -> None:
        """记录预约通知 Mock 短信供开发与测试使用。

        Args:
            phone (str): 目标手机号。
            message (str): 短信正文。
        """
        payload = {"kind": "booking_notification", "phone": phone, "message": message}
        _SENT_MESSAGES.append(payload)
        logger.info("mock_sms_booking_notification phone=%s", phone)


def sms_adapter_get() -> SmsAdapter:
    """返回当前配置的短信适配器。

    Returns:
        SmsAdapter: 当前环境可用的短信适配器实例。

    Raises:
        ValueError: 配置了不支持的适配器名称。
    """
    adapter_name = getattr(settings, "SMS_ADAPTER", "mock")
    if adapter_name != "mock":
        raise ValueError(f"不支持的短信适配器: {adapter_name}")
    return MockSmsAdapter()


def sms_sent_message_list() -> list[dict[str, str]]:
    """返回 Mock 适配器已发送的短信列表（测试辅助）。

    Returns:
        list[dict[str, str]]: 已发送短信记录，含 ``phone``、``code``、``message`` 字段。
    """
    return list(_SENT_MESSAGES)


def sms_sent_message_clear() -> None:
    """清空 Mock 适配器发送记录（测试辅助）。"""
    _SENT_MESSAGES.clear()
