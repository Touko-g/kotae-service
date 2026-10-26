from django.contrib import admin

from .crypto import CredentialCryptoError, decrypt, mask_api_key
from .models import AiCredential, AiUsage


@admin.register(AiCredential)
class AiCredentialAdmin(admin.ModelAdmin):
    list_display = ('user', 'masked_key', 'default_model', 'enabled', 'update_time')
    list_filter = ('enabled',)
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('masked_key', 'create_time', 'update_time')

    @admin.display(description='API Key')
    def masked_key(self, obj):
        try:
            return mask_api_key(decrypt(obj.api_key))
        except CredentialCryptoError:
            return '（无法解密，需重新填写）'


@admin.register(AiUsage)
class AiUsageAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'model', 'requests', 'total_tokens')
    list_filter = ('date', 'model')
    search_fields = ('user__username',)
    ordering = ('-date', '-total_tokens')
