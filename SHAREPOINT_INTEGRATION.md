# Connect the consolidated public-source RSS to existing UKSP Power Automate

**Status: NOT CONNECTED.** This is a development procedure, based on the user's exported `UKSP DEV - National RSS Monitor` flow definition. Never claim live SharePoint intake until end-to-end tested.

## Prerequisite

After a successful GitHub workflow execution with the updated `watch.py`, confirm:
`https://kathrynbowman.github.io/uksp-public-source-monitor/all-changes.xml`
contains a valid RSS 2.0 channel. It may have **zero items** if there have been no substantive changes. Do not manufacture regulatory-change alerts to force a test.

## Adapt the existing flow BEFORE activating the national feed

Flow: `UKSP DEV - National RSS Monitor` → Edit → `For_Each_Regulatory_Source` → `For_Each_RSS_Item` → `Is_New_Regulatory_Change` → True → `Create_New_Regulatory_Change`.

Existing action uses `field_2` from the source record for `StateCode`, and `field_1` for `SourceID`. For a national feed, both must be taken from the RSS article title, preserving unchanged behavior for other state-specific feeds.

Replace only **StateCode** with this FX expression:

```text
if(
  equals(items('For_Each_Regulatory_Source')?['field_1'], 'SRC-WEB-NATIONAL'),
  trim(first(split(last(split(coalesce(items('For_Each_RSS_Item')?['title'], ''), '] ')), ' | '))),
  items('For_Each_Regulatory_Source')?['field_2']
)
```

Replace only **SourceID** with this FX expression:

```text
if(
  equals(items('For_Each_Regulatory_Source')?['field_1'], 'SRC-WEB-NATIONAL'),
  trim(last(split(coalesce(items('For_Each_RSS_Item')?['title'], ''), ' | '))),
  items('For_Each_Regulatory_Source')?['field_1']
)
```

Sample title `[Potential source change] SD | SRC-WEB-SD` maps to StateCode=`SD`, SourceID=`SRC-WEB-SD`. If the source row is not `SRC-WEB-NATIONAL`, the old single-state mapping stays in force.

**Keep unchanged:** `SourceItemKey` (from the RSS unique link), `ReviewStatus=New - Unverified`, `LegalDecision=Not Reviewed`, `PublicationStatus=Internal Research Only`, plus original deduplication and exception handling.

RSS `primaryLink` points to a public evidence-difference page. That page links to the official government source. Do not represent this public evidence link as the government's official page.

## Add ONE national source row to the existing SharePoint source registry

Only after the two action fields have been saved and the RSS URL has been verified, create one row in the EXISTING `Regulatory Source Registry - Research`:

- **Title:** `National | GitHub Public Source Change Feed`
- **Source ID** (internal field_1): `SRC-WEB-NATIONAL`
- **State Code** (internal field_2): `US` (only a *routing placeholder*; item-level state is parsed from title)
- **Source category**: `Rulemaking / Register` or existing nearest text option
- **MonitorFeedURL:** `https://kathrynbowman.github.io/uksp-public-source-monitor/all-changes.xml`
- **DetectionMethod** (internal field_12): `Daily RSS — Power Automate` **only when ready to activate**
- **Research status:** unverified/DEV; not Legal approved.

The existing `Filter_RSS_Sources` action already selects source rows where `field_12 = Daily RSS — Power Automate` and `MonitorFeedURL` is nonblank; it excludes only `SRC-OH-REGISTER`. The national source is not excluded.

No 51 individual SharePoint feed records are necessary for this consolidated intake.

## End-to-end proof (when a real change occurs)

Confirm `Get_Source_RSS_Items` sees an item from the national feed; `Check_Existing_Regulatory_Change` returns zero for new IDs; `Create_New_Regulatory_Change` writes StateCode and SourceID from that item's title; `Regulatory Change Register` shows `New - Unverified`; a second run does NOT duplicate the same SourceItemKey; failures go into existing `Regulatory Monitoring Exceptions`.

**Do not count as end-to-end validated until a real or clearly segregated test event is seen in SharePoint.**

## Risks and outstanding work

- All 51 webpages are research candidates; a retrieved page is not necessarily relevant or comprehensive.
- Github currently belongs to a personal account; UK authorization and institution-owned operation are required for a persistent handoff.
- As of the third live run (2026-10-30 04:48 UTC), four public sources were inaccessible/unusable: AK, DE, MO and TN. A later MO replacement has not been checked.
- `public/health.json` shows failures but does **not** currently create automatic SharePoint exception records. That's a separate integration step.
- Existing Visualping monitored pages must not create duplicate alerts; verify scope before activating both.
