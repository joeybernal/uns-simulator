#!/usr/bin/env node
/**
 * seed-terminusdb.js
 *
 * Seeds the TerminusDB 'aurora' database with:
 *   1. Schema classes (ProductionLine, Asset, FaultScenario, ScenarioEvent, PlantState)
 *   2. ProductionLine documents
 *   3. Asset documents (pulled live from aurora API)
 *   4. FaultScenario documents (pulled live from aurora API)
 *   5. Initial PlantState document
 *
 * Usage:
 *   TERMINUS_URL=https://terminusdb.iotdemozone.com \
 *   TERMINUS_PASS=8Cv7R#ME \
 *   AURORA_API=https://aurora-api.iotdemozone.com \
 *   AURORA_KEY=<api-key> \
 *   node scripts/seed-terminusdb.js
 */

// Node 24 has built-in fetch — no import needed

const TERMINUS_URL = process.env.TERMINUS_URL || "https://terminusdb.iotdemozone.com";
const TERMINUS_USER = process.env.TERMINUS_USER || "admin";
const TERMINUS_PASS = process.env.TERMINUS_PASS || "8Cv7R#ME";
const TERMINUS_TEAM = process.env.TERMINUS_TEAM || "admin";
const TERMINUS_DB   = process.env.TERMINUS_DB   || "aurora";
const AURORA_API    = process.env.AURORA_API    || "https://aurora-api.iotdemozone.com";
const AURORA_KEY    = process.env.AURORA_KEY    || "";

const AUTH = "Basic " + Buffer.from(`${TERMINUS_USER}:${TERMINUS_PASS}`).toString("base64");
const DB_BASE = `${TERMINUS_URL}/api/document/${TERMINUS_TEAM}/${TERMINUS_DB}`;
const SCHEMA_URL = `${DB_BASE}?graph_type=schema&author=seed&message=initial+schema`;
const DOC_URL    = `${DB_BASE}?author=seed&message=initial+seed`;

// ─── helpers ────────────────────────────────────────────────────────────────

async function tpost(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: AUTH },
    body: JSON.stringify(body),
  });
  const txt = await r.text();
  if (!r.ok) throw new Error(`POST ${url} → ${r.status}: ${txt}`);
  return JSON.parse(txt);
}

async function auroraGet(path) {
  const headers = AURORA_KEY ? { "X-API-Key": AURORA_KEY } : {};
  const r = await fetch(`${AURORA_API}${path}`, { headers });
  if (!r.ok) throw new Error(`Aurora GET ${path} → ${r.status}`);
  return r.json();
}

// ─── 1. SCHEMA ───────────────────────────────────────────────────────────────

const SCHEMA = [
  // Enums
  {
    "@type": "Enum",
    "@id": "AssetType",
    "@value": ["press","conveyor","oven","robot","sprayer","compressor","vision","cell","other"],
  },
  {
    "@type": "Enum",
    "@id": "Severity",
    "@value": ["info","warning","critical","emergency"],
  },
  {
    "@type": "Enum",
    "@id": "TriggerSource",
    "@value": ["ui","api","automatic","mqtt"],
  },

  // ProductionLine
  {
    "@type": "Class",
    "@id": "ProductionLine",
    "@key": { "@type": "Lexical", "@fields": ["line_id"] },
    "line_id": "xsd:string",
    "label": "xsd:string",
  },

  // Asset
  {
    "@type": "Class",
    "@id": "Asset",
    "@key": { "@type": "Lexical", "@fields": ["asset_id"] },
    "asset_id": "xsd:string",
    "asset_type": "AssetType",
    "label": "xsd:string",
    "area": "xsd:string",
    "line": { "@type": "Optional", "@class": "ProductionLine" },
    "aas_id": { "@type": "Optional", "@class": "xsd:string" },
    "health_score": { "@type": "Optional", "@class": "xsd:decimal" },
    "operational_status": { "@type": "Optional", "@class": "xsd:string" },
  },

  // FaultScenario
  {
    "@type": "Class",
    "@id": "FaultScenario",
    "@key": { "@type": "Lexical", "@fields": ["scenario_id"] },
    "scenario_id": "xsd:string",
    "label": "xsd:string",
    "description": "xsd:string",
    "ai_hint": "xsd:string",
    "severity": "Severity",
    "fault_key": { "@type": "Optional", "@class": "xsd:string" },
    "affected_assets": { "@type": "Set", "@class": "Asset" },
  },

  // ScenarioEvent
  {
    "@type": "Class",
    "@id": "ScenarioEvent",
    "@key": { "@type": "Random" },
    "scenario": "FaultScenario",
    "activated_at": "xsd:dateTime",
    "deactivated_at": { "@type": "Optional", "@class": "xsd:dateTime" },
    "duration_s": { "@type": "Optional", "@class": "xsd:integer" },
    "triggered_by": "TriggerSource",
    "influx_query_hint": { "@type": "Optional", "@class": "xsd:string" },
    "notes": { "@type": "Optional", "@class": "xsd:string" },
  },

  // PlantState — singleton, @id = "PlantState/current"
  {
    "@type": "Class",
    "@id": "PlantState",
    "@key": { "@type": "Lexical", "@fields": ["plant_id"] },
    "plant_id": "xsd:string",
    "active_scenario": "FaultScenario",
    "last_updated": "xsd:dateTime",
    "mqtt_connected": "xsd:boolean",
  },
];

