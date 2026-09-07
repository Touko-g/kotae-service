from django_filters import rest_framework as filters
from .models import User


class UserFilter(filters.FilterSet):
    username = filters.CharFilter(lookup_expr='icontains')
    email = filters.CharFilter(lookup_expr='exact')
    order = filters.OrderingFilter(fields=(
        ('id', 'id'),
        ('create_time', 'create_time'),
        ('update_time', 'update_time'),
        ('article', 'article')
    ), )

    class Meta:
        model = User
        fields = []
