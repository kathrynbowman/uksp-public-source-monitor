#!/usr/bin/env python3
"""UKSP public regulatory webpage monitor. All alerts are UNVERIFIED signals."""
import csv
import datetime as dt
import difflib
import hashlib
import html
import io
import json
import os
import re
import time
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

BASE = Path(__file__).resolve().parent
SOURCES = BASE / "data" / "sources.csv"
STORE = BASE / "state"
OUT = BASE / "public"
BASE_URL = os.environ.get("UKSP_FEED_BASE", "https://example.github.io/uksp-public-source-monitor").rstrip("/")
HEADERS = {"User-Agent": "UKSP-public-source-monitor/0.1 (public regulatory publications)"}
NOW = lambda: dt.datetime.now(dt.timezone.utc)
def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
def read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default
def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
def iso(now):
    return now.isoformat(timespec="seconds")
def safe_url(url):
    p = urlsplit(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password:
        raise ValueError("Source is not a public HTTPS URL")
    h = p.hostname.lower()
    if h in ("localhost", "127.0.0.1", "169.254.169.254") or h.endswith((".local", ".internal")):
        raise ValueError("Private endpoint blocked")
def page_text(data, content_type):
    if data.startswith(b"%PDF") or "application/pdf" in content_type:
        pdf = PdfReader(io.BytesIO(data))
        if len(pdf.pages) > 250:
            raise ValueError("PDF exceeds page limit")
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    else:
        soup = BeautifulSoup(data, "html.parser")
        part = soup.select_one("main") or soup.select_one("article") or soup.body or soup
        for el in part.select("script,style,footer,nav,header,iframe,noscript,svg,form"):
            el.decompose()
        text = "\n".join(part.stripped_strings)
    text = "\n".join(re.sub(r"\s+", " ", line).strip() for line in text.splitlines())
    if len(text.strip()) < 80:
        raise ValueError("Too little usable text to form a trustworthy baseline")
    return text[:300000]
def retrieve(url):
    safe_url(url)
    with requests.get(url, headers=HEADERS, timeout=(8, 20), stream=True, allow_redirects=True) as res:
        safe_url(res.url)
        res.raise_for_status()
        data = bytearray()
        for part in res.iter_content(65536):
            data.extend(part)
            if len(data) > 12_000_000:
                raise ValueError("Source download too large")
        if not data:
            raise ValueError("Empty response")
        return page_text(bytes(data), res.headers.get("content-type", ""))
def feed_xml(src, events):
    root = ET.Element("rss", version="2.0")
    ch = ET.SubElement(root, "channel")
    for tag, val in [
        ("title", "UKSP unverified source changes | " + src["StateCode"]),
        ("link", src["SourceURL"]),
        ("description", "Unverified webpage revisions only; never legal determinations"),
        ("language", "en-us"),
    ]:
        ET.SubElement(ch, tag).text = val
    for e in events[:30]:
        item = ET.SubElement(ch, "item")
        link = f"{BASE_URL}/evidence/{src['SourceID']}/{e['id']}.html"
        for tag, val in [
            ("title", "[Potential source change] " + src["StateCode"] + " | " + src["SourceID"]),
            ("link", link),
            ("guid", "uksp-" + src["SourceID"] + "-" + e["id"]),
            ("description", e["summary"]),
            ("pubDate", format_datetime(dt.datetime.fromisoformat(e["observed_at"]), usegmt=True)),
        ]:
            node = ET.SubElement(item, tag)
            node.text = val
            if tag == "guid":
                node.set("isPermaLink", "false")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
def evidence_html(src, e):
    esc = html.escape
    return ("<!doctype html><html lang='en'><meta charset='utf-8'><meta name='robots' content='noindex'>"
            "<title>Unverified source revision</title><body style='font:16px system-ui;max-width:950px;margin:4em auto'>"
            "<h1>Unverified source revision — " + esc(src["StateCode"]) + "</h1>"
            "<p><b>Do not treat as a verified law or regulation change.</b></p>"
            "<p>Official source: <a href='" + esc(src["SourceURL"], quote=True) + "'>" + esc(src["SourceURL"]) + "</a></p>"
            "<p>Observed UTC: " + esc(e["observed_at"]) + "</p>"
            "<p>Previous SHA256: " + esc(e["previous_sha256"]) + "<br>Current SHA256: " + esc(e["current_sha256"]) + "</p>"
            "<pre style='white-space:pre-wrap;overflow-wrap:anywhere'>" + esc(e["diff"]) + "</pre></body></html>")
def check(src, fetch=retrieve, now=None):
    now = now or NOW()
    sid = src["SourceID"]
    status_file = STORE / "sources" / (sid + ".json")
    snapshot_file = STORE / "snapshots" / (sid + ".txt")
    event_file = STORE / "events" / (sid + ".json")
    status = read_json(status_file, {})
    old_hash = status.get("last_sha256")
    events = read_json(event_file, [])
    status.update({"source_id":sid, "state_code":src["StateCode"], "official_url":src["SourceURL"], "last_checked_utc":iso(now)})
    try:
        text = fetch(src["SourceURL"])
        new_hash = digest(text)
        if old_hash and old_hash != new_hash:
            previous = snapshot_file.read_text(encoding="utf-8") if snapshot_file.exists() else ""
            diff = "\n".join(difflib.unified_diff(previous.splitlines(), text.splitlines(), fromfile="previous", tofile="current", lineterm=""))[:18000]
            event_id = digest(sid + "|" + new_hash)[:24]
            if not any(e["id"] == event_id for e in events):
                e = {
                    "id":event_id, "observed_at":iso(now), "previous_sha256":old_hash,
                    "current_sha256":new_hash, "diff":diff,
                    "summary":"Unverified content difference detected at " + src["SourceURL"] + " on " + iso(now)
                              + ". Compare the official source before assigning legal effect. Difference excerpt: " + diff[:900]
                }
                events.insert(0, e)
                evpath = OUT / "evidence" / sid / (event_id + ".html")
                evpath.parent.mkdir(parents=True, exist_ok=True)
                evpath.write_text(evidence_html(src, e), encoding="utf-8")
            outcome = "POTENTIAL_CHANGE"
        elif old_hash:
            outcome = "UNCHANGED"
        else:
            outcome = "BASELINED"
        snapshot_file.parent.mkdir(parents=True, exist_ok=True)
        snapshot_file.write_text(text, encoding="utf-8")
        status.update({"status":outcome, "last_success_utc":iso(now), "last_sha256":new_hash, "last_error":None, "consecutive_failures":0})
    except Exception as exc:
        outcome = "FAILED"
        status.update({"status":"FAILED", "last_error":str(exc)[:350], "consecutive_failures":int(status.get("consecutive_failures", 0)) + 1})
        # The last successful snapshot and SHA are never overwritten after failures.
    write_json(status_file, status)
    write_json(event_file, events[:30])
    f = OUT / "feeds" / (sid + ".xml")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(feed_xml(src, events))
    return status
def main():
    with SOURCES.open(encoding="utf-8-sig", newline="") as handle:
        sources = list(csv.DictReader(handle))
    if len(sources) != 51 or len({x["StateCode"] for x in sources}) != 51:
        raise RuntimeError("Expected exactly 51 jurisdiction sources")
    results = []
    for i, src in enumerate(sources, 1):
        row = check(src)
        results.append(row)
        print(f"{i}/51 {src['StateCode']} {row['status']}: {row.get('last_error') or ''}", flush=True)
        time.sleep(0.15)
    write_json(OUT / "health.json", {
        "generated_at_utc":iso(NOW()),
        "note":"Public source retrieval health, not comprehensive legal monitoring or verified legal changes.",
        "source_count":len(results), "failed_count":sum(x["status"] == "FAILED" for x in results),
        "sources":results,
    })
    # A source-level failure must not be mislabeled as a change to a law.
    print(f"Checked {len(results)} sources; {sum(x['status'] == 'FAILED' for x in results)} retrieval failures.")
if __name__ == "__main__":
    main()
