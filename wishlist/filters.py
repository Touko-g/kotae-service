from django_filters import rest_framework as filters

from .models import Wish


class WishFilter(filters.FilterSet):
    completed = filters.BooleanFilter(field_name='completed')
    title = filters.CharFilter(lookup_expr='icontains')
    order = filters.OrderingFilter(fields=(
        ('id', 'id'),
        ('create_time', 'create_time'),
        ('update_time', 'update_time'),
        ('complete_time', 'complete_time'),
    ), )

    class Meta:
        model = Wish
        fields = []