// ─── 2. STATIC PRODUCTION LINES ─────────────────────────────────────────────

const LINES = [
  { "@type": "ProductionLine", "line_id": "line_01", "label": "Line 01" },
  { "@type": "ProductionLine", "line_id": "line_02", "label": "Line 02" },
  { "@type": "ProductionLine", "line_id": "utilities", "label": "Utilities" },
];

// ─── severity mapping ────────────────────────────────────────────────────────

function severityOf(sc) {
  const desc = (sc.description || "").toLowerCase();
  const label = (sc.label || "").toLowerCase();
  if (/runaway|cascade|emergency|scorch|stop/.test(desc + label)) return "emergency";
  if (/escape|failure|blocked|jam|leak|shortage/.test(desc + label)) return "critical";
  if (/wear|drift|drop|blockage|anomaly/.test(desc + label)) return "warning";
  return "info";
}

// ─── asset_type mapping ──────────────────────────────────────────────────────

function assetTypeOf(id) {
  if (/^press/.test(id))      return "press";
  if (/^conv/.test(id))       return "conveyor";
  if (/^oven/.test(id))       return "oven";
  if (/^robot/.test(id))      return "robot";
  if (/^spray/.test(id))      return "sprayer";
  if (/^comp/.test(id))       return "compressor";
  if (/^vision|^cmm/.test(id))return "vision";
  if (/^cell/.test(id))       return "cell";
  return "other";
}

function lineRefOf(area) {
  if (!area) return undefined;
  const a = area.toLowerCase();
  if (/line.?01|line.?1/.test(a)) return { "@type": "@id", "@id": "ProductionLine/line_01" };
  if (/line.?02|line.?2/.test(a)) return { "@type": "@id", "@id": "ProductionLine/line_02" };
  if (/util/.test(a))             return { "@type": "@id", "@id": "ProductionLine/utilities" };
  return undefined;
}

// ─── MAIN ────────────────────────────────────────────────────────────────────

