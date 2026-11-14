"""Bundled Korean fonts must work without host fonts or manual registration."""

from pathlib import Path
import warnings

import pytest

pytest.importorskip("matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
from matplotlib.ft2font import FT2Font
from PIL import Image, ImageStat

from hermes_ext.fortune_oracle import chart_renderer as renderer


@pytest.fixture
def isolated_fonts(monkeypatch):
    # Keep matplotlib's baseline Latin fonts, but remove any host Korean fonts.
    manager = fm.FontManager()
    manager.ttflist = [entry for entry in manager.ttflist
                      if Path(entry.fname).is_relative_to(matplotlib.get_data_path())]
    monkeypatch.setattr(fm, "fontManager", manager)
    monkeypatch.setattr(fm, "findfont", manager.findfont)
    exists = Path.exists
    monkeypatch.setattr(Path, "exists", lambda p: False if str(p).startswith(
        "/usr/share/fonts/") else exists(p))
    return manager


def test_bundle_is_registered_and_contains_korean_glyphs(isolated_fonts):
    name = renderer._setup_korean_font()
    assert name == "Noto Sans CJK KR"
    path = Path(isolated_fonts.findfont(name, fallback_to_default=False))
    assert path == Path(renderer.__file__).resolve().parent / "fonts/NotoSansCJKkr-Regular.otf"
    charmap = FT2Font(str(path)).get_charmap()
    assert all(ord(ch) in charmap for ch in "운세흐름평균최고최저오락자기성찰")
    count = len(isolated_fonts.ttflist)
    assert renderer._setup_korean_font() == name
    assert len(isolated_fonts.ttflist) == count


def test_png_automatically_uses_bundle(isolated_fonts, tmp_path, monkeypatch):
    # The renderer normally suppresses glyph warnings; expose them for this test.
    monkeypatch.setattr(renderer._warnings, "filterwarnings", lambda *a, **kw: None)
    with matplotlib.rc_context(), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        output = renderer.render_month_card_png(profile={"birth_date": "1990-05-15", "birth_time": "07:30", "gender": "male"}, year=2026, month=10,
                                               output_path=tmp_path / "card.png")
        assert matplotlib.rcParams["font.family"] == ["Noto Sans CJK KR"]
    assert not [w for w in caught if "Glyph" in str(w.message) and "missing" in str(w.message)]
    with Image.open(output) as im:
        assert im.format == "PNG"
        assert im.width > 500 and im.height > 250
        assert min(ImageStat.Stat(im.convert("RGB")).stddev) > 5


def test_damaged_sans_uses_bundled_serif(isolated_fonts, monkeypatch):
    addfont = isolated_fonts.addfont
    def load(path):
        if Path(path).name == "NotoSansCJKkr-Regular.otf":
            raise OSError("damaged font")
        return addfont(path)
    monkeypatch.setattr(isolated_fonts, "addfont", load)
    assert renderer._setup_korean_font() == "Noto Serif CJK KR"


def test_missing_fonts_remain_fail_open(isolated_fonts, monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda p: False)
    assert renderer._setup_korean_font() is None
