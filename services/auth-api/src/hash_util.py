"""Utility to pre-hash passwords in a users.json file for production use.

Usage:
    python src/hash_util.py users.json users-hashed.json
"""

import hashlib
import json
import os
import sys


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
    return salt.hex() + ":" + key.hex()


def main():
    if len(sys.argv) < 2:
        print("Usage: python src/hash_util.py <input.json> [output.json]")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as fh:
        data = json.load(fh)

    for user in data.get("users", []):
        if "password" in user and "password_hash" not in user:
            user["password_hash"] = hash_password(user.pop("password"))

    output = sys.argv[2] if len(sys.argv) > 2 else sys.argv[1]
    with open(output, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    print(f"Hashed {len(data.get('users', []))} user(s) -> {output}")


if __name__ == "__main__":
    main()
