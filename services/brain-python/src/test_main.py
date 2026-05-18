import unittest

from main import calculate_risk, concrete_index_name, parse_packet_with_meta


class BrainTests(unittest.TestCase):
    def test_calculate_risk_critical(self):
        score, label = calculate_risk("password admin secret leaked", [{"text": "Alice", "type": "PERSON"}])
        self.assertGreaterEqual(score, 50)
        self.assertEqual(label, "CRITICAL")

    def test_calculate_risk_high(self):
        score, label = calculate_risk("login admin", [])
        self.assertGreaterEqual(score, 20)
        self.assertIn(label, ["HIGH", "CRITICAL"])

    def test_calculate_risk_low(self):
        score, label = calculate_risk("the quick brown fox", [])
        self.assertEqual(score, 0)
        self.assertEqual(label, "LOW")

    def test_parse_packet_with_meta_json(self):
        payload = '{"text": "clean content", "traceparent": "00-abc-def-01", "source_url": "https://example.com", "collected_at": "2026-01-01T00:00:00Z"}'
        parsed = parse_packet_with_meta(payload)
        self.assertEqual(parsed["text"], "clean content")
        self.assertEqual(parsed["traceparent"], "00-abc-def-01")
        self.assertEqual(parsed["source_url"], "https://example.com")
        self.assertEqual(parsed["collected_at"], "2026-01-01T00:00:00Z")
        self.assertFalse(parsed["fallback"])

    def test_parse_packet_with_meta_fallback(self):
        raw = "plain text not json"
        parsed = parse_packet_with_meta(raw)
        self.assertEqual(parsed["text"], raw)
        self.assertIsNone(parsed["traceparent"])
        self.assertIsNone(parsed["source_url"])
        self.assertTrue(parsed["fallback"])

    def test_parse_packet_with_meta_missing_text(self):
        payload = '{"source_url": "https://example.com"}'
        parsed = parse_packet_with_meta(payload)
        self.assertEqual(parsed["text"], payload)
        self.assertFalse(parsed["fallback"])

    def test_concrete_index_name(self):
        self.assertEqual(concrete_index_name("intel-data-v3", "v4"), "intel-data-v3-v4")


if __name__ == "__main__":
    unittest.main()
