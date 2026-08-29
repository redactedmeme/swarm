"""Unit tests for swarm heartbeat parsing and lookup."""
import json
import time
import unittest

from swarm_core.swarm_heartbeat import (
    build_heartbeat_payload,
    parse_heartbeat_value,
    pick_best_heartbeat,
    HEARTBEAT_LOOKUP_KEYS,
)


class SwarmHeartbeatTests(unittest.TestCase):
    def test_parse_json_with_unix(self):
        now = time.time()
        raw = json.dumps(build_heartbeat_payload("hermes", {"role": "test"}))
        hb = parse_heartbeat_value(raw, now)
        self.assertTrue(hb["present"])
        self.assertTrue(hb["online"])
        self.assertLess(hb["age_s"], 5)

    def test_parse_legacy_float(self):
        now = time.time()
        raw = str(now - 60)
        hb = parse_heartbeat_value(raw, now)
        self.assertTrue(hb["online"])
        self.assertEqual(hb["age_s"], 60)

    def test_parse_stale_json(self):
        now = time.time()
        payload = build_heartbeat_payload("hermes")
        payload["unix"] = now - 400
        hb = parse_heartbeat_value(json.dumps(payload), now)
        self.assertFalse(hb["online"])

    def test_parse_invalid_json_present(self):
        hb = parse_heartbeat_value("{not json", time.time())
        self.assertTrue(hb["present"])
        self.assertFalse(hb["online"])

    def test_pick_best_prefers_online(self):
        now = time.time()
        stale = parse_heartbeat_value(str(now - 400), now)
        fresh = parse_heartbeat_value(json.dumps(build_heartbeat_payload("smolting")), now)
        best = pick_best_heartbeat([stale, fresh])
        self.assertTrue(best["online"])

    def test_smolting_alias_keys(self):
        self.assertIn("redactedintern", HEARTBEAT_LOOKUP_KEYS["smolting"])


if __name__ == "__main__":
    unittest.main()
