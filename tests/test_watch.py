import csv
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
import watch

class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = (watch.STORE, watch.OUT)
        watch.STORE = Path(self.tmp.name) / "state"
        watch.OUT = Path(self.tmp.name) / "public"
        self.source = {"SourceID": "SRC-WEB-KY", "StateCode": "KY", "SourceURL": "https://pharmacy.ky.gov/test"}
        self.now = dt.datetime(2026, 10, 30, tzinfo=dt.timezone.utc)
    def tearDown(self):
        watch.STORE, watch.OUT = self.old
        self.tmp.cleanup()
    def test_baseline_revision_and_idempotency(self):
        a = "Existing Kentucky board pharmacy rulemaking information. " * 4
        b = "New Kentucky board pharmacy rulemaking information. " * 4
        self.assertEqual(watch.check(self.source, lambda _: a, self.now)["status"], "BASELINED")
        self.assertEqual(watch.check(self.source, lambda _: a, self.now)["status"], "UNCHANGED")
        self.assertEqual(watch.check(self.source, lambda _: b, self.now)["status"], "POTENTIAL_CHANGE")
        self.assertEqual(watch.check(self.source, lambda _: b, self.now)["status"], "UNCHANGED")
        events = json.loads((watch.STORE / "events" / "SRC-WEB-KY.json").read_text())
        self.assertEqual(len(events), 1)
        parsed = ET.parse(watch.OUT / "feeds" / "SRC-WEB-KY.xml")
        self.assertEqual(len(parsed.findall(".//item")), 1)
    def test_failure_preserves_last_baseline(self):
        original = "Public pharmacy board notice and formal rule changes. " * 4
        watch.check(self.source, lambda _: original, self.now)
        def blocked(_): raise ConnectionError("HTTP 403")
        failed = watch.check(self.source, blocked, self.now)
        self.assertEqual(failed["status"], "FAILED")
        self.assertEqual(failed["last_sha256"], watch.digest(original))
        self.assertEqual(failed["consecutive_failures"], 1)
    def test_south_dakota_clock_noise_ignored_and_real_changes_detected(self):
        self.source = {"SourceID": "SRC-WEB-SD", "StateCode": "SD", "SourceURL": "https://rules.sd.gov/"}
        base = "Notices of administrative rulemaking and pharmacy regulations. " * 3
        initial = "as of\\n10-29-2026 23:35:40 PM\\n" + base
        later = "as of\\n10-29-2026 23:41:08 PM\\n" + base
        self.assertEqual(watch.check(self.source, lambda _: initial, self.now)["status"], "BASELINED")
        self.assertEqual(watch.check(self.source, lambda _: later, self.now)["status"], "UNCHANGED")
        real_change = later + " New pharmacy hearing and proposed regulations."
        self.assertEqual(watch.check(self.source, lambda _: real_change, self.now)["status"], "POTENTIAL_CHANGE")
        self.assertEqual(len(json.loads((watch.STORE / "events" / "SRC-WEB-SD.json").read_text())), 1)
        recorded_clock_only = "--- previous\\n+++ current\\n@@ -42,7 +42,7 @@\\n-10-29-2026 23:35:40 PM\\n+10-29-2026 23:41:08 PM\\n"
        self.assertTrue(watch.sd_clock_only_event(recorded_clock_only))
    def test_51_unique_source_ids(self):
        with watch.SOURCES.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 51)
        self.assertEqual(len({r["SourceID"] for r in rows}), 51)
        self.assertEqual(len({r["StateCode"] for r in rows}), 51)
