# TerminusDB — Aurora Scenario & Digital Twin Context Layer

## The Core Idea: Three Layers, Three Purposes

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: InfluxDB — "What is happening RIGHT NOW?"         │
│  Time-series telemetry: speed, pressure, OEE, temp, etc.   │
│  Tags: asset_id, scenario, area, source                     │
│  Retention: 30 days rolling                                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  LAYER 2: TerminusDB — "WHY is it happening? Who is         │
│           affected? What does it MEAN?"                     │
│  Graph of: Assets → Lines → Plant                           │
│            Scenarios → AffectedAssets → CausalChains       │
│            ScenarioEvents (timestamped activations)        │
│            Thresholds, Recommendations, WorkOrders         │
│  Updated: When scenarios change, on fault events           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  LAYER 3: BaSyx AAS — "What IS this asset?"                 │
│  Identity, type, manufacturer, rated specs, certificates   │
│  Submodels: NameplateData, TechnicalData, Documentation    │
│  Updated: Slowly, lifecycle events only                     │
└─────────────────────────────────────────────────────────────┘
```

---

## What TerminusDB Gives You That InfluxDB Cannot

| Question | InfluxDB | TerminusDB |
|----------|----------|------------|
| PR01 pressure is dropping — what else is affected? | ❌ No relationships | ✅ Graph traversal: PR01 → feeds CV01 → affects Line 01 output |
| Which scenario is active and since when? | ✅ Tag on data | ✅ Full history with git-style branching |
| Who is the maintenance owner for press_PR01? | ❌ | ✅ Document property |
| What work orders were open during the cascade failure? | ❌ | ✅ Linked WorkOrder documents |
| Give me all faults where a quality escape happened upstream | ❌ | ✅ WOQL graph query |
| What were the last 5 scenario activations and their outcomes? | ❌ | ✅ ScenarioEvent history |
| Which assets share a hydraulic circuit with PR01? | ❌ | ✅ Relationship traversal |

---

## Proposed TerminusDB Schema

### Document Classes

```json
// Asset — maps to AAS AssetAdministrationShell
{
  "@type": "Class",
  "@id": "Asset",
  "asset_id": "xsd:string",
  "asset_type": {"@type": "Enum", "@values": ["press","conveyor","oven","robot","sprayer","compressor","vision"]},
  "label": "xsd:string",
  "area": "xsd:string",
  "line": {"@type": "Optional", "@class": "ProductionLine"},
  "aas_id": {"@type": "Optional", "xsd:string": ""},
  "health_score": {"@type": "Optional", "xsd:decimal": ""},
  "operational_status": {"@type": "Optional", "xsd:string": ""}
}

// ProductionLine
{
  "@type": "Class",
  "@id": "ProductionLine",
  "line_id": "xsd:string",
  "label": "xsd:string",
  "assets": {"@type": "Set", "@class": "Asset"}
}

// FaultScenario — the static definition
{
  "@type": "Class",
  "@id": "FaultScenario",
  "scenario_id": "xsd:string",
  "label": "xsd:string",
  "description": "xsd:string",
  "ai_hint": "xsd:string",
  "affected_assets": {"@type": "Set", "@class": "Asset"},
  "severity": {"@type": "Enum", "@values": ["info","warning","critical","emergency"]},
  "fault_key": {"@type": "Optional", "xsd:string": ""}
}

// ScenarioEvent — records every activation/deactivation (the live history)
{
  "@type": "Class",
  "@id": "ScenarioEvent",
  "scenario": "FaultScenario",
  "activated_at": "xsd:dateTime",
  "deactivated_at": {"@type": "Optional", "xsd:dateTime": ""},
  "duration_s": {"@type": "Optional", "xsd:integer": ""},
  "triggered_by": {"@type": "Enum", "@values": ["ui","api","automatic"]},
  "influx_measurement": "xsd:string",
  "notes": {"@type": "Optional", "xsd:string": ""}
}

// PlantState — single document, updated on every scenario change
{
  "@type": "Class",
  "@id": "PlantState",
  "active_scenario": "FaultScenario",
  "last_updated": "xsd:dateTime",
  "mqtt_connected": "xsd:boolean",
  "active_faults": {"@type": "Set", "xsd:string": ""}
}
```

---

## How TerminusDB Updates When Scenarios Change

### Option A — Direct write from aurora_simulator.py (RECOMMENDED)

Add a `_write_terminus()` call alongside `_write_influx()` in the scenario change handler:

```python
# In aurora_simulator.py — set_scenario() endpoint
@app.post("/api/scenario/{scenario_id}")
async def set_scenario(scenario_id: str):
    old_scenario = STATE.active_scenario
    STATE.active_scenario = scenario_id
    sc = FAULT_SCENARIOS[scenario_id]
    
    # Existing: publish to MQTT
    await WS_MGR.broadcast(...)
    
    # NEW: update TerminusDB
    asyncio.create_task(_update_terminus_scenario(old_scenario, scenario_id, sc))
    
    return {"ok": True, ...}

