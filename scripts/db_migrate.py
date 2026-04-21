#!/usr/bin/env python3
"""
UNS Platform — Database Migration
Rebuilds Locations + Flows from the live UNS simulator model.

Steps:
  1. Get a fresh API token
  2. Delete all existing flows (IDs 1-48)
  3. Delete stale locations (Berlin, Houston, London, Shanghai)
  4. Update Frankfurt to correct coordinates + active status
  5. Create Munich and Ingolstadt
  6. Seed 91 flows from uns_model.py STREAMS list
"""

import sys, os, time, json
import urllib.request, urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from uns_model import STREAMS

# ── Config ────────────────────────────────────────────────────────────────────
API           = "https://api.iotdemozone.com"
SERVICE_KEY   = "636313eb95b09e9a0cc96fb80813aa9bbe01221b596478996c2034fbc56314ba"

# AI classification by source type
CLASSIFICATION = {"PLC": "telemetry", "MES": "status", "ERP": "metric", "SCADA": "telemetry"}
PRIORITY       = {"PLC": "high",      "MES": "normal",  "ERP": "low",    "SCADA": "normal"}

# Interval multipliers for warn/alert thresholds
#   warn  = 3× the publish interval  (missed 3 cycles)
#   alert = 10× the publish interval (missed 10 cycles)
WARN_MULT  = 3
ALERT_MULT = 10

# ── Locations ─────────────────────────────────────────────────────────────────
LOCATIONS_DESIRED = {
    "Frankfurt":  {"lat": "50.1109",  "lon": "8.6821",  "status": 0},  # 0=Healthy
    "Munich":     {"lat": "48.1351",  "lon": "11.5820", "status": 0},
    "Ingolstadt": {"lat": "48.7665",  "lon": "11.4258", "status": 0},
}

# ── HTTP helpers ──────────────────────────────────────────────────────────────
_token = None

def _req(method, path, body=None, *, token=None):
    url  = f"{API}{path}"
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} {method} {path}: {body_text}")

def get_token():
    global _token
    r = _req("POST", "/auth/service-token", {"api_key": SERVICE_KEY})
    _token = r["data"]["token"]
    return _token

def api(method, path, body=None):
    return _req(method, path, body, token=_token)

# ── Progress helpers ──────────────────────────────────────────────────────────
def section(title):
    print(f"\n{'━'*60}")
    print(f"  {title}")
    print(f"{'━'*60}")

def ok(msg):   print(f"  ✓  {msg}")
def info(msg): print(f"  ·  {msg}")
def warn(msg): print(f"  ⚠  {msg}")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Auth
# ══════════════════════════════════════════════════════════════════════════════
section("STEP 1  ·  Authenticate")
get_token()
ok(f"Token acquired (first 40 chars): {_token[:40]}...")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Delete all existing flows
# ══════════════════════════════════════════════════════════════════════════════
section("STEP 2  ·  Delete all existing flows")

existing = api("GET", "/flows?limit=300")
flow_items = existing.get("data", {}).get("items", [])
info(f"Found {len(flow_items)} flows to delete")

deleted = 0
errors  = 0
for flow in flow_items:
    fid = flow["flow_id"]
    try:
        api("DELETE", f"/flows/{fid}")
        deleted += 1
    except RuntimeError as e:
        warn(f"Could not delete flow {fid}: {e}")
        errors += 1

ok(f"Deleted {deleted} flows ({errors} errors)")

# Verify
remaining = api("GET", "/flows?limit=300").get("data", {}).get("items", [])
if remaining:
    warn(f"{len(remaining)} flows still present after delete")
    for r in remaining[:5]:
        info(f"  Remaining: id={r['flow_id']} topic={r['flow_topic']}")
else:
    ok("All flows cleared")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Rebuild locations
# ══════════════════════════════════════════════════════════════════════════════
section("STEP 3  ·  Rebuild locations (Frankfurt / Munich / Ingolstadt)")

current_locs = api("GET", "/locations?limit=50").get("data", {}).get("items", [])
info(f"Current locations in DB: {[(l['location_id'], l['location_name']) for l in current_locs]}")

loc_id_map = {}  # name → id

for loc in current_locs:
    lid  = loc["location_id"]
    name = loc["location_name"]

    if name in LOCATIONS_DESIRED:
        # Update to correct coordinates + status
        d = LOCATIONS_DESIRED[name]
        api("PUT", f"/locations/{lid}", {
            "loc_name":        name,
            "latitude":        d["lat"],
            "longitude":       d["lon"],
            "location_status": d["status"],
            "slo_target":      "99.5",
            "slo_status":      "99.5",
            "error_budget":    "100",
        })
        loc_id_map[name] = lid
        ok(f"Updated  {name} (id={lid})  lat={d['lat']} lon={d['lon']}")
    else:
        # Delete phantom location
        try:
            api("DELETE", f"/locations/{lid}")
            ok(f"Deleted  {name} (id={lid})")
        except RuntimeError as e:
            warn(f"Could not delete {name} (id={lid}): {e}")

