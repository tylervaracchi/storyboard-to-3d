# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
Image transport optimization for Vision-Language Model API calls.

Rationale: Anthropic server-side downscales any image whose long edge
exceeds 1568 px before the model ever sees it, so uploading full-resolution
1920x1080 PNG viewport captures wastes upload time and image tokens. A
~1288 px long-edge JPEG is visually equivalent for VLM scene judgment
(composition, actor placement, framing) and is typically 5-10x smaller on
the wire, which directly cuts per-iteration latency in the refinement loop.

Token estimate: image tokens are roughly (width * height) / 750. A
1920x1080 frame is ~2765 tokens, while a 1288x724 downscale of the same
frame is ~1243 tokens, so the downscale also roughly halves image tokens.

PIL (Pillow) is already a plugin dependency, but the import is guarded:
if PIL is unavailable the original bytes pass through untouched.
"""

import io
from pathlib import Path
from typing import Tuple, Union

try:
    import unreal
except ImportError:
    class _UnrealLogStub:
        """Print-based logging fallback so this module can be imported outside UE."""

        @staticmethod
        def log(message):
            print(message)

        @staticmethod
        def log_warning(message):
            print(f"[WARNING] {message}")

        @staticmethod
        def log_error(message):
            print(f"[ERROR] {message}")

    unreal = _UnrealLogStub()

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    Image = None
    PIL_AVAILABLE = False

_EXTENSION_MEDIA_TYPES = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
    '.gif': 'image/gif',
}

_pil_warning_emitted = False


def _media_type_for_path(image_path) -> str:
    """Map an image file extension to its MIME type (defaults to PNG)."""
    ext = Path(str(image_path)).suffix.lower()
    return _EXTENSION_MEDIA_TYPES.get(ext, 'image/png')


def _sniff_media_type(data: bytes) -> str:
    """Detect an image MIME type from magic bytes (defaults to PNG)."""
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if data.startswith(b'\xff\xd8'):
        return 'image/jpeg'
    if data.startswith(b'GIF87a') or data.startswith(b'GIF89a'):
        return 'image/gif'
    if len(data) >= 12 and data[0:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return 'image/png'


def _lanczos_filter():
    """Return the LANCZOS resampling filter across Pillow versions."""
    if hasattr(Image, 'LANCZOS'):
        return Image.LANCZOS
    return Image.Resampling.LANCZOS


def optimize_image_for_api(image_path_or_bytes: Union[str, bytes], max_edge: int = 1288, jpeg_quality: int = 85) -> Tuple[bytes, str]:
    """
    Downscale and re-encode an image for faster VLM API transport.

    Downscales so the long edge is at most max_edge (LANCZOS), converts
    RGBA/P to RGB, and re-encodes as JPEG at jpeg_quality. If the result
    is not at least 10 percent smaller than the input (some PNGs are
    already tiny), the original bytes are returned instead.

    Args:
        image_path_or_bytes: Path to an image file, or raw image bytes
        max_edge: Maximum long-edge dimension in pixels (default: 1288)
        jpeg_quality: JPEG re-encode quality 1-95 (default: 85)

    Returns:
        Tuple of (image bytes, media type string). On any failure, or when
        PIL is missing, returns the original bytes and their media type.
    """
    global _pil_warning_emitted

    if isinstance(image_path_or_bytes, (bytes, bytearray)):
        original = bytes(image_path_or_bytes)
        original_media_type = _sniff_media_type(original)
    else:
        with open(str(image_path_or_bytes), 'rb') as f:
            original = f.read()
        original_media_type = _media_type_for_path(image_path_or_bytes)

    if not PIL_AVAILABLE:
        if not _pil_warning_emitted:
            _pil_warning_emitted = True
            unreal.log_warning("[ImagePrep] PIL (Pillow) not available; sending original image bytes")
        return original, original_media_type

    try:
        img = Image.open(io.BytesIO(original))
        img.load()

        width, height = img.size
        long_edge = max(width, height)
        if long_edge > max_edge:
            scale = max_edge / float(long_edge)
            new_size = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
            img = img.resize(new_size, _lanczos_filter())

        # JPEG cannot encode alpha or palette modes (RGBA/P); flatten to RGB.
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')

        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=jpeg_quality)
        optimized = buffer.getvalue()
    except Exception as e:
        unreal.log_warning(f"[ImagePrep] Optimization failed ({e}); sending original image bytes")
        return original, original_media_type

    # Keep the original unless the re-encode is at least 10 percent smaller.
    if len(optimized) > len(original) * 0.9:
        return original, original_media_type

    return optimized, 'image/jpeg'
