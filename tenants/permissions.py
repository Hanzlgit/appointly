from rest_framework.permissions import BasePermission

from tenants.models import TenantRole


class RequiresTenantMembership(BasePermission):
    message = "无权访问该租户。"

    def has_permission(self, request, view) -> bool:
        """判断用户是否为租户成员或平台超管。

        Args:
            request: DRF 请求对象。
            view: 当前视图，须实现 ``get_tenant()``。

        Returns:
            bool: 有权限时返回 ``True``。
        """
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True

        tenant = view.get_tenant()
        return user.tenant_memberships.filter(tenant=tenant).exists()


class RequiresTenantAdmin(BasePermission):
    message = "需要租户管理员权限。"

    def has_permission(self, request, view) -> bool:
        """判断用户是否为租户管理员或平台超管。

        Args:
            request: DRF 请求对象。
            view: 当前视图，须实现 ``get_tenant()``。

        Returns:
            bool: 有权限时返回 ``True``。
        """
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True

        tenant = view.get_tenant()
        return user.tenant_memberships.filter(
            tenant=tenant,
            role=TenantRole.TENANT_ADMIN,
        ).exists()


class RequiresTenantCustomer(BasePermission):
    message = "需要该租户下的客户档案。"

    def has_permission(self, request, view) -> bool:
        """判断用户是否在该租户下拥有客户档案。

        Args:
            request: DRF 请求对象。
            view: 当前视图，须实现 ``get_tenant()``。

        Returns:
            bool: 有权限时返回 ``True``。
        """
        user = request.user
        if not user or not user.is_authenticated:
            return False

        tenant = view.get_tenant()
        return user.tenant_customers.filter(tenant=tenant).exists()
