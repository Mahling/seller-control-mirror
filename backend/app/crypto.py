from cryptography.fernet import Fernet, InvalidToken
import os

_key = os.getenv("SECRET_KEY")
if not _key:
    raise RuntimeError("SECRET_KEY is missing in environment")

try:
    fernet = Fernet(_key.encode())
except Exception as e:
    raise RuntimeError(
        "SECRET_KEY must be a Fernet key (32 bytes urlsafe-base64)."
    ) from e

def encrypt(text: str) -> str:
    return fernet.encrypt(text.encode()).decode()

def decrypt(token: str) -> str:
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        raise RuntimeError("Invalid SECRET_KEY or token")
