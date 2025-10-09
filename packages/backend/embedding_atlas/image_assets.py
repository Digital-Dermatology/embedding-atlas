# Copyright (c) 2025 Apple Inc. Licensed under MIT License.

from __future__ import annotations

import base64
import math
from collections import defaultdict
from dataclasses import dataclass
from io import BytesIO
from typing import Iterable

import pandas as pd

IMAGE_TOKEN_PREFIX = "ea://image/"
IMAGE_RELATIVE_PATH = "images"
DEFAULT_THUMBNAIL_SIZE = 256


@dataclass(frozen=True)
class ImageAsset:
    """Container for a serialized image asset."""

    content: bytes
    mime: str


def _is_nan(value) -> bool:
    return isinstance(value, float) and math.isnan(value)


def _decode_data_url(text: str) -> bytes | None:
    try:
        prefix, encoded = text.split(",", 1)
    except ValueError:
        return None
    if not prefix.startswith("data:image/"):
        return None
    try:
        return base64.b64decode(encoded)
    except (base64.binascii.Error, ValueError):
        return None


def _decode_base64(text: str) -> bytes | None:
    try:
        data = base64.b64decode(text, validate=True)
    except (base64.binascii.Error, ValueError):
        return None
    if detect_image_type(data) == "application/octet-stream":
        return None
    return data


def normalize_image_bytes(value) -> bytes | None:
    """Return image bytes for supported value types or None otherwise."""
    if value is None or _is_nan(value):
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    if isinstance(value, dict):
        bytes_value = value.get("bytes")
        if isinstance(bytes_value, (bytes, bytearray, memoryview)):
            return bytes(bytes_value)
        if isinstance(bytes_value, str):
            decoded = _decode_base64(bytes_value)
            if decoded is not None:
                return decoded
        path_value = value.get("path")
        if isinstance(path_value, str):
            try:
                with open(path_value, "rb") as f:
                    return f.read()
            except OSError:
                pass
        array_value = value.get("array")
        if array_value is not None:
            bytes_from_array = _bytes_from_array(array_value)
            if bytes_from_array is not None:
                return bytes_from_array
        return None
    if isinstance(value, str):
        if value.startswith("data:image/"):
            return _decode_data_url(value)
        decoded = _decode_base64(value)
        if decoded is not None:
            return decoded
    pil_bytes = _bytes_from_pil_image(value)
    if pil_bytes is not None:
        return pil_bytes
    array_bytes = _bytes_from_array(value)
    if array_bytes is not None:
        return array_bytes
    return None


def _bytes_from_pil_image(value) -> bytes | None:
    try:
        from PIL import Image
    except ImportError:
        return None

    if isinstance(value, Image.Image):
        buffer = BytesIO()
        value.save(buffer, format="PNG")
        return buffer.getvalue()
    return None


def _bytes_from_array(value) -> bytes | None:
    try:
        import numpy as np
    except ImportError:
        np = None

    if np is not None and isinstance(value, np.ndarray):
        value = value.astype("uint8")
        try:
            from PIL import Image
        except ImportError:
            return value.tobytes()
        mode = "L"
        if value.ndim == 3 and value.shape[2] == 3:
            mode = "RGB"
        elif value.ndim == 3 and value.shape[2] == 4:
            mode = "RGBA"
        elif value.ndim not in (2, 3):
            return None
        img = Image.fromarray(value, mode=mode)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()
    return None


def detect_image_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data.startswith(b"BM"):
        return "image/bmp"
    if data.startswith(b"\x49\x49\x2a\x00") or data.startswith(b"\x4d\x4d\x00\x2a"):
        return "image/tiff"
    return "application/octet-stream"


def _encode_thumbnail(data: bytes, mime: str, max_size: int) -> tuple[bytes, str]:
    try:
        from PIL import Image
    except ImportError:
        # Pillow is optional; fall back to original bytes.
        return data, mime

    with Image.open(BytesIO(data)) as img:
        img = img.convert("RGBA") if img.mode in ("P", "RGBA", "LA") else img.convert("RGB")
        img.thumbnail((max_size, max_size))
        buffer = BytesIO()
        if img.mode == "RGB":
            img.save(buffer, format="JPEG", quality=85, optimize=True)
            return buffer.getvalue(), "image/jpeg"
        img.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue(), "image/png"


def _extension_for_mime(mime: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
    }.get(mime, ".bin")


def _candidate_columns(df: pd.DataFrame) -> Iterable[str]:
    for column in df.columns:
        if df[column].dtype == "object":
            yield column


def extract_image_assets(
    df: pd.DataFrame,
    id_column: str,
    max_thumbnail: int = DEFAULT_THUMBNAIL_SIZE,
) -> tuple[dict[str, dict[str, ImageAsset]], set[str]]:
    """Replace image-like values with lightweight tokens and return serialized assets."""
    assets: dict[str, dict[str, ImageAsset]] = defaultdict(dict)
    processed_columns: set[str] = set()

    for column in _candidate_columns(df):
        series = df[column]
        updated_rows = False

        for index, value in series.items():
            bytes_value = normalize_image_bytes(value)
            if bytes_value is None:
                continue

            mime = detect_image_type(bytes_value)
            if mime == "application/octet-stream":
                continue
            try:
                thumb_bytes, thumb_mime = _encode_thumbnail(bytes_value, mime, max_thumbnail)
            except Exception:
                continue
            extension = _extension_for_mime(thumb_mime)

            row_identifier = df.at[index, id_column]
            filename = f"{row_identifier}{extension}"
            token = f"{IMAGE_TOKEN_PREFIX}{column}/{filename}"

            df.at[index, column] = token
            assets[column][filename] = ImageAsset(content=thumb_bytes, mime=thumb_mime)
            updated_rows = True

        if updated_rows:
            processed_columns.add(column)

    cleaned = {column: dict(files) for column, files in assets.items()}
    return cleaned, processed_columns
