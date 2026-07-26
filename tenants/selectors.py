from django.contrib.auth.models import User

from tenants.models import PLATFORM_ADMIN_ROLE, Tenant, TenantCustomer, TenantScopedRecord


def tenant_get_by_slug(*, slug: str) -> Tenant:
    """按 slug 查询租户。

    Args:
        slug (str): 租户 slug。

    Returns:
        Tenant: 匹配的租户实例。

    Raises:
        Tenant.DoesNotExist: slug 不存在。
    """
    return Tenant.objects.get(slug=slug)


def tenant_membership_role_get_for_user(*, tenant: Tenant, user: User) -> str:
    """返回用户在指定租户下的角色。

    平台超管不在 membership 表中，返回 ``PLATFORM_ADMIN_ROLE``。

    Args:
        tenant (Tenant): 目标租户。
        user (User): 待查询的用户。

    Returns:
        str: 用户在租户下的角色标识。

    Raises:
        TenantMembership.DoesNotExist: 普通用户不是该租户成员。
    """
    if user.is_superuser:
        return PLATFORM_ADMIN_ROLE
    membership = user.tenant_memberships.get(tenant=tenant)
    return membership.role


def tenant_scoped_record_list_for_tenant(*, tenant: Tenant) -> list[TenantScopedRecord]:
    """列出租户下的 scoped records，按 label 排序。

    Args:
        tenant (Tenant): 目标租户。

    Returns:
        list[TenantScopedRecord]: 该租户下的 scoped record 列表。
    """
    return list(TenantScopedRecord.objects.filter(tenant=tenant).order_by("label"))


def tenant_customer_get_for_user(*, tenant: Tenant, user: User) -> TenantCustomer:
    """获取用户在租户下的客户档案。

    Args:
        tenant (Tenant): 目标租户。
        user (User): 客户用户。

    Returns:
        TenantCustomer: 租户客户档案。

    Raises:
        TenantCustomer.DoesNotExist: 用户在该租户下无客户档案。
    """
    return TenantCustomer.objects.select_related("tenant", "user__customer_profile").get(
        tenant=tenant,
        user=user,
    )


def tenant_customer_me_get_for_user(*, tenant: Tenant, user: User) -> dict[str, object]:
    """组装 ``/customers/me/`` 端点所需的展示字段。

    Args:
        tenant (Tenant): 目标租户。
        user (User): 当前登录的客户用户。

    Returns:
        dict[str, object]: 含 ``tenant_slug``、``phone``、``display_name`` 等字段的字典。
    """
    tenant_customer = tenant_customer_get_for_user(tenant=tenant, user=user)
    return {
        "tenant_slug": tenant.slug,
        "phone": tenant_customer.user.customer_profile.phone,
        "display_name": tenant_customer.display_name,
        "notes": tenant_customer.notes,
        "tags": tenant_customer.tags,
    }
