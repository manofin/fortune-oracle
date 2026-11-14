"""gunicorn --chdir web wsgi:app; configure paths as described in README.md."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))
from fortune_web import create_app

app = create_app()
