from rest_framework import serializers

from .crypto import CredentialCryptoError, decrypt, encrypt, mask_api_key
from .models import AiCredential


class AiCredentialWriteSerializer(serializers.Serializer):
    """保存/更新凭据的入参。

    api_key 允许留空：更新时留空表示「沿用已保存的 key」，
    这样用户只想改默认模型时不必重新粘贴一遍密钥。
    """

    api_key = serializers.CharField(
        required=False, allow_blank=True, max_length=500, trim_whitespace=True)
    base_url = serializers.URLField(
        required=False, allow_blank=True, max_length=500)
    default_model = serializers.CharField(
        required=False, allow_blank=True, max_length=100, trim_whitespace=True)
    enabled = serializers.BooleanField(required=False)

    def validate_api_key(self, value):
        value = (value or '').strip()
        # 上游密钥都是可见 ASCII，混进空格/换行通常是从控制台复制时带上的
        if value and (value != value.strip() or any(ch.isspace() for ch in value)):
            raise serializers.ValidationError('API Key 不能包含空白字符')
        return value

    def validate_base_url(self, value):
        value = (value or '').strip()
        if not value:
            return value
        if not value.startswith(('http://', 'https://')):
            raise serializers.ValidationError('接口地址必须以 http:// 或 https:// 开头')
        return value.rstrip('/')

    def save(self, user):
        validated = self.validated_data
        credential = AiCredential.objects.filter(user=user).first()
        created = credential is None

        if created:
            if not validated.get('api_key'):
                raise serializers.ValidationError({'api_key': '首次配置必须填写 API Key'})
            credential = AiCredential(user=user, api_key=encrypt(validated['api_key']))

        if validated.get('api_key'):
            credential.api_key = encrypt(validated['api_key'])
        if validated.get('base_url'):
            credential.base_url = validated['base_url']
        if validated.get('default_model'):
            credential.default_model = validated['default_model']
        if 'enabled' in validated:
            credential.enabled = validated['enabled']

        credential.save()
        return credential, created


def serialize_credential(credential):
    """对外表示：只回掩码，绝不回明文或密文。"""
    if credential is None:
        return {
            'configured': False,
            'enabled': False,
            'api_key_masked': '',
            'base_url': '',
            'default_model': '',
            'update_time': None,
        }

    try:
        masked = mask_api_key(decrypt(credential.api_key))
        broken = False
    except CredentialCryptoError:
        # SECRET_KEY 换过导致旧密文解不开：告诉前端「需要重填」而不是假装配置好了
        masked = ''
        broken = True

    return {
        'configured': not broken,
        'enabled': credential.enabled,
        'api_key_masked': masked,
        'base_url': credential.base_url,
        'default_model': credential.default_model,
        'update_time': credential.update_time,
        'needs_reentry': broken,
    }
