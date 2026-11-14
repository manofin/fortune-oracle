"""
hermes_ext._compat - 공통 fallback/호환 헬퍼

upstream Hermes 모듈이 sys.path에 없는 독립 실행 환경(smoke test, CI)에서도
import가 깨지지 않도록 최소 fallback을 제공한다.
런타임에서는 원본 upstream 모듈이 우선한다.
"""
from __future__ import annotations

# --- utc_now ---
try:
    from hermes_time import now as utc_now  # upstream 우선
except ImportError:
    from datetime import datetime, timezone
    def utc_now() -> datetime:
        return datetime.now(timezone.utc)

# --- get_hermes_home ---
try:
    from hermes_constants import get_hermes_home  # upstream 우선
except ImportError:
    import os
    from pathlib import Path
    def get_hermes_home() -> Path:
        return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))

# --- optional_import: try-import helper ---
def optional_import(module: str, attr: str | None = None, default=None):
    """upstream 모듈이 없으면 default 반환, 있으면 attr 또는 모듈 반환."""
    try:
        import importlib
        mod = importlib.import_module(module)
        if attr:
            return getattr(mod, attr, default)
        return mod
    except ImportError:
        return default

