from rest_framework import permissions
from rest_framework.permissions import SAFE_METHODS


# 所有的请求都需要经过授权
class IsAuthorizePermission(permissions.DjangoModelPermissions):
    perms_map = {
        'GET': ['%(app_label)s.view_%(model_name)s'],
        'OPTIONS': [],
        'HEAD': [],
        'POST': ['%(app_label)s.add_%(model_name)s'],
        'PUT': ['%(app_label)s.change_%(model_name)s'],
        'PATCH': ['%(app_label)s.change_%(model_name)s'],
        'DELETE': ['%(app_label)s.delete_%(model_name)s'],
    }


class IsEditBySelfPermission(permissions.BasePermission):
    message = 'Editing posts is restricted to the author only'

    def has_object_permission(self, request, view, obj):
        # 安全的请求运行访问 允许GET，HEAD或OPTIONS 请求.
        if request.method in SAFE_METHODS:
            return True
        return obj.user == request.user or request.user.is_superuser
