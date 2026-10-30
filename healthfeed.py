#!/usr/bin/env python3
"""Publish operational monitoring failures separately from regulatory-source changes.

These are retrieval status alerts only, never findings that pharmacy law changed.
"""
import datetime as dt
import hashlib
import html
import json
import os
from email.utils import format_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
BASE_URL = os.environ.get(
    "UKSP_FEED_BASE", "https://kathrynbowman.github.io/uksp-public-source-monitor"
).rstrip("/")


def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def record_events(health, current_state, old_events):
    """Create one failure notice per incident and one restoration notice on recovery.

    Re-running the same status does not create another alert; a later relapse does.
    """
    state = dict(current_state)
    events = list(old_events)
    when = health["generated_at_utc"]
    for source in health["sources"]:
        sid = source["source_id"]
        failed = source["status"] == "FAILED"
        previous = state.get(sid, {}).get("failed", False)
        if failed != previous:
            kind = "failure" if failed else "restored"
            key = hashlib.sha256((sid + "|" + kind + "|" + when).encode("utf-8")).hexdigest()[:24]
            error = source.get("last_error") or ""
            events.insert(0, {
                "id": key,
                "kind": kind,
                "state_code": source["state_code"],
                "source_id": sid,
                "source_url": source["official_url"],
                "observed_at": when,
                "error": error[:350] if failed else "",
                "consecutive_failures": source.get("consecutive_failures", 0) if failed else 0,
            })
        state[sid] = {"failed": failed}
    return state, events[:200]


def publish(root=ROOT, base_url=BASE_URL):
    public = root / "public"
    state = root / "state"
    health = load(public / "health.json", None)
    if not health or not isinstance(health.get("sources"), list):
        raise ValueError("Missing valid public/health.json; run watch.py first.")
    ledger = state / "health-status.json"
    history = state / "health-events.json"
    latest, events = record_events(health, load(ledger, {}), load(history, []))
    save(ledger, latest)
    save(history, events)

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    for key, value in [
        ("title", "UKSP public-source monitor operational incidents"),
        ("link", base_url + "/health.json"),
        ("description", "Failed or restored public webpage retrieval; NOT a legal or regulatory change."),
        ("language", "en-us"),
    ]:
        ET.SubElement(channel, key).text = value

    for event in events:
        sid, code, kind = event["source_id"], event["state_code"], event["kind"]
        link = base_url + "/monitor-events/" + event["id"] + ".html"
        title = ("[Monitor failure] " if kind == "failure" else "[Monitor restored] ") + code + " | " + sid
        description = (
            ("Source retrieval failed: " + event["error"]) if kind == "failure"
            else "Public source retrieval has recovered."
        ) + " Official source: " + event["source_url"]
        node = ET.SubElement(channel, "item")
        for key, value in [
            ("title", title),
            ("link", link),
            ("guid", "uksp-operational-" + event["id"]),
            ("description", description),
            ("pubDate", format_datetime(dt.datetime.fromisoformat(event["observed_at"]), usegmt=True)),
        ]:
            child = ET.SubElement(node, key)
            child.text = value
            if key == "guid":
                child.set("isPermaLink", "false")
        file = public / "monitor-events" / (event["id"] + ".html")
        if not file.is_file():
            file.parent.mkdir(parents=True, exist_ok=True)
            esc = html.escape
            file.write_text(
                "<!doctype html><html lang='en'><meta charset='utf-8'>"
                "<title>UKSP monitoring incident</title>"
                "<body style='font:16px system-ui;max-width:850px;margin:3em auto'>"
                "<h1>" + esc(title) + "</h1>"
                "<p><b>Operational retrieval alert only. This does not indicate a change to law.</b></p>"
                "<p>Observed UTC: " + esc(event["observed_at"]) + "</p>"
                "<p>Official page: <a href='" + esc(event["source_url"], quote=True)
                + "'>" + esc(event["source_url"]) + "</a></p>"
                "<p>" + esc(description) + "</p></body></html>",
                encoding="utf-8",
            )

    target = public / "health-alerts.xml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(ET.tostring(rss, encoding="utf-8", xml_declaration=True))
    return len(events)


if __name__ == "__main__":
    print("Published operational monitor RSS with", publish(), "total incident records")
