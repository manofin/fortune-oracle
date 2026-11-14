"""Same-origin mobile web API. All user data lives outside the Telegram store."""
from functools import wraps
import hashlib
import hmac
import os
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit

from flask import Flask, g, jsonify, request, render_template_string, send_file
from werkzeug.exceptions import HTTPException

from . import metrics, service
from .storage import WebStore


def create_app(config=None):
    static = Path(__file__).parent / "static"
    app = Flask(__name__, static_folder=str(static), static_url_path="/assets")
    app.config.update(
        SECRET_KEY=os.environ.get("FORTUNE_WEB_SECRET", ""),
        WEB_STORE=os.environ.get("FORTUNE_WEB_STORE", ""),
        COOKIE_SECURE=True, COOKIE_NAME="fortune_session", SESSION_LIFETIME=90 * 86400,
        MAX_CONTENT_LENGTH=8192, MAX_FORM_PARTS=20,
        NOW=None, VERSION=os.environ.get("FORTUNE_WEB_VERSION", "development"),
        CLEANUP_INTERVAL=60,
        PUBLIC_ORIGIN=os.environ.get("FORTUNE_WEB_PUBLIC_ORIGIN", ""),
        INTEGRATED_ENABLED=os.environ.get("FORTUNE_WEB_INTEGRATED_ENABLED", "") == "1",
        BIRTH_LOCATION_ENABLED=os.environ.get("FORTUNE_WEB_BIRTH_LOCATION_ENABLED", "") == "1",
    )
    app.config.update(config or {})
    # Environment opt-in is exactly "1"; Python callers must supply actual True.
    # A non-empty string such as "false" must never publish a reserved feature.
    for flag in ("INTEGRATED_ENABLED", "BIRTH_LOCATION_ENABLED"):
        app.config[flag] = app.config[flag] is True
    index_template = (static / "index.html").read_text(encoding="utf-8")
    if len(app.config["SECRET_KEY"]) < 32 or not app.config["WEB_STORE"]:
        raise RuntimeError("Set FORTUNE_WEB_SECRET (at least 32 characters) and a separate FORTUNE_WEB_STORE path")
    public_origin = app.config["PUBLIC_ORIGIN"].rstrip("/")
    if public_origin:
        parsed = urlsplit(public_origin)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment):
            raise RuntimeError("FORTUNE_WEB_PUBLIC_ORIGIN must be an HTTPS origin without a path")
        # Configure the public address explicitly; never trust client-supplied proxy headers.
        app.config["TRUSTED_HOSTS"] = [parsed.hostname, "127.0.0.1", "localhost"]
        if not app.config["COOKIE_SECURE"]:
            raise RuntimeError("Public hosting requires secure session cookies")
    store = WebStore(app.config["WEB_STORE"])
    store.purge_expired()
    app.extensions["fortune_store"] = store
    if app.config.get("START_CLEANUP", not app.testing):
        stop = threading.Event()
        def cleanup():
            while not stop.wait(app.config["CLEANUP_INTERVAL"]):
                try:
                    store.purge_expired()
                except Exception:
                    app.logger.error("fortune-web: expired session cleanup failed")
        worker = threading.Thread(target=cleanup, name="fortune-web-cleanup", daemon=True)
        worker.start()
        app.extensions["fortune_cleanup"] = (stop, worker)
    calculations = threading.BoundedSemaphore(4)
    rate_lock, rates = threading.Lock(), {}

    def error(code, text, status):
        return jsonify(ok=False, computed=False, error=code, text=text), status

    def csrf(token):
        return hmac.new(app.config["SECRET_KEY"].encode(), token.encode(), hashlib.sha256).hexdigest()

    def measure(token, event, view):
        try:
            store.record_event(token, metrics.metric_day(app.config["NOW"]), event, view)
        except Exception:
            # Measurement must not break registration or expose the input in logs.
            app.logger.warning("fortune-web: measurement unavailable")

    @app.before_request
    def boundaries():
        if not request.path.startswith("/api/"):
            return
        if isinstance(request.routing_exception, HTTPException):
            raise request.routing_exception
        # Request bodies and identifiers are never logged; this bounded rate map is memory-only.
        now = time.monotonic()
        identity = request.remote_addr or "unknown"
        with rate_lock:
            expired = [key for key, value in rates.items() if now - value[0] >= 60]
            for key in expired:
                del rates[key]
            if identity not in rates and len(rates) >= 4096:
                return error("busy", "요청이 많습니다. 잠시 후 다시 시도해 주세요.", 429)
            start, count = rates.get(identity, (now, 0))
            if count >= 120:
                return error("rate_limited", "요청이 많습니다. 잠시 후 다시 시도해 주세요.", 429)
            rates[identity] = (start, count + 1)
        token = request.cookies.get(app.config["COOKIE_NAME"], "")
        try:
            g.token, g.record = token, store.find(token)
        except Exception:
            if request.path == "/api/events" and request.method == "POST":
                return error("interest_unavailable", "관심을 기록하지 못했습니다. 잠시 후 다시 눌러 주세요.", 503)
            raise
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if g.record is None:
                return error("session_required", "이용 세션이 만료됐습니다. 화면을 새로고침해 주세요.", 401)
            supplied_csrf = request.headers.get("X-CSRF-Token", "")
            if not supplied_csrf.isascii() or not hmac.compare_digest(supplied_csrf, csrf(token)):
                return error("csrf_invalid", "요청을 확인하지 못했습니다. 화면을 새로고침해 주세요.", 403)
            origin = request.headers.get("Origin")
            expected_origin = public_origin or request.host_url.rstrip("/")
            if origin and origin.rstrip("/") != expected_origin:
                return error("origin_invalid", "요청한 화면의 주소를 확인해 주세요.", 403)

    @app.after_request
    def private_response(response):
        response.headers.update({
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        })
        if request.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
        if public_origin or request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.errorhandler(Exception)
    def fail_closed(exc):
        status = exc.code if isinstance(exc, HTTPException) else 500
        # Do not expose traceback, input, internal paths, or engine stderr.
        return error("request_failed", "계산 결과가 아님\n요청을 처리하지 못했습니다. 입력을 확인하거나 잠시 후 다시 시도해 주세요.", status)

    def require_profile(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if g.record is None:
                return error("session_required", "계산 결과가 아님\n화면을 새로고침해 주세요.", 401)
            if not g.record["profile"]:
                return error("profile_required", "계산 결과가 아님\n출생정보를 먼저 등록해 주세요.", 409)
            if not calculations.acquire(blocking=False):
                return error("busy", "계산 결과가 아님\n계산 요청이 많습니다. 잠시 후 다시 시도해 주세요.", 503)
            try:
                return fn(*args, **kwargs)
            finally:
                calculations.release()
        return wrapped

    def require_integrated(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not app.config["INTEGRATED_ENABLED"]:
                return error("feature_unavailable", "아직 제공하지 않는 풀이입니다.", 404)
            return fn(*args, **kwargs)
        return wrapped

    @app.get("/")
    def index():
        # Common metadata only: never load a session/profile for preview crawlers.
        return render_template_string(
            index_template, public_origin=public_origin or request.host_url.rstrip("/"),
            integrated_enabled=app.config["INTEGRATED_ENABLED"],
            birth_location_enabled=app.config["BIRTH_LOCATION_ENABLED"],
        )

    @app.get("/samples")
    @app.get("/samples/")
    def samples():
        # Public editorial examples: no session lookup, calculation, or profile.
        return send_file(static / "samples.html")

    @app.get("/healthz")
    def health():
        return jsonify(status="ok", version=app.config["VERSION"])

    @app.get("/api/session")
    def bootstrap():
        token = g.token if g.record is not None else store.create(app.config["SESSION_LIFETIME"])
        profile = g.record["profile"] if g.record else None
        measure(token, "visit", "entry")
        response = jsonify(ok=True, profile=profile, csrf=csrf(token), storage="this_browser", retention_days=90,
                           reading_window=service.reading_window(profile, app.config["NOW"]))
        if g.record is None:
            response.set_cookie(app.config["COOKIE_NAME"], token, max_age=app.config["SESSION_LIFETIME"],
                                secure=app.config["COOKIE_SECURE"], httponly=True, samesite="Lax", path="/")
        return response

    @app.put("/api/profile")
    def save_profile():
        try:
            profile = service.validate_birth(
                request.get_json(silent=True), allow_location=app.config["BIRTH_LOCATION_ENABLED"],
            )
        except service.InvalidProfile as exc:
            return error("invalid_profile", str(exc), 400)
        if not app.config["BIRTH_LOCATION_ENABLED"] and g.record["profile"]:
            # Hidden fields cannot be edited while collection is disabled. Keep
            # earlier values until the owner explicitly deletes their profile.
            profile.update({key: value for key, value in g.record["profile"].items()
                            if key in service.LOCATION_FIELDS})
        if not store.save(g.token, profile):
            return error("session_expired", "이용 세션이 만료됐습니다. 화면을 새로고침해 주세요.", 401)
        measure(g.token, "profile_saved", "entry")
        return jsonify(ok=True, profile=profile, reading_window=service.reading_window(profile, app.config["NOW"]))

    @app.post("/api/events")
    def event():
        try:
            name, view = metrics.parse_event(request.get_json(silent=True))
        except ValueError:
            return error("invalid_event", "허용된 이용 단계만 기록할 수 있습니다.", 400)
        if view == "integrated" and not app.config["INTEGRATED_ENABLED"]:
            return error("invalid_event", "허용된 이용 단계만 기록할 수 있습니다.", 400)
        if name in metrics.PRODUCT_SAMPLE_EVENTS:
            # These new actions require an explicit same-origin browser request.
            expected_origin = public_origin or request.host_url.rstrip("/")
            if request.headers.get("Origin", "").rstrip("/") != expected_origin:
                return error("origin_invalid", "요청한 화면의 주소를 확인해 주세요.", 403)
            try:
                result = store.record_sample_event(g.token, metrics.metric_day(app.config["NOW"]), name, view)
            except Exception:
                app.logger.warning("fortune-web: sample measurement unavailable")
                return error("interest_unavailable", "관심을 기록하지 못했습니다. 잠시 후 다시 눌러 주세요.", 503)
            if result == "session_expired":
                return error("session_expired", "이용 세션이 만료됐습니다. 화면을 새로고침해 주세요.", 401)
            if result == "sample_not_viewed":
                return error("sample_not_viewed", "샘플을 먼저 읽은 뒤 관심을 표시해 주세요.", 409)
            if result not in {"inserted", "duplicate"}:
                return error("interest_unavailable", "관심을 기록하지 못했습니다. 잠시 후 다시 눌러 주세요.", 503)
            return jsonify(ok=True), 202
        if name not in {"form_started", "shared_link_visit"} and not g.record["profile"]:
            return error("profile_required", "출생정보를 먼저 등록해 주세요.", 409)
        if name == "premium_interest":
            # This explicit user action needs an honest acknowledgement. Other
            # funnel events remain best-effort so metrics cannot break readings.
            try:
                inserted = store.record_event(g.token, metrics.metric_day(app.config["NOW"]), name, view)
                if not inserted and store.find(g.token) is None:
                    return error("session_expired", "이용 세션이 만료됐습니다. 화면을 새로고침해 주세요.", 401)
            except Exception:
                app.logger.warning("fortune-web: interest measurement unavailable")
                return error("interest_unavailable", "관심을 기록하지 못했습니다. 잠시 후 다시 눌러 주세요.", 503)
        else:
            measure(g.token, name, view)
        return jsonify(ok=True), 202

    @app.delete("/api/profile")
    def delete_profile():
        store.delete(g.token)
        response = jsonify(ok=True, text="출생정보와 이 브라우저의 이용 기록을 삭제했습니다.")
        response.delete_cookie(app.config["COOKIE_NAME"], path="/", secure=app.config["COOKIE_SECURE"], httponly=True, samesite="Lax")
        return response

    @app.get("/api/readings/integrated")
    @require_integrated
    @require_profile
    def integrated_reading():
        result = service.integrated(g.record["profile"])
        return jsonify(result), 200 if result["computed"] else 503

    @app.get("/api/readings/<day>")
    @require_profile
    def reading(day):
        if day not in ("today", "tomorrow", "week"):
            return error("invalid_period", "계산 결과가 아님\n풀이 날짜를 다시 선택해 주세요.", 400)
        return jsonify(service.daily(g.record["profile"], day, app.config["NOW"]))

    @app.get("/api/chart")
    @require_profile
    def chart():
        return jsonify(service.chart(g.record["profile"]))

    @app.get("/api/kline")
    @require_profile
    def kline():
        return jsonify(service.kline(g.record["profile"], app.config["NOW"]))

    @app.post("/api/readings/date")
    @require_profile
    def dated_reading():
        try:
            result = service.dated_reading(g.record["profile"], request.get_json(silent=True), app.config["NOW"])
        except service.InvalidProfile as exc:
            return error("invalid_date", str(exc), 400)
        return jsonify(result), 200 if result["ok"] else 503

    @app.post("/api/compat")
    @require_profile
    def compatibility():
        try:
            result = service.compatibility(g.record["profile"], request.get_json(silent=True))
        except service.InvalidProfile as exc:
            return error("invalid_partner", str(exc), 400)
        return jsonify(result), 200 if result["ok"] else 503

    return app
