import logging
from typing import Protocol

from django.conf import settings

logger = logging.getLogger(__name__)

_SENT_MESSAGES: list[dict[str, str]] = []


class SmsAdapter(Protocol):
    def send_otp(self, *, phone: str, code: str) -> None: ...


class MockSmsAdapter:
    def send_otp(self, *, phone: str, code: str) -> None:
        message = f"您的验证码是 {code}"
        payload = {"phone": phone, "code": code, "message": message}
        _SENT_MESSAGES.append(payload)
        logger.info("mock_sms_send phone=%s code=%s", phone, code)


def get_sms_adapter() -> SmsAdapter:
    adapter_name = getattr(settings, "SMS_ADAPTER", "mock")
    if adapter_name != "mock":
        raise ValueError(f"不支持的短信适配器: {adapter_name}")
    return MockSmsAdapter()


def sms_sent_messages() -> list[dict[str, str]]:
    return list(_SENT_MESSAGES)


def sms_sent_messages_clear() -> None:
    _SENT_MESSAGES.clear()
