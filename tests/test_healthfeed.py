import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

import healthfeed


class HealthFeedTests(unittest.TestCase):
    def sample(self, when, statuses):
        return {
            "generated_at_utc": when,
            "sources": [
                {
                    "source_id": "SRC-WEB-" + code,
                    "state_code": code,
                    "official_url": "https://example.org/" + code,
                    "status": status,
                    "last_error": "HTTP 403" if status == "FAILED" else None,
                    "consecutive_failures": 2 if status == "FAILED" else 0,
                }
                for code, status in statuses.items()
            ],
        }

    def test_deduplicates_persistent_failure_and_records_recovery_and_relapse(self):
        a = self.sample("2026-10-30T12:00:00+00:00", {"AK": "FAILED", "KY": "UNCHANGED"})
        state, events = healthfeed.record_events(a, {}, [])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["kind"], "failure")
        state, events = healthfeed.record_events(a, state, events)
        self.assertEqual(len(events), 1)
        b = self.sample("2026-10-31T12:00:00+00:00", {"AK": "UNCHANGED", "KY": "UNCHANGED"})
        state, events = healthfeed.record_events(b, state, events)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["kind"], "restored")
        c = self.sample("2026-11-01T12:00:00+00:00", {"AK": "FAILED", "KY": "UNCHANGED"})
        state, events = healthfeed.record_events(c, state, events)
        self.assertEqual(len(events), 3)
        self.assertEqual(len({e["id"] for e in events}), 3)

    def test_publishes_parseable_rss_and_unique_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "public").mkdir()
            data = self.sample("2026-10-30T12:00:00+00:00", {"AK": "FAILED", "DE": "FAILED"})
            (root / "public" / "health.json").write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(healthfeed.publish(root, "https://example.github.io/feed"), 2)
            channel = ET.parse(root / "public" / "health-alerts.xml")
            items = channel.findall(".//item")
            self.assertEqual(len(items), 2)
            self.assertNotEqual(items[0].findtext("link"), items[1].findtext("link"))
            self.assertIn("[Monitor failure]", items[0].findtext("title"))
            self.assertTrue((root / "state" / "health-status.json").is_file())
            self.assertEqual(healthfeed.publish(root, "https://example.github.io/feed"), 2)
            self.assertEqual(len(ET.parse(root / "public" / "health-alerts.xml").findall(".//item")), 2)


if __name__ == "__main__":
    unittest.main()
