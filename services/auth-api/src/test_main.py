import os
import time
import unittest

os.environ["AUTH_SECRET_KEY"] = "a-very-long-secret-key-for-unit-testing-purposes-only"

from main import (
    _password_strong,
    blacklist_token,
    create_token,
    decode_token,
    hash_password,
    role_sufficient,
    verify_password,
)


class PasswordTests(unittest.TestCase):
    def test_hash_and_verify_roundtrip(self):
        hashed = hash_password("MyP@ssw0rd!")
        self.assertTrue(verify_password(hashed, "MyP@ssw0rd!"))
        self.assertFalse(verify_password(hashed, "wrongpassword"))

    def test_different_salts(self):
        h1 = hash_password("SamePass1!")
        h2 = hash_password("SamePass1!")
        self.assertNotEqual(h1, h2)

    def test_verify_malformed_hash(self):
        self.assertFalse(verify_password("notahash", "anything"))


class PasswordStrengthTests(unittest.TestCase):
    def test_strong_password(self):
        self.assertTrue(_password_strong("Secure@Pass1!"))

    def test_too_short(self):
        self.assertFalse(_password_strong("Short1!"))

    def test_no_uppercase(self):
        self.assertFalse(_password_strong("alllowercase1!ab"))

    def test_no_digit(self):
        self.assertFalse(_password_strong("NoDigitsHere!!a"))

    def test_no_special(self):
        self.assertFalse(_password_strong("NoSpecial12345A"))


class TokenTests(unittest.TestCase):
    def test_create_and_decode(self):
        token = create_token("alice", "analyst")
        claims = decode_token(token)
        self.assertIsNotNone(claims)
        self.assertEqual(claims["sub"], "alice")
        self.assertEqual(claims["role"], "analyst")
        self.assertIn("jti", claims)

    def test_decode_invalid_token(self):
        self.assertIsNone(decode_token("not.a.token"))

    def test_blacklist_token(self):
        token = create_token("bob", "viewer")
        self.assertIsNotNone(decode_token(token))
        self.assertTrue(blacklist_token(token))
        self.assertIsNone(decode_token(token))

    def test_blacklist_already_invalid(self):
        self.assertFalse(blacklist_token("not.a.real.token"))


class RoleTests(unittest.TestCase):
    def test_admin_sufficient_for_viewer(self):
        self.assertTrue(role_sufficient("admin", "viewer"))

    def test_viewer_insufficient_for_admin(self):
        self.assertFalse(role_sufficient("viewer", "admin"))

    def test_analyst_sufficient_for_analyst(self):
        self.assertTrue(role_sufficient("analyst", "analyst"))

    def test_unknown_role_insufficient(self):
        self.assertFalse(role_sufficient("unknown", "viewer"))


if __name__ == "__main__":
    unittest.main()
