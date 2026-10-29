from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request

from apps.accounts.models import UserProfile, UserRole


def get_user_role(user: object) -> str:
    if not getattr(user, "is_authenticated", False):
        return ""
    if getattr(user, "is_superuser", False):
        return UserRole.ADMIN
    try:
        return str(user.profile.role)  # type: ignore[attr-defined]
    except UserProfile.DoesNotExist:
        return UserRole.VIEWER


class RoleBasedAccessPermission(BasePermission):
    """所有业务 API 需要登录；写操作仅管理员和分析员可用。"""

    def has_permission(self, request: Request, view: object) -> bool:  # noqa: ARG002
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return get_user_role(request.user) in {UserRole.ADMIN, UserRole.ANALYST}


class IsAdministrator(BasePermission):
    def has_permission(self, request: Request, view: object) -> bool:  # noqa: ARG002
        return bool(request.user and request.user.is_authenticated and get_user_role(request.user) == UserRole.ADMIN)


class IsAnalystOrAdministrator(BasePermission):
    def has_permission(self, request: Request, view: object) -> bool:  # noqa: ARG002
        return bool(
            request.user
            and request.user.is_authenticated
            and get_user_role(request.user) in {UserRole.ADMIN, UserRole.ANALYST}
        )
