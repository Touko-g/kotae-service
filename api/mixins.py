from .permissons import IsAuthorizePermission, IsEditBySelfPermission
from rest_framework import permissions


class StaffEditorPermissionMixin():
    permission_classes = [IsAuthorizePermission, IsEditBySelfPermission]


class UserQuerySetMixin():
    user_field = 'author'
    allow_staff_view = False

    def get_queryset(self, *args, **kwargs):
        user = self.request.user
        lookup_data = {}
        lookup_data[self.user_field] = user
        lookup_data['public'] = True
        qs = super().get_queryset(*args, **kwargs)
        if user.is_superuser:
            return qs
        return qs.filter(**lookup_data)


class PublicQuerySetMixin():
    def get_queryset(self, *args, **kwargs):
        user = self.request.user
        lookup_data = {}
        lookup_data['public'] = True
        qs = super().get_queryset(*args, **kwargs)
        if user.is_superuser:
            return qs
        return qs.filter(**lookup_data)
