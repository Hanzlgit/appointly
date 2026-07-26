from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken


def _staff_user_get_by_login(*, login: str) -> User | None:
    """按用户名或后台手机号查找用户。

    Args:
        login (str): 用户名或后台手机号。

    Returns:
        User | None: 匹配的用户；未找到时返回 ``None``。
    """
    user = User.objects.filter(username=login).first()
    if user is None:
        user = (
            User.objects.filter(staff_profile__phone=login).select_related("staff_profile").first()
        )
    return user


def staff_authenticate(*, login: str, password: str) -> User:
    """校验后台用户凭据，支持用户名或手机号登录。

    Args:
        login (str): 用户名或后台手机号。
        password (str): 明文密码。

    Returns:
        User: 校验通过的用户实例。

    Raises:
        ValidationError: 用户名/手机号或密码错误。
    """
    user = _staff_user_get_by_login(login=login)
    if user is None or not user.check_password(password):
        raise ValidationError("用户名或密码错误。")
    return user


def staff_tokens_issue(*, user: User) -> dict[str, str]:
    """为后台用户签发 JWT access / refresh token。

    Args:
        user (User): 已认证的后台用户。

    Returns:
        dict[str, str]: 含 ``access`` 与 ``refresh`` 键的 token 字典。
    """
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}