async function main() {
  console.log("=== Aurora → TerminusDB seed ===\n");

  // ── Schema ──
  console.log("1. Posting schema...");
  await tpost(SCHEMA_URL, SCHEMA);
  console.log("   ✓ Schema posted");

  // ── Lines ──
  console.log("2. Seeding production lines...");
  await tpost(DOC_URL, LINES);
  console.log(`   ✓ ${LINES.length} lines`);

  // ── Assets from Aurora API ──
  console.log("3. Fetching assets from Aurora API...");
  let assets = [];
  try {
    const status = await auroraGet("/api/status");
    const streams = status.streams || [];
    console.log(`   Found ${streams.length} streams`);

    const seenAssets = new Set();
    for (const s of streams) {
      const aid = s.asset_id || s.id;
      if (!aid || seenAssets.has(aid)) continue;
      seenAssets.add(aid);
      const lineRef = lineRefOf(s.area);
      const doc = {
        "@type": "Asset",
        "asset_id": aid,
        "asset_type": assetTypeOf(aid.toLowerCase()),
        "label": s.label || aid,
        "area": s.area || "Plant",
        "operational_status": "running",
      };
      if (lineRef) doc["line"] = lineRef;
      assets.push(doc);
    }
  } catch (e) {
    console.warn(`   Warning: Could not fetch from Aurora API (${e.message})`);
    console.warn("   Using fallback asset list...");
    // Fallback list based on known Aurora plant
    const fallback = [
      { id: "press_PR01", label: "Press PR01", area: "Line 01" },
      { id: "press_PR02", label: "Press PR02", area: "Line 01" },
      { id: "conveyor_CV01", label: "Conveyor CV01", area: "Line 01" },
      { id: "conveyor_CV02", label: "Conveyor CV02", area: "Line 01" },
      { id: "conveyor_CV03", label: "Conveyor CV03", area: "Line 01" },
      { id: "conveyor_CV04", label: "Conveyor CV04", area: "Line 02" },
      { id: "conveyor_CV05", label: "Conveyor CV05", area: "Line 02" },
      { id: "oven_OV01", label: "Oven OV01", area: "Line 01" },
      { id: "robot_R1", label: "Robot R1 (Weld)", area: "Line 01" },
      { id: "robot_R3", label: "Robot R3 (Paint)", area: "Line 02" },
      { id: "sprayer_SP01", label: "Sprayer SP01", area: "Line 02" },
      { id: "sprayer_SP02", label: "Sprayer SP02", area: "Line 02" },
      { id: "compressor_CP01", label: "Compressor CP01", area: "Utilities" },
      { id: "vision_CMM01", label: "Vision CMM01", area: "Line 01" },
    ];
    for (const f of fallback) {
      const lineRef = lineRefOf(f.area);
      const doc = {
        "@type": "Asset",
        "asset_id": f.id,
        "asset_type": assetTypeOf(f.id.toLowerCase()),
        "label": f.label,
        "area": f.area,
        "operational_status": "running",
      };
      if (lineRef) doc["line"] = lineRef;
      assets.push(doc);
    }
  }

  await tpost(DOC_URL, assets);
  console.log(`   ✓ ${assets.length} assets seeded`);

  // ── Scenarios from Aurora API ──
  console.log("4. Fetching scenarios from Aurora API...");
  let scenarioDocs = [];
  try {
    const scenData = await auroraGet("/api/scenarios");
    const list = scenData.scenarios || [];
    console.log(`   Found ${list.length} scenarios`);

    for (const sc of list) {
      const affected = (sc.affected_assets || sc.affected_streams || []).map((aid) => ({
        "@type": "@id",
        "@id": `Asset/${aid}`,
      }));
      scenarioDocs.push({
        "@type": "FaultScenario",
        "scenario_id": sc.id,
        "label": sc.label,
        "description": sc.description,
        "ai_hint": sc.ai_hint || "",
        "severity": severityOf(sc),
        "fault_key": sc.fault_key || null,
        "affected_assets": affected,
      });
    }
  } catch (e) {
    console.warn(`   Warning: Could not fetch scenarios (${e.message})`);
  }

  // Always ensure "normal" scenario exists
  if (!scenarioDocs.find((s) => s.scenario_id === "normal")) {
    scenarioDocs.unshift({
      "@type": "FaultScenario",
      "scenario_id": "normal",
      "label": "Normal Operation",
      "description": "All assets operating within normal parameters.",
      "ai_hint": "No anomalies. Plant OEE ~79%. Energy consumption nominal.",
      "severity": "info",
      "affected_assets": [],
    });
  }

  await tpost(DOC_URL, scenarioDocs);
  console.log(`   ✓ ${scenarioDocs.length} scenarios seeded`);

  // ── PlantState ──
  console.log("5. Creating initial PlantState...");
  const plantState = {
    "@type": "PlantState",
    "plant_id": "aurora",
    "active_scenario": { "@type": "@id", "@id": "FaultScenario/normal" },
    "last_updated": new Date().toISOString().replace("Z", "+00:00"),
    "mqtt_connected": true,
  };
  await tpost(DOC_URL, plantState);
  console.log("   ✓ PlantState/aurora created (scenario: normal)");

  console.log("\n=== Seed complete ===");
  console.log(`   TerminusDB: ${TERMINUS_URL}`);
  console.log(`   Database:   ${TERMINUS_TEAM}/${TERMINUS_DB}`);
  console.log(`   Assets:     ${assets.length}`);
  console.log(`   Scenarios:  ${scenarioDocs.length}`);
}

main().catch((e) => {
  console.error("SEED FAILED:", e.message);
  process.exit(1);
});