async def _update_terminus_scenario(old_id: str, new_id: str, sc: dict):
    now = datetime.utcnow().isoformat() + "Z"
    
    # 1. Close the previous ScenarioEvent (set deactivated_at)
    # 2. Create a new ScenarioEvent document
    # 3. Update PlantState.active_scenario
    
    payload = {
        "@type": "ScenarioEvent",
        "@id": f"ScenarioEvent/{now}_{new_id}",
        "scenario": {"@type": "@id", "@id": f"FaultScenario/{new_id}"},
        "activated_at": now,
        "triggered_by": "api",
        "influx_measurement": "aurora_data"
    }
    # POST to TERMINUS_URL/api/document/aurora/local/branch/main
```

### Option B — aurora-aas-sync subscribes to MQTT scenario_change events

The `aurora-aas-sync` service already subscribes to MQTT. Add a handler that:
1. Listens for `type: "scenario_change"` messages 
2. Writes the ScenarioEvent to TerminusDB via its REST API

This keeps the simulator clean and gives TerminusDB updates even if the UI triggers scenarios directly via MQTT.

### Option C — Dedicated sync microservice (most scalable)

A small Python service that:
- Subscribes to `aurora/+/+/+` MQTT topics
- Polls `/api/status` every 10s
- On scenario change: writes ScenarioEvent + updates PlantState
- On asset fault tags appearing: updates Asset.operational_status + health_score

---

## How TerminusDB Contrasts With Digital Twin (AAS) Data

```
                    ┌──────────────────────────┐
                    │   AAS (BaSyx)            │
                    │   "What IS this thing?"  │
                    │                          │
                    │  press_PR01:             │
                    │  - Manufacturer: SCHULER  │
                    │  - RatedForce: 2500 kN   │
                    │  - SerialNo: SCH-2024-01 │
                    │  - Certification: ISO... │
                    └──────────┬───────────────┘
                               │ aas_id link
                    ┌──────────▼───────────────┐
                    │   TerminusDB             │
                    │   "What ROLE does it     │
                    │    play & what happened?"│
                    │                          │
                    │  Asset/press_PR01:       │
                    │  - line → Line01         │
                    │  - feeds → CV01 (graph)  │
                    │  - health_score: 71%     │
                    │  - active scenario: ...  │
                    │  - 12 ScenarioEvents     │
                    │  - 3 open WorkOrders     │
                    └──────────┬───────────────┘
                               │ asset_id tag
                    ┌──────────▼───────────────┐
                    │   InfluxDB               │
                    │   "What is it DOING      │
                    │    right now?"           │
                    │                          │
                    │  press_PR01:             │
                    │  - pressure: 186.2 bar   │
                    │  - oee: 0.76             │
                    │  - cycle_time_s: 4.8     │
                    │  - scenario: pr01_wear   │
                    └──────────────────────────┘
```

### The Key Contrast

| Dimension | AAS (BaSyx) | TerminusDB | InfluxDB |
|-----------|-------------|------------|----------|
| **Data type** | Identity & specs | Relationships & events | Measurements |
| **Time model** | Versioned (slow) | Git-branched history | Time series |
| **Query style** | REST / AASX | WOQL graph traversal | Flux |
| **AI use** | "What cert does this have?" | "What caused this cascade?" | "Show me the trend" |
| **Update rate** | Lifecycle (rare) | Event-driven (scenario changes) | Every 5 seconds |
| **Why it matters** | Compliance, specs | Root cause, relationships | Anomaly detection |

---

## Recommended Implementation Plan

### Phase 1 — Seed static data (1-2 hours)

Write a one-time script that POSTs to TerminusDB:
1. All 12 `FaultScenario` documents (from `FAULT_SCENARIOS` dict)
2. All `Asset` documents (from `STREAMS` dict)
3. All `ProductionLine` documents with asset membership
4. Initial `PlantState` (scenario = "normal")

### Phase 2 — Live scenario sync (2-3 hours)

Modify `aurora_simulator.py`:
- On scenario change → POST `ScenarioEvent` to TerminusDB
- On `/api/reset` → close open ScenarioEvent, update PlantState
- Add `TERMINUS_URL` + `TERMINUS_TOKEN` env vars to task def

### Phase 3 — Asset health updates (ongoing)

In the background ticker that writes to InfluxDB, also:
- Update `Asset.health_score` in TerminusDB when it changes significantly (>5%)
- Update `Asset.operational_status` on fault state transitions

### Phase 4 — AI contextual queries (demo value)

With this in place, an AI agent can answer:
- *"PR01 pressure is dropping — give me the full context"*
  → TerminusDB: active scenario, affected assets, last 3 events, linked AAS specs
  → InfluxDB: last 10 min of pressure trend
  → Combined: causal chain + recommendation + historical precedent

---

## Quick Start: Create the aurora database in TerminusDB

```bash
# 1. Create database
curl -X POST https://terminusdb.iotdemozone.com/api/db/admin/aurora \
  -u admin:<password> \
  -H "Content-Type: application/json" \
  -d '{"label":"Aurora Digital Twin","comment":"Aurora plant graph, scenarios, events","schema":true}'

# 2. Post schema
# (Use terminusdb-mcp-server insert-document tool with the schema JSON above)

# 3. Seed data
# Run: node scripts/seed-terminusdb.js
```

The seed script would be ~200 lines of JS that reads `FAULT_SCENARIOS` from the Aurora API
(`GET /api/scenarios`) and posts them to TerminusDB.
