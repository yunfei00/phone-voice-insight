import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class CredentialDecryptionError(ValueError):
    pass


def _fernet() -> Fernet:
    source = str(settings.AI_CREDENTIAL_ENCRYPTION_KEY).encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(source).digest())
    return Fernet(key)


def encrypt_credential(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_credential(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeError, ValueError) as exc:
        raise CredentialDecryptionError("AI_CREDENTIAL_DECRYPTION_FAILED") from exc
