from rest_framework.permissions import BasePermission


class RequiresTenantMembership(BasePermission):
    message = "无权访问该租户。"

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True

        tenant = view.get_tenant()
        return user.tenant_memberships.filter(tenant=tenant).exists()
