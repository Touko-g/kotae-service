from rest_framework import serializers

from .models import Wish


class WishSerializer(serializers.ModelSerializer):
    user_info = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Wish
        fields = ('id', 'user_info', 'title', 'content', 'completed', 'complete_time', 'create_time', 'update_time')
        read_only_fields = ('complete_time', 'create_time', 'update_time')

    def get_user_info(self, obj):
        if not obj.user:
            return {}
        user = obj.user
        return {
            "id": user.id,
            "username": user.username,
            "avatar": user.avatar
        }

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError('标题不能为空')
        return value
