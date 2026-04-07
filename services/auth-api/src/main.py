"""JWT-based authentication and RBAC service.

Endpoints:
  POST /login          - Authenticate and receive a JWT token
  GET  /verify         - Validate token and check role (used by nginx auth_request)
  GET  /health         - Service health
  POST /users          - Create a new user (admin only)
  GET  /users          - List users (admin only)
"""

import hashlib
import hmac
import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import jwt

SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "change-me-in-production")
TOKEN_EXPIRY_HOURS = int(os.getenv("AUTH_TOKEN_EXPIRY_HOURS", "24"))
PORT = int(os.getenv("AUTH_PORT", "8084"))
USERS_FILE = os.getenv("USERS_FILE", "/app/users.json")

ROLE_HIERARCHY = {"viewer": 1, "analyst": 2, "admin": 3}
USERS: dict = {}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
    return salt.hex() + ":" + key.hex()


def verify_password(stored: str, password: str) -> bool:
    try:
        salt_hex, key_hex = stored.split(":")
        salt = bytes.fromhex(salt_hex)
        computed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
        return hmac.compare_digest(computed.hex(), key_hex)
    except (ValueError, AttributeError):
        return False


def load_users():
    if not os.path.exists(USERS_FILE):
        admin_user = os.getenv("AUTH_ADMIN_USER", "admin")
        admin_pass = os.getenv("AUTH_ADMIN_PASSWORD", "admin")
        USERS[admin_user] = {"password_hash": hash_password(admin_pass), "role": "admin"}
        print(f"No users file found; created default admin user '{admin_user}'")
        return

    with open(USERS_FILE, encoding="utf-8") as fh:
        data = json.load(fh)

    for entry in data.get("users", []):
        username = entry["username"]
        role = entry.get("role", "viewer")
        if "password_hash" in entry:
            USERS[username] = {"password_hash": entry["password_hash"], "role": role}
        elif "password" in entry:
            USERS[username] = {"password_hash": hash_password(entry["password"]), "role": role}


def create_token(username: str, role: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_EXPIRY_HOURS * 3600,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decode_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def role_sufficient(user_role: str, required_role: str) -> bool:
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(required_role, 999)


class AuthHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        if self.path == "/health":
            return
        super().log_message(fmt, *args)

    # --- POST -----------------------------------------------------------
    def do_POST(self):
        if self.path == "/login":
            return self._handle_login()
        if self.path == "/users":
            return self._handle_create_user()
        self._send(404, {"error": "not found"})

    def _handle_login(self):
        body = self._read_body()
        if body is None:
            return
        username = body.get("username", "")
        password = body.get("password", "")
        user = USERS.get(username)
        if not user or not verify_password(user["password_hash"], password):
            return self._send(401, {"error": "invalid credentials"})
        token = create_token(username, user["role"])
        self._send(200, {"token": token, "role": user["role"]})

    def _handle_create_user(self):
        claims = self._require_role("admin")
        if claims is None:
            return
        body = self._read_body()
        if body is None:
            return
        username = body.get("username", "")
        password = body.get("password", "")
        role = body.get("role", "viewer")
        if not username or not password:
            return self._send(400, {"error": "username and password required"})
        if role not in ROLE_HIERARCHY:
            return self._send(400, {"error": f"role must be one of {list(ROLE_HIERARCHY)}"})
        if username in USERS:
            return self._send(409, {"error": "user already exists"})
        USERS[username] = {"password_hash": hash_password(password), "role": role}
        self._send(201, {"username": username, "role": role})

    # --- GET ------------------------------------------------------------
    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"status": "ok", "users": len(USERS)})
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
        users = [{"username": u, "role": d["role"]} for u, d in USERS.items()]
        self._send(200, {"users": users})

    # --- helpers --------------------------------------------------------
    def _extract_token(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        return None

    def _require_role(self, role):
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

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid JSON"})
            return None

    def _send(self, status, data):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main():
    load_users()
    print(f"Auth API starting on port {PORT} with {len(USERS)} user(s)")
    server = HTTPServer(("0.0.0.0", PORT), AuthHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
