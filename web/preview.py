"""Local QA only: loopback, temporary database, no production data or credentials."""
import argparse
from pathlib import Path
import secrets
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))
from fortune_web import create_app
from werkzeug.serving import make_server

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--port", type=int, default=8765)
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix="fortune-web-preview-") as temporary:
    app = create_app({"SECRET_KEY": secrets.token_hex(32), "WEB_STORE": str(Path(temporary) / "preview.sqlite3"),
                      "COOKIE_SECURE": False, "VERSION": "local-preview"})
    server = make_server("127.0.0.1", args.port, app, threaded=True)
    print(f"Local QA: http://127.0.0.1:{server.server_port} (temporary store; not public hosting)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        stop, worker = app.extensions["fortune_cleanup"]
        stop.set()
        worker.join(timeout=10)