# Create any missing desired locations
for name, d in LOCATIONS_DESIRED.items():
    if name not in loc_id_map:
        r = api("POST", "/locations", {
            "loc_name":        name,
            "latitude":        d["lat"],
            "longitude":       d["lon"],
            "location_status": d["status"],
            "slo_target":      "99.5",
            "slo_status":      "99.5",
            "error_budget":    "100",
        })
        new_id = r.get("data", {}).get("loc_id") or r.get("data", {}).get("location_id")
        if not new_id:
            # Fall back: re-fetch and find by name
            locs = api("GET", "/locations?limit=50").get("data", {}).get("items", [])
            for l in locs:
                if l["location_name"] == name:
                    new_id = l["location_id"]
                    break
        loc_id_map[name] = new_id
        ok(f"Created  {name} (id={new_id})  lat={d['lat']} lon={d['lon']}")

# Final location state
final_locs = api("GET", "/locations?limit=50").get("data", {}).get("items", [])
info(f"Locations now in DB:")
for l in final_locs:
    info(f"  id={l['location_id']}  {l['location_name']}  lat={l.get('latitude','?')} lon={l.get('longitude','?')}")

# Rebuild map from fresh data in case IDs changed
loc_id_map = {}
for l in final_locs:
    loc_id_map[l["location_name"]] = l["location_id"]

print(f"\n  Location ID map: {loc_id_map}")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Seed 91 flows from uns_model.py
# ══════════════════════════════════════════════════════════════════════════════
section("STEP 4  ·  Seed 91 flows from UNS simulator model")

info(f"Simulator streams loaded: {len(STREAMS)}")
info(f"Location map: {loc_id_map}")

# Validate all locations are in the map
missing_locs = set(s["location"] for s in STREAMS if s.get("location")) - set(loc_id_map.keys())
if missing_locs:
    warn(f"Streams reference locations not in DB: {missing_locs}")
    sys.exit(1)

created  = 0
skipped  = 0
errors_f = []

# Source → classification / priority mappings
def ai_class(source):  return CLASSIFICATION.get(source, "telemetry")
def ai_prio(source):   return PRIORITY.get(source, "normal")

# Human-readable description from stream metadata
def make_desc(s):
    parts = s.get("area", "").split("/")
    area  = " › ".join(parts[-2:]) if len(parts) >= 2 else s.get("area", "")
    return (
        f"{s.get('source','?')} sensor — {area} — "
        f"interval {s.get('interval',0)}s — "
        f"{s.get('source_detail','')}"
    )

for stream in STREAMS:
    loc_name = stream.get("location", "")
    loc_id   = loc_id_map.get(loc_name)
    if not loc_id:
        warn(f"No loc_id for location '{loc_name}' on stream {stream['id']} — skipping")
        skipped += 1
        continue

    interval = stream.get("interval", 60)
    if isinstance(interval, float) and interval < 1:
        # Sub-second intervals (e.g. 0.5s) → round up to 1 for DB
        interval = 1

    body = {
        "location_id":       loc_id,
        "flow_topic":        stream["topic"],
        "flow_name":         stream["label"],
        "flow_desc":         make_desc(stream),
        "flow_status":       0,    # 0=active
        "flow_parent":       0,
        "flow_default_interval": int(interval),
        "flow_warn_interval":    int(interval * WARN_MULT),
        "flow_alert_interval":   int(interval * ALERT_MULT),
        "ai_classification": ai_class(stream.get("source", "")),
        "ai_priority":       ai_prio(stream.get("source", "")),
    }

    try:
        r = api("POST", "/flows", body)
        new_id = (r.get("data") or {}).get("flow_id", "?")
        created += 1
        if created % 10 == 0 or created <= 3:
            ok(f"[{created:>3}] id={new_id}  {stream['id']}")
    except RuntimeError as e:
        errors_f.append(f"{stream['id']}: {e}")
        warn(f"Failed to create {stream['id']}: {e}")

    # Small pause to avoid hammering the API
    time.sleep(0.05)

ok(f"Created {created} flows  ({skipped} skipped, {len(errors_f)} errors)")
if errors_f:
    warn("Errors:")
    for e in errors_f[:10]:
        info(f"  {e}")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — Verify
# ══════════════════════════════════════════════════════════════════════════════
section("STEP 5  ·  Verification")

# Re-fetch and summarise
final_locs = api("GET", "/locations?limit=50").get("data", {}).get("items", [])
total_flows = 0
for loc in final_locs:
    lid   = loc["location_id"]
    lname = loc["location_name"]
    flows = api("GET", f"/flows?location_id={lid}&limit=200").get("data", {}).get("items", [])
    total_flows += len(flows)
    info(f"  {lname} (id={lid}): {len(flows)} flows")
    if flows:
        # Check a sample topic
        sources = {}
        for f in flows:
            # Parse source from desc or just count
            src = f.get("ai_classification", "?")
            sources[src] = sources.get(src, 0) + 1
        info(f"    classifications: {sources}")

print()
ok(f"Total: {len(final_locs)} locations  |  {total_flows} flows")

expected = len(STREAMS)
if total_flows == expected:
    ok(f"Flow count matches simulator ({expected}) ✓")
else:
    warn(f"Flow count mismatch: DB has {total_flows}, simulator has {expected}")

print()
print("━"*60)
print("  Migration complete.")
print("  Next: restart the pipeline-monitor ECS task so it refreshes")
print("  its cache and starts matching the new flow topics.")
print("━"*60)
