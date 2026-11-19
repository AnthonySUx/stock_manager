"""Bounded multipart parsing for stock intake without temporary files."""

import json
import re
from email.message import Message

from python_multipart import MultipartParser
from python_multipart.exceptions import MultipartParseError
from starlette.requests import ClientDisconnect, Request

from stock_manager.api.errors import APIError
from stock_manager.api.intake_schemas import MAX_IMAGE_BYTES, MAX_IMAGES

MAX_PAYLOAD_BYTES = 256 * 1024
MAX_REQUEST_BYTES = MAX_IMAGES * MAX_IMAGE_BYTES + MAX_PAYLOAD_BYTES + 64 * 1024
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


def _parse_boundary(content_type: str) -> str:
    header = Message()
    header["Content-Type"] = content_type
    boundary = header.get_boundary()
    if not boundary or not _BOUNDARY.fullmatch(boundary):
        raise _invalid_multipart()
    return boundary


class _ImageForm:
    """Collect a JSON payload and validated images through parser callbacks."""

    def __init__(self):
        self.payload: bytes | None = None
        self.images: list[dict] = []
        self.complete = False

    def on_part_begin(self) -> None:
        self.part = bytearray()
        self.mime: str | None = None
        self.disposition: bytes | None = None
        self.header_name = bytearray()
        self.header_value = bytearray()
        self.is_image = False

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self.header_name.extend(memoryview(data)[start:end])

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self.header_value.extend(memoryview(data)[start:end])

    def on_header_end(self) -> None:
        if self.header_name.lower() == b"content-disposition":
            if self.disposition is not None:
                raise _invalid_multipart()
            self.disposition = bytes(self.header_value)
        self.header_name.clear()
        self.header_value.clear()

    def on_headers_finished(self) -> None:
        if self.disposition is None:
            raise _invalid_multipart()
        header = Message()
        header["Content-Disposition"] = self.disposition.decode("latin-1")
        if header.get_content_disposition() != "form-data":
            raise _invalid_multipart()
        name = header.get_param("name", header="Content-Disposition")
        is_file = header.get_param("filename", header="Content-Disposition") is not None
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

    def on_end(self) -> None:
        self.complete = True

    def result(self) -> tuple[dict, list[dict]]:
        if not self.complete:
            raise _invalid_multipart()
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


async def read_image_upload(request: Request) -> tuple[dict, list[dict]]:
    """Check limits before retaining bytes, including when Content-Length is absent."""
    length = request.headers.get("content-length")
    if length is not None:
        if not length.isascii() or not length.isdecimal():
            raise _invalid_multipart()
        digits = length.lstrip("0") or "0"
        if len(digits) > len(str(MAX_REQUEST_BYTES)) or int(digits) > MAX_REQUEST_BYTES:
            raise _request_too_large()

    boundary = _parse_boundary(request.headers.get("content-type", ""))
    form = _ImageForm()
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
            if received > MAX_REQUEST_BYTES:
                raise _request_too_large()
            if not form.complete:
                parser.write(chunk)
        parser.finalize()
    except (MultipartParseError, ClientDisconnect):
        raise _invalid_multipart() from None
    return form.result()
