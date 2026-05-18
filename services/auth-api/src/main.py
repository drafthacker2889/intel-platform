"""JWT-based authentication and RBAC service.

Endpoints:
  POST /login   - Authenticate and receive a JWT token
  POST /logout  - Blacklist the caller's token
  GET  /verify  - Validate token and check role (used by nginx auth_request)
  GET  /health  - Service health
  POST /users   - Create a new user (admin only)
  GET  /users   - List users (admin only)
"""

import hashlib
import hmac
import json
import logging
import os
import re
import signal
import socketserver
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import jwt

# ── Structured JSON logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":%(message)s}',
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("auth-api")

# ── Configuration ──────────────────────────────────────────────────────────────
_raw_secret = os.getenv("AUTH_SECRET_KEY", "")
_INSECURE_DEFAULT = "change-me-in-production"

if not _raw_secret or _raw_secret == _INSECURE_DEFAULT:
    raise RuntimeError(
        "AUTH_SECRET_KEY is not set or uses the insecure default. "
        "Set a random secret of at least 32 characters before starting the service."
    )
if len(_raw_secret) < 32:
    raise RuntimeError(
        f"AUTH_SECRET_KEY is only {len(_raw_secret)} characters. "
        "Minimum required is 32 characters for HS256."
    )

SECRET_KEY         = _raw_secret
TOKEN_EXPIRY_HOURS = int(os.getenv("AUTH_TOKEN_EXPIRY_HOURS", "4"))
PORT               = int(os.getenv("AUTH_PORT", "8084"))
USERS_FILE         = os.getenv("USERS_FILE", "/app/users.json")

ROLE_HIERARCHY: dict[str, int] = {"viewer": 1, "analyst": 2, "admin": 3}

MAX_BODY_SIZE      = 10_000   # bytes — hard cap on request bodies
RATE_LIMIT_WINDOW  = 300      # seconds per rate-limit bucket
RATE_LIMIT_MAX     = 5        # max login attempts per IP per window

# ── Mutable shared state (all guarded by locks) ────────────────────────────────
USERS: dict            = {}
_users_lock            = threading.Lock()

_token_blacklist: set  = set()  # stores blacklisted JTIs
_blacklist_lock        = threading.Lock()

_rate_counters: dict   = {}     # ip → (count, window_start)
_rate_lock             = threading.Lock()

# ── Password strength ──────────────────────────────────────────────────────────
_PASSWORD_RE = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^a-zA-Z\d]).{12,}$"
)

def _password_strong(password: str) -> bool:
    return bool(_PASSWORD_RE.match(password))


# ── Password helpers ───────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key  = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + ":" + key.hex()


def verify_password(stored: str, password: str) -> bool:
    try:
        salt_hex, key_hex = stored.split(":")
        salt     = bytes.fromhex(salt_hex)
        computed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
        return hmac.compare_digest(computed.hex(), key_hex)
    except (ValueError, AttributeError):
        return False


# ── User loading ───────────────────────────────────────────────────────────────
def load_users() -> None:
    if not os.path.exists(USERS_FILE):
        admin_user = os.getenv("AUTH_ADMIN_USER", "admin")
        admin_pass = os.getenv("AUTH_ADMIN_PASSWORD", "")
        if not admin_pass:
            raise RuntimeError(
                "No USERS_FILE found and AUTH_ADMIN_PASSWORD is not set. "
                "Cannot create a default admin user without a password."
            )
        USERS[admin_user] = {"password_hash": hash_password(admin_pass), "role": "admin"}
        logger.info('"Created default admin user %s from environment"', admin_user)
        return

    with open(USERS_FILE, encoding="utf-8") as fh:
        data = json.load(fh)

    for entry in data.get("users", []):
        username = entry["username"]
        role     = entry.get("role", "viewer")
        if "password_hash" in entry:
            USERS[username] = {"password_hash": entry["password_hash"], "role": role}
        elif "password" in entry:
            USERS[username] = {"password_hash": hash_password(entry["password"]), "role": role}


