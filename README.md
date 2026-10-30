# UKSP Public Source Monitor

Development prototype: daily, automated public-source change checks. Not a verified regulatory compliance service.

- `watch.py` checks one public URL in each of 51 jurisdictions and compares text hashes.
- `data/sources.csv` identifies candidate URLs, including three replacement sources under re-test.
- `public/health.json` records the outcome of every check. A green workflow means the job completed, not that all sources were accessible.
- `public/feeds/SRC-WEB-KY.xml` illustrates the per-jurisdiction RSS feed path. A successful initial baseline produces an empty feed.
- Source changes are unverified signals; legal changes require review of the official publication.

This repository is personal and for development only. Long-term UKSP deployment requires institutional authorization, organization ownership, monitoring QA, and tested integration into the existing SharePoint and Power Apps system. Do not upload internal UKSP information or patient records.

## Setup

In repository Settings > Pages, select GitHub Actions. In Actions > UKSP Public Source Monitoring, run the workflow manually for an initial baseline or source re-test. Inspect the `Check 51 public source candidates` step, then the published `public/health.json` file for failures.
