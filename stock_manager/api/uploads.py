"""Bounded multipart parsing without temporary files."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from email.message import Message

from python_multipart import MultipartParser
from python_multipart.exceptions import MultipartParseError
from starlette.requests import ClientDisconnect, Request

from stock_manager.api.errors import APIError
from stock_manager.api.intake_schemas import MAX_IMAGE_BYTES, MAX_IMAGES

MAX_PAYLOAD_BYTES = 256 * 1024
MAX_REQUEST_BYTES = MAX_IMAGES * MAX_IMAGE_BYTES + MAX_PAYLOAD_BYTES + 64 * 1024
MAX_AUDIO_BYTES = 8 * 1024 * 1024
_MAX_AUDIO_REQUEST_BYTES = MAX_AUDIO_BYTES + 64 * 1024
_MAX_AUDIO_FIELD_BYTES = 256
_SIGNATURE_BYTES = 12
_BOUNDARY = re.compile(r"[a-zA-Z0-9'()+_,./:=? -]{1,70}")


def image_mime(data: bytes, index: int) -> str:
    """Read the declared image format from the file signature."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    raise APIError(
        422, "intake_image_type_unsupported", "Expected a JPEG, PNG or WebP image", index=index,
    )


def _invalid_multipart() -> APIError:
    return APIError(422, "intake_multipart_invalid", "Invalid multipart image request")


def _request_too_large() -> APIError:
    return APIError(
        413, "intake_request_too_large", "Multipart request is too large", max_bytes=MAX_REQUEST_BYTES,
    )


class _MultipartForm:
    """Collect the part headers shared by the image and audio uploads."""

    def __init__(self):
        self.complete = False

    def on_part_begin(self) -> None:
        self.part = bytearray()
        self.disposition: bytes | None = None
        self.header_name = bytearray()
        self.header_value = bytearray()

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self.header_name.extend(memoryview(data)[start:end])

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self.header_value.extend(memoryview(data)[start:end])

    def on_header_end(self) -> None:
        if self.header_name.lower() == b"content-disposition":
            if self.disposition is not None:
                raise self.invalid()
            self.disposition = bytes(self.header_value)
        self.header_name.clear()
        self.header_value.clear()

    def on_headers_finished(self) -> None:
        if self.disposition is None:
            raise self.invalid()
        header = Message()
        header["Content-Disposition"] = self.disposition.decode("latin-1")
        if header.get_content_disposition() != "form-data":
            raise self.invalid()
        name = header.get_param("name", header="Content-Disposition")
        is_file = header.get_param("filename", header="Content-Disposition") is not None
        self.start_field(name, is_file)

    def on_end(self) -> None:
        self.complete = True


class _ImageForm(_MultipartForm):
    """Collect a JSON payload and validated images through parser callbacks."""

    invalid = staticmethod(_invalid_multipart)

    def __init__(self):
        super().__init__()
        self.payload: bytes | None = None
        self.images: list[dict] = []

    def start_field(self, name: str | None, is_file: bool) -> None:
        self.is_image = False
        self.mime: str | None = None
        if name == "images" and is_file:
            if len(self.images) >= MAX_IMAGES:
                raise APIError(422, "intake_images_too_many", "Too many images", max=MAX_IMAGES)
            self.is_image = True
        elif name != "payload" or is_file or self.payload is not None:
            raise _invalid_multipart()

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        size = len(self.part) + end - start
        if self.is_image:
            index = len(self.images)
            if size > MAX_IMAGE_BYTES:
                raise APIError(
                    422, "intake_image_too_large", "Image is too large", index=index, max_bytes=MAX_IMAGE_BYTES,
                )
            if self.mime is None and size >= _SIGNATURE_BYTES:
                needed = _SIGNATURE_BYTES - len(self.part)
                self.mime = image_mime(bytes(self.part) + data[start:start + needed], index)
        elif size > MAX_PAYLOAD_BYTES:
            raise _invalid_multipart()
        self.part.extend(memoryview(data)[start:end])

    def on_part_end(self) -> None:
        content = bytes(self.part)
        if self.is_image:
            mime = self.mime or image_mime(content, len(self.images))
            self.images.append({"data": content, "mime": mime})
        else:
            self.payload = content
        self.part.clear()

    def result(self) -> tuple[dict, list[dict]]:
        if not self.images:
            raise APIError(422, "intake_images_missing", "At least one image is required")
        if self.payload is None:
            raise _invalid_multipart()
        try:
            payload = json.loads(self.payload)
        except ValueError:
            raise _invalid_multipart() from None
        if not isinstance(payload, dict):
            raise _invalid_multipart()
        return payload, self.images


