import unittest

from main import calculate_risk, concrete_index_name, parse_packet, parse_packet_with_meta


class BrainTests(unittest.TestCase):
    def test_calculate_risk_levels(self):
        score, label = calculate_risk("password admin", [{"text": "Alice", "type": "PERSON"}])
        self.assertGreaterEqual(score, 25)
        self.assertIn(label, ["HIGH", "CRITICAL"])

    def test_parse_packet_fallback(self):
        raw = "plain text"
        self.assertEqual(parse_packet(raw), raw)

    def test_parse_packet_json(self):
        payload = '{"text": "clean content"}'
        self.assertEqual(parse_packet(payload), "clean content")

    def test_parse_packet_with_meta(self):
        payload = '{"text": "clean content", "traceparent": "00-abc-def-01", "source_url": "https://example.com"}'
        parsed = parse_packet_with_meta(payload)
        self.assertEqual(parsed["text"], "clean content")
        self.assertEqual(parsed["traceparent"], "00-abc-def-01")
        self.assertEqual(parsed["source_url"], "https://example.com")
        self.assertFalse(parsed["fallback"])

    def test_concrete_index_name(self):
        self.assertEqual(concrete_index_name("intel-data-v3", "v4"), "intel-data-v3-v4")


if __name__ == "__main__":
    unittest.main()
