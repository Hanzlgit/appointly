from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from rest_framework_simplejwt.tokens import RefreshToken
from tenants.models import Tenant, TenantCustomer
from tenants.selectors import tenant_get_by_slug

from accounts.models import CustomerProfile
from accounts.services.otp import customer_otp_verify


def _find_user_by_phone(*, phone: str) -> User | None:
    """按手机号查找客户或后台用户。

    Args:
        phone (str): 中国大陆手机号。

    Returns:
        User | None: 匹配的用户；未找到时返回 ``None``。
    """
    return (
        User.objects.filter(Q(customer_profile__phone=phone) | Q(staff_profile__phone=phone))
        .select_related("customer_profile", "staff_profile")
        .first()
    )


@transaction.atomic
def customer_authenticate(*, phone: str, code: str, tenant_slug: str) -> User:
    """校验 OTP 并完成客户登录。

    首次登录时创建平台账号与 ``CustomerProfile``，并确保租户客户档案存在。

    Args:
        phone (str): 中国大陆手机号。
        code (str): 短信验证码。
        tenant_slug (str): 租户 slug，用于建立租户客户档案。

    Returns:
        User: 登录成功的用户实例。

    Raises:
        ValidationError: 验证码无效、租户不存在或已停用。
    """
    customer_otp_verify(phone=phone, code=code)

    try:
        tenant = tenant_get_by_slug(slug=tenant_slug)
    except Tenant.DoesNotExist as exc:
        raise ValidationError("租户不存在。") from exc
    if not tenant.is_active:
        raise ValidationError("租户已停用。")

    user = _find_user_by_phone(phone=phone)
    if user is None:
        user = User.objects.create_user(username=f"customer_{phone}")
        profile = CustomerProfile(user=user, phone=phone)
        profile.full_clean()
        profile.save()
    elif not hasattr(user, "customer_profile"):
        profile = CustomerProfile(user=user, phone=phone)
        profile.full_clean()
        profile.save()

    TenantCustomer.objects.get_or_create(tenant=tenant, user=user)
    return user


def customer_tokens_issue(*, user: User) -> dict[str, str]:
    """为客户用户签发 JWT access / refresh token。

    Args:
        user (User): 已认证的客户用户。

    Returns:
        dict[str, str]: 含 ``access`` 与 ``refresh`` 键的 token 字典。
    """
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}
