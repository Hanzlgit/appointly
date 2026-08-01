from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import CustomerProfile
from accounts.services.otp import customer_otp_verify


@transaction.atomic
def customer_authenticate(*, phone: str, code: str) -> User:
    """校验 OTP 并完成客户登录。

    首次登录时创建平台账号与 ``CustomerProfile``。

    Args:
        phone (str): 中国大陆手机号。
        code (str): 短信验证码。

    Returns:
        User: 登录成功的用户实例。

    Raises:
        ValidationError: 验证码无效。
    """
    customer_otp_verify(phone=phone, code=code)

    user = User.objects.filter(customer_profile__phone=phone).select_related("customer_profile").first()
    if user is None:
        user = User.objects.create_user(username=f"customer_{phone}")
        profile = CustomerProfile(user=user, phone=phone)
        profile.full_clean()
        profile.save()

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