# ── JWT helpers ────────────────────────────────────────────────────────────────
def create_token(username: str, role: str) -> str:
    now = int(time.time())
    payload = {
        "sub":  username,
        "role": role,
        "iat":  now,
        "exp":  now + TOKEN_EXPIRY_HOURS * 3600,
        "jti":  str(uuid.uuid4()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        claims = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
    jti = claims.get("jti")
    if jti:
        with _blacklist_lock:
            if jti in _token_blacklist:
                return None
    return claims


def blacklist_token(token: str) -> bool:
    claims = decode_token(token)
    if not claims:
        return False
    jti = claims.get("jti")
    if jti:
        with _blacklist_lock:
            _token_blacklist.add(jti)
    return True


def role_sufficient(user_role: str, required_role: str) -> bool:
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(required_role, 999)


# ── Rate limiting ──────────────────────────────────────────────────────────────
def _check_rate_limit(ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        entry = _rate_counters.get(ip)
        if entry is None or now - entry[1] > RATE_LIMIT_WINDOW:
            _rate_counters[ip] = (1, now)
            return True
        count, window_start = entry
        if count >= RATE_LIMIT_MAX:
            return False
        _rate_counters[ip] = (count + 1, window_start)
        return True


# ── Threading HTTP server (one thread per connection) ─────────────────────────
class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True


# ── Request handler ────────────────────────────────────────────────────────────
class AuthHandler(BaseHTTPRequestHandler):

    def log_message(self, *_):
        if self.path != "/health":
            logger.info('"HTTP %s %s"', self.command, self.path)

    # --- POST ---
    def do_POST(self):
        if self.path == "/login":
            return self._handle_login()
        if self.path == "/logout":
            return self._handle_logout()
        if self.path == "/users":
            return self._handle_create_user()
        self._send(404, {"error": "not found"})

    def _handle_login(self):
        ip = self.client_address[0]
        if not _check_rate_limit(ip):
            logger.warning('"Rate limit exceeded for IP %s"', ip)
            return self._send(429, {"error": "too many login attempts, try again later"})
        body = self._read_body()
        if body is None:
            return
        username = body.get("username", "")
        password = body.get("password", "")
        with _users_lock:
            user = USERS.get(username)
        if not user or not verify_password(user["password_hash"], password):
            logger.warning('"Failed login attempt for user %s from %s"', username, ip)
            return self._send(401, {"error": "invalid credentials"})
        token = create_token(username, user["role"])
        logger.info('"Successful login for user %s (role=%s)"', username, user["role"])
        self._send(200, {"token": token, "role": user["role"]})

    def _handle_logout(self):
        token = self._extract_token()
        if not token:
            return self._send(401, {"error": "token required"})
        if blacklist_token(token):
            logger.info('"Token blacklisted on logout"')
            self._send(200, {"status": "logged out"})
        else:
            self._send(401, {"error": "invalid or expired token"})

    def _handle_create_user(self):
        claims = self._require_role("admin")
        if claims is None:
            return
        body = self._read_body()
        if body is None:
            return
        username = body.get("username", "")
        password = body.get("password", "")
        role     = body.get("role", "viewer")
        if not username or not password:
            return self._send(400, {"error": "username and password required"})
        if not _password_strong(password):
            return self._send(400, {
                "error": (
                    "password must be at least 12 characters and contain uppercase, "
                    "lowercase, a digit, and a special character"
                )
            })
        if role not in ROLE_HIERARCHY:
            return self._send(400, {"error": f"role must be one of {list(ROLE_HIERARCHY)}"})
        with _users_lock:
            if username in USERS:
                return self._send(409, {"error": "user already exists"})
            USERS[username] = {"password_hash": hash_password(password), "role": role}
        logger.info('"Created user %s with role %s by admin %s"', username, role, claims["sub"])
        self._send(201, {"username": username, "role": role})

    # --- GET ---
    def do_GET(self):
        if self.path == "/health":
            with _users_lock:
                user_count = len(USERS)
            return self._send(200, {"status": "ok", "users": user_count})
        if self.path.startswith("/verify"):
            return self._handle_verify()
        if self.path == "/users":
            return self._handle_list_users()
        self._send(404, {"error": "not found"})

    def _handle_verify(self):
        token = self._extract_token()
        if not token:
            self.send_response(401)
            self.end_headers()
            return
        claims = decode_token(token)
        if not claims:
            self.send_response(401)
            self.end_headers()
            return
        required_role = self.headers.get("X-Required-Role", "viewer")
        if required_role not in ROLE_HIERARCHY:
            self.send_response(400)
            self.end_headers()
            return
        if not role_sufficient(claims.get("role", ""), required_role):
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("X-Auth-User", claims["sub"])
        self.send_header("X-Auth-Role", claims["role"])
        self.end_headers()

    def _handle_list_users(self):
        claims = self._require_role("admin")
        if claims is None:
            return
        with _users_lock:
            users = [{"username": u, "role": d["role"]} for u, d in USERS.items()]
        self._send(200, {"users": users})

    # --- helpers ---
    def _extract_token(self) -> str | None:
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        return None

    def _require_role(self, role: str) -> dict | None:
        token = self._extract_token()
        if not token:
            self._send(401, {"error": "token required"})
            return None
        claims = decode_token(token)
        if not claims:
            self._send(401, {"error": "invalid token"})
            return None
        if not role_sufficient(claims.get("role", ""), role):
            self._send(403, {"error": "insufficient permissions"})
            return None
        return claims

    def _read_body(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._send(400, {"error": "invalid Content-Length"})
            return None
        if length > MAX_BODY_SIZE:
            self._send(413, {"error": "request body too large"})
            return None
        try:
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        except UnicodeDecodeError:
            self._send(400, {"error": "request body must be UTF-8"})
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid JSON"})
            return None

    def _send(self, status: int, data: dict) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


# ── Entry point ────────────────────────────────────────────────────────────────
def main() -> None:
    load_users()
    logger.info('"Auth API starting on port %d with %d user(s)"', PORT, len(USERS))

    server = ThreadingHTTPServer(("0.0.0.0", PORT), AuthHandler)

    def _shutdown(*_):
        logger.info('"Shutdown signal received, stopping auth-api"')
        server.shutdown()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT,  _shutdown)

    server.serve_forever()
    logger.info('"Auth API stopped"')


if __name__ == "__main__":
    main()
