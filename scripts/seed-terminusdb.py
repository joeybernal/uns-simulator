#!/usr/bin/env python3
"""
Seed TerminusDB admin/aurora database with:
  1. Asset documents (from STREAMS)
  2. FaultScenario documents (from FAULT_SCENARIOS)
  3. PlantState document (active_scenario = "normal")

Usage:
    python3 scripts/seed-terminusdb.py

Env vars (optional, defaults shown):
    TERMINUS_URL   = https://terminusdb.iotdemozone.com
    TERMINUS_USER  = admin
    TERMINUS_PASS  = 8Cv7R#ME
    TERMINUS_DB    = admin/aurora
"""

import sys, os, json, time, requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from aurora_model import STREAMS, FAULT_SCENARIOS

# ── Config ──────────────────────────────────────────────────────────────────
BASE      = os.environ.get("TERMINUS_URL",  "https://terminusdb.iotdemozone.com")
USER      = os.environ.get("TERMINUS_USER", "admin")
PASS      = os.environ.get("TERMINUS_PASS", "8Cv7R#ME")
DB        = os.environ.get("TERMINUS_DB",   "admin/aurora")
DOC_URL   = f"{BASE}/api/document/{DB}"
auth      = (USER, PASS)
headers   = {"Content-Type": "application/json"}

def post_docs(docs, label):
    """POST a list of documents to TerminusDB, using insert mode."""
    if not docs:
        print(f"  {label}: nothing to post")
        return
    resp = requests.post(
        DOC_URL,
        params={"author": "seed-script", "message": f"Seed {label}"},
        auth=auth,
        headers=headers,
        json=docs,
        timeout=30,
    )
    if resp.status_code in (200, 201):
        print(f"  ✅ {label}: {len(docs)} documents inserted")
    elif resp.status_code == 409:
        # Already exist — use PUT to replace
        resp2 = requests.put(
            DOC_URL,
            params={"author": "seed-script", "message": f"Replace {label}"},
            auth=auth,
            headers=headers,
            json=docs,
            timeout=30,
        )
        if resp2.status_code in (200, 201):
            print(f"  ✅ {label}: {len(docs)} documents replaced (already existed)")
        else:
            print(f"  ⚠️  {label}: PUT returned {resp2.status_code}: {resp2.text[:200]}")
    else:
        print(f"  ❌ {label}: {resp.status_code}: {resp.text[:300]}")

# ── 1. Assets ────────────────────────────────────────────────────────────────
print("Seeding Assets…")
seen_assets = {}
for s in STREAMS:
    aid = s.get("asset_id")
    if not aid or aid in seen_assets:
        continue
    seen_assets[aid] = {
        "@type":            "Asset",
        "@id":              f"Asset/{aid}",
        "asset_id":         aid,
        "asset_type":       s.get("asset_type", "press"),
        "label":            aid.replace("_", " ").title(),
        "area":             s.get("area", "unknown"),
        "operational_status": "normal",
    }

asset_docs = list(seen_assets.values())
post_docs(asset_docs, f"Assets ({len(asset_docs)})")

# ── 2. FaultScenarios ────────────────────────────────────────────────────────
print("Seeding FaultScenarios…")
scenario_docs = []
for sid, sc in FAULT_SCENARIOS.items():
    sev_map = {"normal": "info", "warning": "warning"}
    severity = "critical"
    if sid == "normal":
        severity = "info"
    elif sc.get("kpi_impact", {}).get("oee", 100) > 60:
        severity = "warning"

    doc = {
        "@type":       "FaultScenario",
        "@id":         f"FaultScenario/{sid}",
        "scenario_id": sid,
        "label":       sc.get("label", sid),
        "description": sc.get("description", ""),
        "ai_hint":     sc.get("ai_hint", ""),
        "severity":    severity,
    }
    if sc.get("fault_key"):
        doc["fault_key"] = sc["fault_key"]

    # Link affected assets that exist in our asset set
    affected = []
    for asset_id in sc.get("affected", []):
        if asset_id in seen_assets:
            affected.append({"@type": "@id", "@id": f"Asset/{asset_id}"})
    if affected:
        doc["affected_assets"] = affected

    scenario_docs.append(doc)

post_docs(scenario_docs, f"FaultScenarios ({len(scenario_docs)})")

# ── 3. PlantState ────────────────────────────────────────────────────────────
print("Seeding PlantState…")
now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
plant_state = [{
    "@type":           "PlantState",
    "@id":             "PlantState/aurora",
    "active_scenario": {"@type": "@id", "@id": "FaultScenario/normal"},
    "last_updated":    now_iso,
    "mqtt_connected":  True,
    "active_faults":   [],
}]
post_docs(plant_state, "PlantState")

# ── 4. Summary ───────────────────────────────────────────────────────────────
print()
print("=== Verify ===")
resp = requests.get(DOC_URL, params={"count": "true"}, auth=auth, timeout=10)
if resp.status_code == 200:
    try:
        data = resp.json()
        print(f"Total documents in admin/aurora: {data}")
    except:
        print(f"Response: {resp.text[:200]}")
else:
    print(f"Count check failed: {resp.status_code}: {resp.text[:200]}")
