"""Validate audio containers and calculate duration without decoding audio."""

from dataclasses import dataclass
from struct import unpack_from

from stock_manager.api.errors import APIError

_WAV_SAMPLE_RATES = (8000, 16000, 22050, 24000, 32000, 44100, 48000)
_OPUS_SAMPLE_RATE = 48000
_MAX_SECONDS = 120


@dataclass(frozen=True)
class AudioFormat:
    filename: str
    mime: str
    stereo_wav: bool = False


def unsupported_audio() -> APIError:
    return APIError(
        422, "audio_format_unsupported", "Expected PCM16 WAV or Ogg Opus",
        accepted=["wav_pcm16", "ogg_opus"],
    )


def _check_duration(samples: int, sample_rate: int) -> None:
    if samples > _MAX_SECONDS * sample_rate:
        raise APIError(422, "audio_too_long", "Audio is too long", max_seconds=_MAX_SECONDS)


def _wav_format(data: bytes) -> AudioFormat:
    if unpack_from("<I", data, 4)[0] != len(data) - 8:
        raise unsupported_audio()
    pcm = None
    data_size = None
    offset = 12
    while offset + 8 <= len(data):
        kind, size = unpack_from("<4sI", data, offset)
        start = offset + 8
        offset = start + size + size % 2  # RIFF pads odd-length chunks.
        if offset > len(data):
            raise unsupported_audio()
        if kind == b"fmt ":
            if pcm is not None or size < 16:
                raise unsupported_audio()
            pcm = unpack_from("<HHIIHH", data, start)
        elif kind == b"data":
            if data_size is not None:
                raise unsupported_audio()
            data_size = size

    if offset != len(data) or pcm is None or not data_size:
        raise unsupported_audio()
    encoding, channels, rate, byte_rate, frame_size, bits = pcm
    if encoding != 1 or bits != 16 or rate not in _WAV_SAMPLE_RATES or channels not in (1, 2):
        raise unsupported_audio()
    if frame_size != channels * 2 or byte_rate != rate * frame_size or data_size % frame_size:
        raise unsupported_audio()
    _check_duration(data_size // frame_size, rate)
    return AudioFormat("audio.wav", "audio/wav", stereo_wav=channels == 2)


def _ogg_format(data: bytes) -> AudioFormat:
    offset = 0
    pre_skip = None
    stream_serial = None
    while offset < len(data):
        if offset + 27 > len(data) or data[offset:offset + 5] != b"OggS\x00":
            raise unsupported_audio()
        flags, granule, serial = unpack_from("<BQI", data, offset + 5)
        table_start = offset + 27
        payload_start = table_start + data[offset + 26]
        lacing = data[table_start:payload_start]
        page_end = payload_start + sum(lacing)
        if page_end > len(data):
            raise unsupported_audio()
        if pre_skip is None:
            if (
                not flags & 2 or not lacing or not 19 <= lacing[0] < 255
                or data[payload_start:payload_start + 8] != b"OpusHead"
            ):
                raise unsupported_audio()
            pre_skip = unpack_from("<H", data, payload_start + 10)[0]
            stream_serial = serial
        elif serial != stream_serial or flags & 2:
            # Granule positions are relative to one logical stream.
            raise unsupported_audio()
        offset = page_end
        if flags & 4:
            if offset != len(data) or granule == 2**64 - 1 or granule < pre_skip:
                raise unsupported_audio()
            _check_duration(granule - pre_skip, _OPUS_SAMPLE_RATE)
            return AudioFormat("audio.ogg", "audio/ogg")
    raise unsupported_audio()


def check_audio(data: bytes) -> AudioFormat:
    """Use file content to select the format and enforce the duration limit."""
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return _wav_format(data)
    if data.startswith(b"OggS"):
        return _ogg_format(data)
    raise unsupported_audio()
