"""Build the checked-in web font from the existing OFL-licensed Noto font.

Build dependencies only: fonttools and brotli. No external font request at runtime.
Keep web/fortune_web/static/fonts/OFL.txt with the output.
"""
from pathlib import Path

from fontTools import subset

repo = Path(__file__).resolve().parents[1]
root = repo / "plugins/hermes_ext/fortune_oracle"
web = repo / "web/fortune_web/static"
characters = set(range(0x20, 0x100)) | set(range(0xAC00, 0xD7A4))
characters |= set(range(0x1100, 0x1200)) | set(range(0x3130, 0x3190))
for source in list(root.glob("*.py")) + list(web.glob("*")):
    if source.suffix in (".py", ".html", ".js", ".css"):
        characters.update(ord(char) for char in source.read_text() if ord(char) > 127)
options = subset.Options()
options.flavor = "woff2"
options.layout_features = ["*"]
font = subset.load_font(str(root / "fonts/NotoSansCJKkr-Regular.otf"), options)
builder = subset.Subsetter(options=options)
builder.populate(unicodes=sorted(characters))
builder.subset(font)
target = web / "fonts/fortune-korean.woff2"
target.parent.mkdir(parents=True, exist_ok=True)
subset.save_font(font, str(target), options)
print(f"Built {target.name}: {target.stat().st_size} bytes")
