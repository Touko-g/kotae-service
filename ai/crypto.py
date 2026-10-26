"""API Key 的加解密。

用户各自的 key 落在数据库里，必须密文存储：即使 db.sqlite3 被拖走，
没有 SECRET_KEY 也解不出明文。

刻意不复用 SECRET_KEY 原文，而是先用 sha256 派生一把独立的 Fernet 密钥，
避免同一把密钥被用在签名和加密两个场景上。
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class CredentialCryptoError(Exception):
    """密文解不开（通常是 SECRET_KEY 变更），按「未配置」处理让用户重填。"""


def _fernet() -> Fernet:
    digest = hashlib.sha256(
        f'ai-credential:{settings.SECRET_KEY}'.encode('utf-8')
    ).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode('utf-8')).decode('ascii')


def decrypt(cipher: str) -> str:
    try:
        return _fernet().decrypt(cipher.encode('ascii')).decode('utf-8')
    except (InvalidToken, ValueError, TypeError) as exc:
        raise CredentialCryptoError('API Key 无法解密，请重新填写') from exc


def mask_api_key(plain: str) -> str:
    """只露首尾各 4 位，用于「已配置」的展示。"""
    if not plain:
        return ''
    if len(plain) <= 8:
        return '*' * len(plain)
    return f'{plain[:4]}{"*" * 6}{plain[-4:]}'
