"""
card_layout.py - Card visual regression guard for Fortune Oracle.

Provides structural metadata validation, PNG signature checks,
file size checks, subtitle privacy checks, and design token validation.
No pixel-level checksum; structural checks are deterministic and
independent of rendering engine internals.
"""

from __future__ import annotations

import importlib
import os
import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_WIDTH: int = 1024
EXPECTED_HEIGHT: int = 512
EXPECTED_ASPECT_RATIO: float = 2.0
MAX_FILE_BYTES: int = 3 * 1024 * 1024  # 3 MB
MAX_ANNOTATION_COUNT: int = 20
MAX_DATA_STRIP_CELLS: int = 8
MIN_DATA_STRIP_CELLS: int = 2

PURE_WHITE_BANNED: bool = True   # '#ffffff' 순백색 금지 정책
COOL_GRAY_BANNED: bool = True    # '#f0f0f0' cool gray 계열 금지 정책

DESIGN_TOKEN_NAMES: list[str] = [
    "CANVAS_PARCHMENT",
    "SURFACE_IVORY",
    "INK_BLUE",
    "YANG_WARM",
    "YIN_MUTED",
]

_PNG_MAGIC: bytes = b"\x89PNG\r\n\x1a\n"

_SENSITIVE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\d{4}-\d{2}-\d{2}"),          # YYYY-MM-DD
    re.compile(r"[\u4e00-\u9fff]{2,}"),          # 한자 2자 이상
    re.compile(r"\d{2}:\d{2}:\d{2}"),           # HH:MM:SS
]


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class CardLayoutMeta:
    width_px: int
    height_px: int
    aspect_ratio: float
    file_size_bytes: int
    candle_count: int
    data_strip_cells: int
    annotation_count: int
    has_title: bool
    has_subtitle: bool
    subtitle_contains_sensitive: bool  # must be False


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_card_meta(meta: CardLayoutMeta) -> list[str]:
    """Validate CardLayoutMeta. Returns list of error strings; empty = PASS."""
    errors: list[str] = []

    if meta.file_size_bytes <= 0:
        errors.append(
            f"file_size_bytes must be > 0, got {meta.file_size_bytes}"
        )
    if meta.file_size_bytes >= MAX_FILE_BYTES:
        errors.append(
            f"file_size_bytes {meta.file_size_bytes} exceeds MAX_FILE_BYTES "
            f"{MAX_FILE_BYTES} (3 MB fail-closed)"
        )
    if meta.width_px != EXPECTED_WIDTH:
        errors.append(
            f"width_px must be {EXPECTED_WIDTH}, got {meta.width_px}"
        )
    if meta.height_px != EXPECTED_HEIGHT:
        errors.append(
            f"height_px must be {EXPECTED_HEIGHT}, got {meta.height_px}"
        )
    if abs(meta.aspect_ratio - EXPECTED_ASPECT_RATIO) >= 0.1:
        errors.append(
            f"aspect_ratio {meta.aspect_ratio} deviates from "
            f"{EXPECTED_ASPECT_RATIO} by >= 0.1"
        )
    if meta.annotation_count > MAX_ANNOTATION_COUNT:
        errors.append(
            f"annotation_count {meta.annotation_count} > "
            f"MAX_ANNOTATION_COUNT {MAX_ANNOTATION_COUNT}"
        )
    if not (MIN_DATA_STRIP_CELLS <= meta.data_strip_cells <= MAX_DATA_STRIP_CELLS):
        errors.append(
            f"data_strip_cells {meta.data_strip_cells} out of range "
            f"[{MIN_DATA_STRIP_CELLS}, {MAX_DATA_STRIP_CELLS}]"
        )
    if meta.subtitle_contains_sensitive:
        errors.append(
            "subtitle_contains_sensitive must be False (민감정보 노출 금지)"
        )

    return errors


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def check_png_signature(file_path: str) -> bool:
    """Return True iff file exists and starts with PNG magic bytes."""
    try:
        with open(file_path, "rb") as fh:
            header = fh.read(8)
        return header == _PNG_MAGIC
    except Exception:
        return False


def check_file_size(file_path: str) -> int:
    """Return file size in bytes, or -1 if file does not exist."""
    try:
        return os.path.getsize(file_path)
    except OSError:
        return -1


# ---------------------------------------------------------------------------
# Privacy helper
# ---------------------------------------------------------------------------

def check_subtitle_privacy(subtitle: str) -> bool:
    """Return True if subtitle contains sensitive information."""
    for pattern in _SENSITIVE_PATTERNS:
        if pattern.search(subtitle):
            return True
    return False


# ---------------------------------------------------------------------------
# Design token validation
# ---------------------------------------------------------------------------

def validate_design_tokens() -> list[str]:
    """Return list of missing design token names; empty list = PASS."""
    missing: list[str] = []
    try:
        mod = importlib.import_module(
            "hermes_ext.fortune_oracle.design_tokens"
        )
    except ImportError:
        # Try relative-style fallback
        try:
            from hermes_ext.fortune_oracle import design_tokens as mod  # type: ignore
        except ImportError:
            return list(DESIGN_TOKEN_NAMES)

    for name in DESIGN_TOKEN_NAMES:
        if not hasattr(mod, name):
            missing.append(name)
    return missing
