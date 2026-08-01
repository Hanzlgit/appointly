from rest_framework.permissions import BasePermission


class RequiresStaff(BasePermission):
    """要求当前用户为后台工作人员或平台超管。"""

    message = "需要后台工作人员权限。"

    def has_permission(self, request, view) -> bool:
        """判断用户是否拥有后台工作人员权限。

        Args:
            request: DRF 请求对象。
            view: 当前视图。

        Returns:
            bool: 有权限时返回 ``True``。
        """
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        return hasattr(user, "staff_profile")
