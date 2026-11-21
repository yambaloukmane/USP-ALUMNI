"""Fichiers (photos de profil, messages vocaux, galerie) dans Supabase Storage."""
import logging
from urllib.parse import urlparse

from .supabase_client import get_client

log = logging.getLogger(__name__)


class StorageError(Exception):
    pass


def upload(bucket: str, path: str, data: bytes, content_type: str) -> str:
    """Envoie un fichier et renvoie son adresse publique. Les noms sont uniques : jamais d'écrasement."""
    try:
        store = get_client().storage.from_(bucket)
        store.upload(path, data, {"content-type": content_type})
        return str(store.get_public_url(path)).rstrip("?")
    except Exception as exc:  # noqa: BLE001
        log.error("Storage upload %s/%s failed: %s", bucket, path, exc)
        raise StorageError("Impossible d'enregistrer le fichier.") from exc


def remove(bucket: str, path: str) -> None:
    try:
        get_client().storage.from_(bucket).remove([path])
    except Exception as exc:  # noqa: BLE001
        log.warning("Storage remove %s/%s failed: %s", bucket, path, exc)


def path_from_url(bucket: str, url: str) -> str:
    """Retrouve le chemin d'un fichier à partir de son adresse publique ('' si ce n'est pas le nôtre)."""
    marker = f"/storage/v1/object/public/{bucket}/"
    path = urlparse(url or "").path
    return path.split(marker, 1)[1] if marker in path else ""
