import os

from cryptography.fernet import Fernet, InvalidToken

from reelcraft.core.config import get_settings
from reelcraft.core.errors import ReelcraftError

KEY_FILE = "secret.key"


def _fernet() -> Fernet:
    """Key lives next to the database, created on first use, readable by the owner only."""
    path = get_settings().data_dir / KEY_FILE
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(Fernet.generate_key())
    return Fernet(path.read_bytes())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise ReelcraftError(
            f"Secret tidak bisa dibuka: {KEY_FILE} di data dir berubah atau hilang. "
            "Simpan ulang API key di Settings."
        ) from e


def mask(value: str) -> str:
    return f"••••{value[-4:]}" if len(value) > 8 else "••••"
