from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from rest_framework_simplejwt.tokens import RefreshToken
from tenants.models import Tenant, TenantCustomer

from accounts.models import CustomerProfile
from accounts.services.otp import customer_otp_verify


def _find_user_by_phone(*, phone: str) -> User | None:
    return (
        User.objects.filter(Q(customer_profile__phone=phone) | Q(staff_profile__phone=phone))
        .select_related("customer_profile", "staff_profile")
        .first()
    )


@transaction.atomic
def customer_authenticate(*, phone: str, code: str, tenant: Tenant) -> User:
    customer_otp_verify(phone=phone, code=code)

    user = _find_user_by_phone(phone=phone)
    if user is None:
        user = User.objects.create_user(username=f"customer_{phone}")
        CustomerProfile.objects.create(user=user, phone=phone)
    elif not hasattr(user, "customer_profile"):
        CustomerProfile.objects.create(user=user, phone=phone)

    TenantCustomer.objects.get_or_create(tenant=tenant, user=user)
    return user


def customer_tokens_issue(*, user: User) -> dict[str, str]:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}
