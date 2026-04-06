import hashlib
import hmac
import logging
import time
from collections import OrderedDict

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from config import settings
from engine import process_attendance
from resolver import SlackUserResolver
from sheets import GoogleSheetsClient

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# --- FastAPI app ---
app = FastAPI(
    title="genifem-attendance",
    docs_url=None,   # disable Swagger UI in production
    redoc_url=None,  # disable ReDoc in production
)

# --- Singletons ---
resolver = SlackUserResolver(settings.slack_bot_token)
sheets_client = GoogleSheetsClient(
    settings.google_service_account_json,
    settings.google_sheet_id,
)

# Max payload size (Slack events are typically <10KB)
MAX_BODY_SIZE = 64 * 1024  # 64KB

# --- IP-based rate limiter ---
class RateLimiter:
    """Simple per-IP rate limiter using sliding window."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, list[float]] = {}

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        cutoff = now - self.window
        hits = self._hits.get(ip, [])
        hits = [t for t in hits if t > cutoff]
        if len(hits) >= self.max_requests:
            self._hits[ip] = hits
            return False
        hits.append(now)
        self._hits[ip] = hits
        return True


rate_limiter = RateLimiter(max_requests=60, window_seconds=60)


# --- Event deduplication cache ---
class EventCache:
    """Simple cache with TTL-based expiry for deduplicating Slack events."""

    def __init__(self, ttl: int = 300):
        self._cache: OrderedDict[str, float] = OrderedDict()
        self.ttl = ttl

    def seen(self, event_id: str) -> bool:
        self._evict()
        if event_id in self._cache:
            return True
        self._cache[event_id] = time.time()
        return False

    def _evict(self) -> None:
        now = time.time()
        while self._cache:
            key, ts = next(iter(self._cache.items()))
            if now - ts > self.ttl:
                self._cache.pop(key)
            else:
                break


event_cache = EventCache(ttl=300)


# --- Slack signature verification ---
def verify_slack_signature(headers, body: bytes) -> None:
    """Verify request came from Slack using signing secret."""
    timestamp = headers.get("X-Slack-Request-Timestamp", "")
    signature = headers.get("X-Slack-Signature", "")

    if not timestamp or not signature:
        raise HTTPException(status_code=403, detail="Missing Slack headers")

    try:
        ts_int = int(timestamp)
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid timestamp")

    if abs(time.time() - ts_int) > 300:
        raise HTTPException(status_code=403, detail="Timestamp too old")

    sig_basestring = f"v0:{timestamp}:{body.decode()}"
    my_sig = "v0=" + hmac.new(
        settings.slack_signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(my_sig, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")


# --- Endpoints ---
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/slack/events")
async def slack_events(request: Request, background_tasks: BackgroundTasks):
    # Rate limit by IP
    client_ip = request.headers.get("X-Real-IP", request.client.host)
    if not rate_limiter.is_allowed(client_ip):
        logger.warning("Rate limit exceeded for %s", client_ip)
        raise HTTPException(status_code=429, detail="Too many requests")

    # Reject oversized payloads
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_BODY_SIZE:
        raise HTTPException(status_code=413, detail="Payload too large")

    body = await request.body()
    if len(body) > MAX_BODY_SIZE:
        raise HTTPException(status_code=413, detail="Payload too large")

    # Verify Slack signature (replay attack protection built-in via timestamp)
    verify_slack_signature(request.headers, body)

    payload = await request.json()

    # URL verification challenge
    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    # Event handling
    if payload.get("type") == "event_callback":
        event = payload.get("event", {})
        event_id = payload.get("event_id") or event.get("event_ts", "")

        # Deduplicate
        if event_cache.seen(event_id):
            logger.debug("Duplicate event %s, skipping", event_id)
            return {"ok": True}

        # Channel restriction — only process events from the configured channel
        if settings.slack_channel_id:
            event_channel = event.get("channel", "")
            if event_channel != settings.slack_channel_id:
                logger.debug("Ignoring event from channel %s", event_channel)
                return {"ok": True}

        # Process regular messages and bot messages (for Jibble)
        event_type = event.get("type")
        subtype = event.get("subtype")

        if event_type == "message" and subtype in (None, "bot_message"):
            background_tasks.add_task(
                process_attendance, event, resolver, sheets_client
            )
        elif event_type == "message" and subtype == "message_changed":
            inner = event.get("message", {})
            if inner.get("text"):
                background_tasks.add_task(
                    process_attendance, inner, resolver, sheets_client,
                    is_edit=True,
                )

    return {"ok": True}


# --- Entry point ---
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=False)
