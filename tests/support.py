"""Test helpers for API envelope responses."""

from catalog.models import Service
from scheduling.models import Booking, BookingStatus
from tenants.models import Tenant, TenantCustomer


def response_body(response) -> dict:
    """解析 HTTP 响应 JSON  body。

    Args:
        response: DRF / Django 测试客户端响应对象。

    Returns:
        dict: 解析后的 JSON 字典。
    """
    return response.json()


def api_data(response) -> dict | list | None:
    """从 envelope 响应中提取 ``data`` 字段。

    Args:
        response: DRF / Django 测试客户端响应对象。

    Returns:
        dict | list | None: 响应体中的 ``data`` 载荷。
    """
    body = response_body(response)
    assert "data" in body, body
    return body["data"]


def api_message(response) -> str:
    """从 envelope 响应中提取 ``message`` 字段。

    Args:
        response: DRF / Django 测试客户端响应对象。

    Returns:
        str: 响应体中的 ``message`` 文本。
    """
    return response_body(response)["message"]


def api_code(response) -> int:
    """从 envelope 响应中提取 ``code`` 字段。

    Args:
        response: DRF / Django 测试客户端响应对象。

    Returns:
        int: 响应体中的业务码。
    """
    return response_body(response)["code"]


def booking_create_for_test(
    *,
    tenant: Tenant,
    time_slot,
    status: str = BookingStatus.CONFIRMED,
    idempotency_key: str = "test-booking",
    service: Service | None = None,
    customer: TenantCustomer | None = None,
) -> Booking:
    """创建满足当前模型约束的测试预约。

    Args:
        tenant (Tenant): 所属租户。
        time_slot: 固定时段实例。
        status (str): 预约状态。
        idempotency_key (str): 幂等键。
        service (Service | None): 服务项目；省略时使用租户首个服务。
        customer (TenantCustomer | None): 客户档案；省略时自动创建。

    Returns:
        Booking: 新建的预约实例。
    """
    if service is None:
        service = Service.objects.filter(tenant=tenant).first()
        if service is None:
            service = Service.objects.create(
                tenant=tenant,
                location=time_slot.location,
                name="Test Service",
                duration_minutes=60,
            )
    if customer is None:
        from django.contrib.auth.models import User

        user = User.objects.create_user(username=f"test-customer-{idempotency_key}")
        customer = TenantCustomer.objects.create(tenant=tenant, user=user)

    return Booking.objects.create(
        tenant=tenant,
        customer=customer,
        time_slot=time_slot,
        service=service,
        status=status,
        idempotency_key=idempotency_key,
    )