@dataclass(frozen=True)
class AudioUpload:
    data: bytes
    feature: str | None


def audio_too_large() -> APIError:
    return APIError(413, "audio_too_large", "Audio is too large", max_bytes=MAX_AUDIO_BYTES)


class _AudioForm(_MultipartForm):
    def __init__(self):
        super().__init__()
        self.audio: bytes | None = None
        self.feature: str | None = None

    @staticmethod
    def invalid() -> APIError:
        return APIError(422, "audio_upload_invalid", "Expected one audio file and an optional feature")

    def start_field(self, name: str | None, is_file: bool) -> None:
        if name == "audio" and is_file and self.audio is None:
            self.is_audio = True
        elif name == "feature" and not is_file and self.feature is None:
            self.is_audio = False
        else:
            raise self.invalid()

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        size = len(self.part) + end - start
        if self.is_audio:
            if size > MAX_AUDIO_BYTES:
                raise audio_too_large()
        elif size > _MAX_AUDIO_FIELD_BYTES:
            raise self.invalid()
        self.part.extend(memoryview(data)[start:end])

    def on_part_end(self) -> None:
        if self.is_audio:
            self.audio = bytes(self.part)
        else:
            try:
                value = self.part.decode("utf-8")
            except UnicodeDecodeError:
                raise self.invalid() from None
            if value not in ("stock_intake", "recipe_explore"):
                raise self.invalid()
            self.feature = value
        self.part.clear()

    def result(self) -> AudioUpload:
        if not self.audio:
            raise self.invalid()
        return AudioUpload(self.audio, self.feature)


async def read_image_upload(request: Request) -> tuple[dict, list[dict]]:
    form = _ImageForm()
    await _read_multipart(request, form, MAX_REQUEST_BYTES, _request_too_large)
    return form.result()


async def read_audio_upload(request: Request) -> AudioUpload:
    form = _AudioForm()
    await _read_multipart(request, form, _MAX_AUDIO_REQUEST_BYTES, audio_too_large)
    return form.result()


async def _read_multipart(
    request: Request,
    form: _ImageForm | _AudioForm,
    max_request_bytes: int,
    too_large: Callable[[], APIError],
) -> None:
    """Check limits before retaining bytes, including when Content-Length is absent."""
    length = request.headers.get("content-length")
    if length is not None:
        if not length.isascii() or not length.isdecimal():
            raise form.invalid()
        digits = length.lstrip("0") or "0"
        if len(digits) > len(str(max_request_bytes)) or int(digits) > max_request_bytes:
            raise too_large()

    header = Message()
    header["Content-Type"] = request.headers.get("content-type", "")
    boundary = header.get_boundary()
    if header.get_content_type() != "multipart/form-data" or not boundary or not _BOUNDARY.fullmatch(boundary):
        raise form.invalid()
    parser = MultipartParser(boundary, {
        "on_part_begin": form.on_part_begin,
        "on_header_field": form.on_header_field,
        "on_header_value": form.on_header_value,
        "on_header_end": form.on_header_end,
        "on_headers_finished": form.on_headers_finished,
        "on_part_data": form.on_part_data,
        "on_part_end": form.on_part_end,
        "on_end": form.on_end,
    })
    received = 0
    try:
        async for chunk in request.stream():
            received += len(chunk)
            if received > max_request_bytes:
                raise too_large()
            if not form.complete:
                parser.write(chunk)
        parser.finalize()
    except (MultipartParseError, ClientDisconnect):
        raise form.invalid() from None
    if not form.complete:
        raise form.invalid()
