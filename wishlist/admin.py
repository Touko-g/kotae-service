from django.contrib import admin

from .models import Wish


@admin.register(Wish)
class WishAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'title', 'completed', 'complete_time', 'public', 'create_time')
    list_filter = ('completed', 'public')
    search_fields = ('title', 'user__username')
