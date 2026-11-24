"""Configure and store content-addressed recipe photos."""

import fcntl
import hashlib
import os
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryFile

from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_manager.api.errors import APIError
from stock_manager.api.models import RecipePhoto
from stock_manager.api.uploads import MAX_IMAGE_BYTES, image_mime, photo_too_large


Image.MAX_IMAGE_PIXELS = 40_000_000
_directory: Path | None = None
FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


@dataclass(frozen=True)
class StoredImage:
    sha256: str
    width: int
    height: int
    bytes: int


def reload_config() -> None:
    global _directory
    _directory = None
    value = os.getenv("MEDIA_DIR", "").strip()
    if not value:
        return
    path = Path(value).expanduser()
    try:
        path = path.resolve()
        path.mkdir(parents=True, exist_ok=True)
        with TemporaryFile(dir=path):
            pass
    except OSError as exc:
        raise RuntimeError(f"MEDIA_DIR must be a writable directory: {path}") from exc
    _directory = path


def available() -> bool:
    return _directory is not None


def require_media() -> Path:
    if _directory is None:
        raise APIError(503, "media_unavailable", "Recipe photo storage is not configured")
    return _directory


@contextmanager
def file_transaction(enabled: bool = True):
    """Serialize file reference changes across workers and the local importer."""
    directory = _directory if enabled else None
    if directory is None:
        yield
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def image_path(sha256: str, size: str = "full") -> Path:
    suffix = "_thumb" if size == "thumb" else ""
    return require_media() / "photos" / sha256[:2] / f"{sha256}{suffix}.jpg"


def _write_atomic(path: Path, data: bytes) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        temporary_path = Path(temp.name)
        try:
            temp.write(data)
            temp.close()
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)
    return True


def _encode(image: Image.Image, size: int, quality: int) -> bytes:
    image.thumbnail((size, size))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def store_image(data: bytes) -> StoredImage:
    require_media()
    if len(data) > MAX_IMAGE_BYTES:
        raise photo_too_large()
    try:
        image_format = FORMATS[image_mime(data, index=0)]
    except APIError as exc:
        raise APIError(422, "photo_type_unsupported", "Expected a JPEG, PNG or WebP photo") from exc

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=[image_format]) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
        full = _encode(image, 1600, 85)
        width, height = image.size
        # Derive the thumbnail from the bytes used as the storage key.
        with Image.open(BytesIO(full)) as reduced:
            thumb = _encode(reduced, 400, 80)
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise APIError(422, "photo_invalid", "The photo could not be decoded") from exc

    sha256 = hashlib.sha256(full).hexdigest()
    thumb_path = image_path(sha256, "thumb")
    created_thumb = _write_atomic(thumb_path, thumb)
    try:
        _write_atomic(image_path(sha256), full)
    except OSError:
        if created_thumb:
            thumb_path.unlink(missing_ok=True)
        raise
    return StoredImage(sha256, width, height, len(full))


def delete_files_if_unused(db: Session, sha256: str) -> None:
    if available() and db.scalar(
        select(RecipePhoto.id).where(RecipePhoto.sha256 == sha256).limit(1)
    ) is None:
        for size in ("full", "thumb"):
            image_path(sha256, size).unlink(missing_ok=True)
