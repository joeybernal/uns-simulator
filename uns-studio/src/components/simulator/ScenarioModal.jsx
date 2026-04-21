import { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'

// Full demo guide content keyed by scenario id
export const SCENARIO_GUIDE = {
  normal: {
    title: 'Normal Operation',
    subtitle: 'All systems nominal across all three plants',
    icon: 'fa-circle-check',
    iconColor: 'text-emerald-400',
    badge: 'NORMAL',
    badgeColor: 'bg-emerald-900/60 text-emerald-300 border-emerald-700',
    overview: `All 91 data streams are publishing live sensor readings within
specification limits. The three plant locations — Frankfurt Paint Shop,
Munich Assembly, and Ingolstadt Press + Body Shop — are operating at
full capacity with no active faults.

Use this mode as the baseline to show what healthy UNS data looks like
before introducing a fault scenario.`,
    howItWorks: [
      'Every stream generates Gaussian noise around its nominal value with Brownian drift',
      'Thermal cycling, wear index and shift warmup add realistic variation',
      'All values stay within spec_min / spec_max bands — status is OK',
      'MQTT publishes full ISA-95 payloads including stats, health and quality fields',
    ],
    whatItShows: [
      'Live MQTT message flow across PLC, MES, ERP and SCADA source systems',
      'Per-stream publish counters and last-value updating in real time',
      'Location-level KPI aggregation (OEE, FPY, Availability)',
      'WebSocket live feed with sub-second latency from ECS to browser',
    ],
    demoScript: [
      { step: '1', title: 'Orient the audience', text: 'Point to the three location cards — Frankfurt Paint Shop, Munich Assembly, Ingolstadt Press Shop. Show the stream count and source breakdown (PLC / MES / ERP / SCADA).' },
      { step: '2', title: 'Show the live feed', text: 'Open the Live Feed panel on the right. Watch messages arriving from all three plants. Filter by PLC to show raw sensor data vs MES/ERP process events.' },
      { step: '3', title: 'Explain the topic hierarchy', text: 'Click any stream to see its full MQTT topic — IoTAuto_GmbH / Location / Shop / Line / Area / Asset / Measurement. This is ISA-95 Level 2 → Level 3 in a single topic.' },
      { step: '4', title: 'Transition', text: 'Say: "Now let me show you what happens when a fault occurs in the real plant." Then click a fault scenario in the sidebar.' },
    ],
  },

  pretreatment_filter_clog: {
    title: 'Pretreatment Filter Clog',
    subtitle: 'Frankfurt Paint Shop — Pretreatment Line',
    icon: 'fa-filter-circle-xmark',
    iconColor: 'text-amber-400',
    badge: 'AMBER ALERT',
    badgeColor: 'bg-amber-900/60 text-amber-300 border-amber-700',
    overview: `Filter01 on the Frankfurt pretreatment line is progressively clogging.
Differential pressure across the filter is rising above the 0.8 bar spec limit,
causing a reduction in pump flow rate from the nominal 120 L/min down toward
55 L/min. The MES has placed the pretreatment line in MAINTENANCE mode and
OEE has dropped to ~52%.

This is one of the most common faults in automotive paint shops —
a clogged pretreatment filter directly impacts coating adhesion quality
and line throughput.`,
    howItWorks: [
      'Filter01 DiffPressure sensor drifts from 0.3 bar → 1.4 bar (alarm_hi = 1.2 bar)',
      'Pump01 FlowRate drops from 120 L/min → 55 L/min (spec_min = 100)',
      'Pretreatment Line Status flips from RUNNING → MAINTENANCE',
      'Pretreatment KPI OEE degrades from 84% → 52%',
      'All other Frankfurt streams (ECoat, Primer, etc.) continue normally',
    ],
    whatItShows: [
      'How a single mechanical fault cascades into process KPIs',
      'Correlated anomalies: pressure UP while flow is DOWN — classic clog signature',
      'MES status change propagating alongside PLC sensor alarms',
      'How UNS enables cross-system correlation — PLC and MES data on the same bus',
    ],
    demoScript: [
      { step: '1', title: 'Set the scene', text: 'Say: "In Frankfurt, our pretreatment line preps car bodies before e-coat. A clogged filter is a common issue that used to take hours to diagnose." Click "FR: Filter Clog" in the sidebar.' },
      { step: '2', title: 'Show the alarms', text: 'Filter the stream table to Frankfurt / Pretreatment. Point to Filter01 Differential Pressure turning RED (ALARM). Show Pump01 Flow Rate dropping into WARN.' },
      { step: '3', title: 'Show KPI impact', text: 'Open the Pretreatment KPI stream. OEE has dropped from 84% → ~52%. Say: "In the old world this would take 2 hours to correlate. In UNS it is instant — same bus, same timestamp."' },
      { step: '4', title: 'Show MES correlation', text: 'Point to Pretreatment Line Status showing MAINTENANCE. Say: "The MES has already reacted — it detected the flow drop via the UNS topic and changed the work order status automatically."' },
    ],
  },

  pretreatment_tank_overheat: {
    title: 'Pretreatment Tank Overheat',
    subtitle: 'Frankfurt Paint Shop — Tank01',
    icon: 'fa-temperature-arrow-up',
    iconColor: 'text-red-400',
    badge: 'RED ALARM',
    badgeColor: 'bg-red-900/60 text-red-300 border-red-700',
    overview: `Tank01 in the Frankfurt pretreatment line has exceeded its temperature
specification. Temperature is climbing toward 89°C against an alarm limit of
82°C. The heating control loop has failed to regulate, likely due to a
faulty temperature sensor or stuck heating valve.

Immediate action is required — sustained overheating will degrade the
chemical bath and cause inconsistent surface preparation across production.`,
    howItWorks: [
      'Tank01 Temperature climbs from 67°C → ~89°C (alarm_hi = 82°C → status = ALARM)',
      'Pretreatment Line Status flips from RUNNING → ALARM',
      'OEE degrades as the line must be halted for inspection',
      'pH and conductivity streams continue to show normal values — isolated fault',
    ],
    whatItShows: [
      'Single-sensor critical alarm escalating through the ISA-95 hierarchy',
      'Difference between WARN (spec exceeded) and ALARM (alarm limit breached)',
      'How UNS provides the SCADA layer with plant-floor data without a dedicated historian',
    ],
    demoScript: [
      { step: '1', title: 'Introduce the fault', text: 'Say: "This is an overtemperature event in the chemical treatment tank — one of the most safety-critical alarms in a paint shop." Click the scenario.' },
      { step: '2', title: 'Show the temperature stream', text: 'Filter to Frankfurt / Pretreatment / Tank01. Watch the temperature value turning red. Show the spec_min / spec_max and alarm thresholds in the stream detail.' },
      { step: '3', title: 'Explain the payload', text: 'Click the value in the live feed. Show the full JSON payload: value, status: ALARM, quality: Uncertain, stats.deviation_sigma, health.drift. Say: "This is not just a number — it is full context."' },
    ],
  },

  ecoat_bath_contamination: {
    title: 'ECoat Bath Contamination',
    subtitle: 'Frankfurt Paint Shop — ECoat Station',
    icon: 'fa-vial-circle-check',
    iconColor: 'text-red-400',
    badge: 'RED ALARM',
    badgeColor: 'bg-red-900/60 text-red-300 border-red-700',
    overview: `The electrocoat bath in Frankfurt has a contamination event. Bath conductivity
has risen abnormally from 1,400 µS/cm to ~1,900 µS/cm (spec_max = 1,600),
indicating ionic contamination — possibly from drag-in of pretreatment chemicals
or bath component breakdown. Bath temperature is also elevated.

ECoat contamination is one of the most expensive faults in automotive painting —
it can require a full bath dump and replacement costing €50,000–€150,000.`,
    howItWorks: [
      'ECoat Bath Conductivity rises from 1,400 → ~1,900 µS/cm (ALARM threshold = 1,800)',
      'ECoat Bath Temperature rises from 32°C → ~41°C (alarm_hi = 42°C)',
      'ECoat Station Status flips to FAULT',
      'ECoat KPI OEE drops to ~45%',
    ],
    whatItShows: [
      'Multi-signal correlated fault: two independent PLC sensors both abnormal simultaneously',
      'How UNS enables anomaly detection that would be invisible in siloed SCADA systems',
      'ERP-level cost implications visible when combined with MES production order data',
    ],
    demoScript: [
      { step: '1', title: 'Set the scene', text: 'Say: "ECoat is the most capital-intensive step in paint shop — the bath costs hundreds of thousands of euros. Contamination events are catastrophic." Click the scenario.' },
      { step: '2', title: 'Show both sensors', text: 'Filter to Frankfurt / ECoat. Show BOTH conductivity (ALARM) and temperature (approaching ALARM) trending together. Say: "Two independent sensors, same anomaly — this is how you distinguish a real event from a sensor glitch."' },
      { step: '3', title: 'Show the FAULT status', text: 'Point to ECoat Station Status = FAULT. Show the OEE stream. Say: "In a connected UNS the ERP system receives this event in real time and can begin the procurement process for bath chemicals immediately."' },
    ],
  },

  primer_robot_bearing: {
    title: 'Primer Robot Bearing Wear',
    subtitle: 'Frankfurt Paint Shop — Primer Robot01',
    icon: 'fa-gear',
    iconColor: 'text-amber-400',
    badge: 'AMBER ALERT',
    badgeColor: 'bg-amber-900/60 text-amber-300 border-amber-700',
    overview: `Primer Robot01's J3 joint bearing in the Frankfurt paint shop is showing signs
of wear. Motor current has risen from 18 A to ~29 A and vibration has
increased from 1.2 mm/s to ~6.8 mm/s — approaching the ISO 10816
alarm threshold of 7.1 mm/s.

This is a predictive maintenance scenario — the robot is still operational
but bearing replacement should be scheduled within the next maintenance window
to prevent an unplanned breakdown.`,
    howItWorks: [
      'Robot J3 Motor Current rises from 18 A → ~29 A (spec_max = 26 A — WARN)',
      'Vibration rises from 1.2 mm/s → ~6.8 mm/s (alarm_hi = 7.1 mm/s — WARN → ALARM)',
      'Primer Station Status remains RUNNING (predictive — not yet a breakdown)',
      'Primer KPI OEE degrades slightly to ~48% due to speed reduction',
      'wear_index in the health payload increments over time',
    ],
    whatItShows: [
      'Predictive maintenance use case — catch the fault before the breakdown',
      'How vibration + current correlation gives earlier warning than either signal alone',
      'The health.wear_index field in the payload growing in real time',
      'How UNS enables CBM (Condition-Based Maintenance) without a dedicated IoT platform',
    ],
    demoScript: [
      { step: '1', title: 'Frame the business case', text: 'Say: "Unplanned robot downtime in a paint shop costs €10,000–€25,000 per hour. Predictive maintenance cuts this to scheduled 2-hour stops." Click the scenario.' },
      { step: '2', title: 'Show current + vibration', text: 'Filter to Frankfurt / Primer. Show Robot01 Motor Current in WARN. Show Vibration approaching ALARM. Say: "Current rising means the motor is working harder. Vibration rising means the bearing is failing. Together they give us 4–8 hours of warning."' },
      { step: '3', title: 'Show wear_index in payload', text: 'Click the current stream in the Live Feed. Show the health.wear_index field incrementing. Say: "This is real-time bearing health — something that previously required a €50k vibration monitoring system."' },
      { step: '4', title: 'Close the loop', text: 'Say: "With UNS, the maintenance system can subscribe to this topic and auto-generate a work order when wear_index > 0.6. Zero human intervention."' },
    ],
  },

  clearcoat_electrode_wear: {
    title: 'Clearcoat Electrode Wear',
    subtitle: 'Frankfurt Paint Shop — Clearcoat Electrode01',
    icon: 'fa-bolt-lightning',
    iconColor: 'text-amber-400',
    badge: 'MAINTENANCE',
    badgeColor: 'bg-amber-900/60 text-amber-300 border-amber-700',
    overview: `The rotary atomiser electrode on the Frankfurt clearcoat robot has reached
its wear threshold. The wear index is above 0.85 (spec_max = 0.6 — ALARM),
indicating the electrode must be replaced in the next scheduled maintenance
window. Continued operation will result in inconsistent electrostatic charge
and clearcoat film thickness variation.`,
    howItWorks: [
      'Electrode01 WearIndex rises from 0.05 → ~0.9 (alarm_hi = 0.85 — ALARM)',
      'Value is calculated from accumulated electrical discharge cycles',
      'Clearcoat Station Status moves to MAINTENANCE',
      'OEE drops to ~44% as speed is reduced to manage quality risk',
    ],
    whatItShows: [
      'Life-cycle / consumable tracking directly through the UNS',
      'How wear counters from SCADA historian can be published alongside process data',
      'Maintenance scheduling driven by actual wear vs fixed time intervals',
    ],
    demoScript: [
      { step: '1', title: 'Introduce consumable tracking', text: 'Say: "Clearcoat electrode replacement is typically done on a fixed 500-hour schedule. With UNS we replace based on actual wear — typically 20% longer life." Click the scenario.' },
      { step: '2', title: 'Show the wear index', text: 'Filter to Frankfurt / Clearcoat. Show Electrode01 WearIndex at ALARM. Say: "The Ignition SCADA historian is publishing this wear counter to the UNS every 60 seconds."' },
      { step: '3', title: 'Show maintenance trigger', text: 'Point to Clearcoat Station Status = MAINTENANCE. Say: "The MES has already received this signal and created a maintenance work order. The maintenance team is notified automatically."' },
    ],
  },

  curing_oven_temp_runaway: {
    title: 'Curing Oven Temperature Runaway',
    subtitle: 'Frankfurt Paint Shop — Curing Oven',
    icon: 'fa-fire',
    iconColor: 'text-red-400',
    badge: 'CRITICAL',
    badgeColor: 'bg-red-950/80 text-red-200 border-red-600',
    overview: `The Frankfurt curing oven has a temperature runaway condition in Zones 1 and 2.
Zone 1 has reached ~195°C against a spec_max of 170°C and an alarm limit of 185°C.
Zone 2 is at ~210°C. The PLC has raised an ALARM and the oven conveyor has been
halted. This is a critical fault — sustained overtemperature will burn the paint
coatings and can create a fire hazard.

Emergency shutdown procedures have been activated.`,
    howItWorks: [
      'Zone 1 temp: 160°C → ~195°C (alarm_hi = 185°C — ALARM)',
      'Zone 2 temp: 175°C → ~210°C (alarm_hi = 200°C — ALARM)',
      'Oven Status changes from RUNNING → ALARM',
      'OEE collapses to ~20% — oven halted, line stopped',
      'Zone 3 continues at nominal (fault is upstream heating circuit)',
    ],
    whatItShows: [
      'Critical multi-zone alarm escalation through UNS in real time',
      'How independent zone sensors give spatial fault localisation',
      'OEE impact of a line stop — most visible KPI collapse in the demo',
      'Emergency response: show how SCADA, MES and ERP all receive the same alarm topic simultaneously',
    ],
    demoScript: [
      { step: '1', title: 'Build the drama', text: 'Say: "This is the fault that keeps plant managers awake at night — a curing oven runaway. In the old world you would hear about it from the operator. In UNS, every system knows instantly." Click the scenario.' },
      { step: '2', title: 'Show zone temperatures', text: 'Filter to Frankfurt / CuringOven. Zone 1 and Zone 2 are ALARM (red). Zone 3 is still OK. Say: "We can localise the fault to the Zone 1 and Zone 2 heating circuit immediately."' },
      { step: '3', title: 'Show OEE collapse', text: 'Open the Curing Oven KPI stream. OEE is at ~20%. Say: "This is a €5,000-per-minute cost event. With UNS the ERP system can begin production rescheduling before the operator has walked to the oven."' },
      { step: '4', title: 'Show simultaneous notification', text: 'Point to the Live Feed. Show the ALARM messages arriving every 2 seconds from both PLC zones AND the MES status change AND the SCADA historian — all on the same MQTT bus. This is the UNS value proposition in one screen.' },
    ],
  },

  biw_weld_robot1_fault: {
    title: 'BIW Weld Robot Fault',
    subtitle: 'Munich Assembly — Body-in-White Cell',
    icon: 'fa-robot',
    iconColor: 'text-red-400',
    badge: 'RED ALARM',
    badgeColor: 'bg-red-900/60 text-red-300 border-red-700',
    overview: `WeldRobot01 in the Munich BIW (Body-in-White) welding cell has triggered an
overcurrent fault. The FANUC R-2000iC J2 joint motor is drawing ~38 A against
a spec_max of 34 A, and weld current has spiked to ~10,800 A against a
nominal of 8,500 A. The robot controller has placed the robot in FAULT state.

BIW welding faults are high-impact — this is on the critical path of vehicle
production and directly affects output rates (JPH).`,
    howItWorks: [
      'WeldRobot01 J2 Motor Current rises from 24 A → ~38 A (ALARM)',
      'Weld Current spikes from 8,500 A → ~10,800 A (above alarm_hi = 11,000 A)',
      'Robot Status changes to FAULT',
      'BIW Cell KPI OEE drops to ~50%',
      'WeldRobots 02 and 03 continue normally',
    ],
    whatItShows: [
      'Robotics fault data from FANUC controller via MQTT OPC-UA bridge',
      'How joint-level motor current correlates with weld quality degradation',
      'Cell-level OEE impact vs individual robot fault — partial production capability',
    ],
    demoScript: [
      { step: '1', title: 'Switch to Munich', text: 'Click Munich in the location sidebar. Say: "Munich Assembly builds the BIW — the bare metal vehicle structure. This is the highest-precision step in the production chain." Click the scenario.' },
      { step: '2', title: 'Show the fault', text: 'Filter to Munich / BIW. Robot01 Motor Current and Weld Current are both in ALARM. Say: "The FANUC controller publishes joint-level data at 50ms intervals. We catch the fault 200ms after it occurs."' },
      { step: '3', title: 'Show partial operation', text: 'Point to WeldRobots 02 and 03 — still WELDING normally. Say: "With UNS we can see that two-thirds of the cell is still operational. We can reduce line speed rather than stop the entire line."' },
    ],
  },

  fa_bolt_station1_overtorque: {
    title: 'Bolt Station Overtorque',
    subtitle: 'Munich Assembly — Final Assembly',
    icon: 'fa-screwdriver-wrench',
    iconColor: 'text-amber-400',
    badge: 'QUALITY ALERT',
    badgeColor: 'bg-amber-900/60 text-amber-300 border-amber-700',
    overview: `BoltStation01 in the Munich final assembly line has reported repeated overtorque
events. Measured torque is reaching ~26.5 Nm against a spec_max of 24 Nm. This
indicates either a worn torque transducer, incorrect fastener, or tooling
calibration drift. All overtorque bolts must be quarantined for re-work.`,
    howItWorks: [
      'BoltStation01 Torque rises from nominal 22 Nm → ~26.5 Nm (spec_max = 24 Nm — ALARM)',
      'Atlas Copco ICS controller publishes both torque and angle on each tightening',
      'Station Status changes to FAULT on NOK events',
      'Final Assembly OEE degrades to ~62% due to re-work loops',
    ],
    whatItShows: [
      'Quality traceability — every tightening result published to UNS with timestamp',
      'How tightening data from Atlas Copco ICS flows directly into quality systems',
      'Re-work cost visibility: OEE drops proportional to NOK rate',
    ],
    demoScript: [
      { step: '1', title: 'Introduce quality traceability', text: 'Say: "Every bolt tightened in a car is a quality record. With UNS, the Atlas Copco result is on the MQTT bus within 100ms of the tightening completing." Click the scenario.' },
      { step: '2', title: 'Show torque alarm', text: 'Filter to Munich / FinalAssembly. BoltStation01 Torque is in ALARM. Show the angle stream — it is nominal. Say: "Angle is fine but torque is high — this is a fastener issue, not a tool issue."' },
      { step: '3', title: 'Close the quality loop', text: 'Say: "In the old world, the operator scans the barcode, the system checks the tightening archive, 3 minutes later the supervisor is called. In UNS, the MES receives the NOK signal in real time and stops the vehicle at the next station automatically."' },
    ],
  },

  agv_fleet_battery_low: {
    title: 'AGV Fleet Battery Low',
    subtitle: 'Munich Assembly — Logistics',
    icon: 'fa-battery-quarter',
    iconColor: 'text-amber-400',
    badge: 'LOGISTICS ALERT',
    badgeColor: 'bg-amber-900/60 text-amber-300 border-amber-700',
    overview: `AGV02 in the Munich assembly logistics fleet has a critically low battery
level — dropping below 10% (alarm threshold). The KUKA KMR iiwa AGV has
autonomously diverted to a charging station, reducing fleet coverage.
AGV01 has been reallocated to cover AGV02's route but is showing moderate
battery depletion.`,
    howItWorks: [
      'AGV02 Battery Level drops from 60% → ~8% (alarm_lo = 10% — ALARM)',
      'AGV02 Status changes from MOVING → ALARM then CHARGING',
      'AGV01 Status is shown diverting to cover — increased usage',
      'Fleet coverage is reduced — logistics KPI at risk',
    ],
    whatItShows: [
      'Fleet-level logistics data on the UNS alongside manufacturing process data',
      'How AGV battery telemetry drives autonomous fleet rebalancing',
      'Cross-system visibility: MES can see logistics constraint and adjust production sequencing',
    ],
    demoScript: [
      { step: '1', title: 'Show logistics integration', text: 'Say: "Most UNS discussions focus on machine data. But logistics is equally critical — an AGV failure stops material flow just as surely as a robot fault." Click the scenario.' },
      { step: '2', title: 'Show the battery alarm', text: 'Filter to Munich / Logistics. AGV02 battery is critical (ALARM). Show the status — CHARGING. Say: "The AGV has autonomously detected its battery state via the UNS topic and routed itself to charging."' },
      { step: '3', title: 'Show fleet-level impact', text: 'Point to AGV01 — still MOVING but battery draining faster. Say: "The MES can see that fleet coverage is reduced and automatically re-sequences production to reduce material demand until AGV02 is recharged."' },
    ],
  },

  press_shop_die_wear: {
    title: 'Press Shop Die Wear',
    subtitle: 'Ingolstadt — Press Shop',
    icon: 'fa-arrow-down-wide-short',
    iconColor: 'text-amber-400',
    badge: 'PREDICTIVE MAINT.',
    badgeColor: 'bg-amber-900/60 text-amber-300 border-amber-700',
    overview: `Press01 in the Ingolstadt press shop is showing die wear signatures.
Stamping force has risen from 3,200 kN to ~3,750 kN (spec_max = 3,600 kN)
and vibration monitored by the SKF Enlight system has reached 9.5 mm/s —
significantly above the 7.1 mm/s ISO 10816 alarm threshold.

Die replacement should be scheduled immediately to prevent burr formation,
panel dimension drift, or press tonnage overload.`,
    howItWorks: [
      'Press01 Stamping Force rises from 3,200 kN → ~3,750 kN (WARN → ALARM)',
      'Vibration rises from 2.5 mm/s → ~9.5 mm/s via SKF Enlight sensor (ALARM)',
      'Press01 Status moves to FAULT',
      'Press Shop OEE drops to ~40%',
      'Press02 continues normally — single-press fault',
    ],
    whatItShows: [
      'Condition monitoring data from SKF Enlight published alongside PLC force data',
      'Multi-sensor die wear signature: force UP + vibration UP = die worn',
      'How UNS enables integration of specialist condition monitoring systems (SKF) with mainstream PLC data',
    ],
    demoScript: [
      { step: '1', title: 'Switch to Ingolstadt', text: 'Click Ingolstadt in the sidebar. Say: "The Ingolstadt press shop stamps body panels at 22 strokes per minute. Die wear is the most expensive consumable in press shop — a single die costs €800,000." Click the scenario.' },
      { step: '2', title: 'Show force + vibration', text: 'Filter to Ingolstadt / PressShop. Press01 Force is ALARM. Vibration from SKF Enlight is ALARM. Say: "Two completely different systems — Schuler press controller and SKF vibration monitor — both publishing to the same UNS topic hierarchy."' },
      { step: '3', title: 'Show the business case', text: 'Point to Press02 — still operating normally. Say: "One press down, one press running. Without UNS, production planning would not know for 30 minutes. With UNS they know in 30 seconds and can re-schedule panel production immediately."' },
    ],
  },

  body_shop_robot1_collision: {
    title: 'Body Shop Robot E-Stop',
    subtitle: 'Ingolstadt — Body Shop',
    icon: 'fa-triangle-exclamation',
    iconColor: 'text-red-400',
    badge: 'E-STOP',
    badgeColor: 'bg-red-950/80 text-red-200 border-red-600',
    overview: `BodyWeldRobot01 in the Ingolstadt body shop has triggered an Emergency Stop
due to collision protection activation. The KUKA KRC5 controller detected
an unexpected force of ~6.2 kN on the weld gun, exceeding the collision
detection threshold. The robot is in ESTOP state pending a safety inspection.

No restart is possible until a qualified technician has inspected the cell
and confirmed the robot path is clear.`,
    howItWorks: [
      'Robot01 Motor Current spikes from 26 A → ~41 A (ALARM) — collision signature',
      'Weld Force jumps from 4.5 kN → ~6.2 kN (alarm_hi = 6.5 kN)',
      'Robot01 Status immediately changes to ESTOP',
      'Body Shop KPI OEE collapses to ~15% — the highest-impact fault in the demo',
      'Robots 02 and 03 continue but cannot compensate for Robot01',
    ],
    whatItShows: [
      'Safety-critical E-Stop event published to UNS in real time (<100ms)',
      'How the KUKA KRC5 safety controller data integrates via MQTT OPC-UA bridge',
      'Dramatic OEE collapse — best scenario to demonstrate production impact',
      'Partial cell operation — showing that UNS enables granular status visibility',
    ],
    demoScript: [
      { step: '1', title: 'Set the stakes', text: 'Say: "An E-Stop in the body shop is the most serious production event outside a fire alarm. Every second costs money and the root cause investigation can take 30+ minutes without good data." Click the scenario.' },
      { step: '2', title: 'Show the E-Stop', text: 'Filter to Ingolstadt / BodyShop. Robot01 Status = ESTOP. Motor Current is ALARM. Say: "The KUKA controller published this event 80 milliseconds after the E-Stop was triggered. It is already on the UNS bus."' },
      { step: '3', title: 'Show the OEE impact', text: 'Open the Body Shop KPI stream. OEE = ~15%. Say: "This is the most dramatic KPI drop in the entire demo. In a connected plant, the production manager gets a push notification before they even hear the alarm siren."' },
      { step: '4', title: 'Tie back to UNS value', text: 'Say: "Root cause used to take 45 minutes of log file analysis. With UNS, the exact timestamp, joint current, weld force and robot status are all available in one MQTT payload. Investigation takes 5 minutes." Show the live feed.' },
    ],
  },

  cross_site_erp_disruption: {
    title: 'Cross-Site ERP Disruption',
    subtitle: 'All Locations — SAP S/4HANA',
    icon: 'fa-server',
    iconColor: 'text-red-400',
    badge: 'SYSTEM OUTAGE',
    badgeColor: 'bg-red-950/80 text-red-200 border-red-600',
    overview: `A SAP S/4HANA disruption is affecting production order publishing across
all three sites. The IBM MQ bridge that translates ERP events to MQTT topics
has lost connectivity. Production orders for Frankfurt, Munich and Ingolstadt
are no longer being updated on the UNS.

All PLC, MES and SCADA streams continue normally — only ERP-sourced topics
are affected. This demonstrates the resilience of a well-designed UNS:
plant-floor operations continue independently of ERP availability.`,
    howItWorks: [
      'ERP source streams stop publishing (FR-ERP-ORDER, MU-ERP-ORDER, IN-ERP-ORDER, FR-ERP-MATERIAL)',
      'All PLC, MES and SCADA streams across all three plants continue normally',
      'Affected streams show no new last_ts updates — last value is stale',
      'Demonstrates UNS isolation of concerns: ERP disruption does not cascade to plant floor',
    ],
    whatItShows: [
      'Cross-site impact of a single system failure — visible across all three locations at once',
      'UNS resilience: ISA-95 Level 2/3 data is independent of Level 4 (ERP)',
      'Which streams are ERP-sourced vs PLC/MES — filter by source type to show isolation',
      'How UNS enables graceful degradation vs hard dependencies',
    ],
    demoScript: [
      { step: '1', title: 'Set the context', text: 'Say: "What happens when SAP goes down? In a traditional integration architecture, the answer is: chaos. In a UNS, it is a planned degradation." Click the scenario.' },
      { step: '2', title: 'Show affected streams', text: 'Filter by Source = ERP. Show the four affected production order streams across all three sites. Their values stop updating. Say: "Only ERP topics are affected — nothing else changes."' },
      { step: '3', title: 'Show continuity', text: 'Remove the ERP filter. Show all PLC and MES streams still publishing normally. Say: "The machines are still running. The operators are still working. Only the management reporting layer is impacted."' },
      { step: '4', title: 'Make the architecture point', text: 'Say: "In a point-to-point integration, an SAP outage takes down 12 direct integrations. In UNS, the SAP connector is just one publisher. Everything else is completely decoupled. This is why ISA-95 UNS is the right architecture."' },
    ],
  },
}

const TAB_ICONS = {
  overview: 'fa-circle-info',
  signals:  'fa-wave-square',
  demo:     'fa-person-chalkboard',
}

export default function ScenarioModal({ scenario, onClose }) {
  const guide = SCENARIO_GUIDE[scenario?.id]
  const overlayRef = useRef(null)
  const [tab, setTab] = useState('overview')

  // reset tab on scenario change
  useEffect(() => { setTab('overview') }, [scenario?.id])

  // close on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  if (!scenario || !guide) return null

  return (
    <div
      ref={overlayRef}
      onClick={(e) => e.target === overlayRef.current && onClose()}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
    >
      <div className="w-full max-w-2xl bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl flex flex-col max-h-[90vh] overflow-hidden">

        {/* Header */}
        <div className="flex items-start gap-4 p-5 border-b border-gray-800">
          <div className="flex-shrink-0 w-10 h-10 rounded-xl bg-gray-800 flex items-center justify-center">
            <i className={`fa-solid ${guide.icon} ${guide.iconColor} text-lg`} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-white font-bold text-base leading-tight">{guide.title}</h2>
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${guide.badgeColor}`}>
                {guide.badge}
              </span>
            </div>
            <div className="text-gray-500 text-xs mt-0.5">{guide.subtitle}</div>
          </div>
          <button
            onClick={onClose}
            className="flex-shrink-0 w-8 h-8 rounded-lg bg-gray-800 hover:bg-gray-700 flex items-center justify-center text-gray-400 hover:text-white transition-colors"
          >
            <i className="fa-solid fa-xmark text-sm" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-800 px-5">
          {[
            { key: 'overview', label: 'Overview'  },
            { key: 'signals',  label: 'Signals'   },
            { key: 'demo',     label: 'Demo Guide' },
          ].map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={clsx(
                'flex items-center gap-1.5 px-3 py-3 text-xs font-medium border-b-2 transition-colors -mb-px',
                tab === key
                  ? 'border-brand-400 text-white'
                  : 'border-transparent text-gray-500 hover:text-gray-300'
              )}
            >
              <i className={`fa-solid ${TAB_ICONS[key]} text-[10px]`} />
              {label}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5">

          {tab === 'overview' && (
            <div className="space-y-4">
              <p className="text-gray-300 text-sm leading-relaxed whitespace-pre-line">
                {guide.overview}
              </p>
              {guide.whatItShows && (
                <div>
                  <div className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-2">What this demo shows</div>
                  <ul className="space-y-1.5">
                    {guide.whatItShows.map((item, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-gray-300">
                        <i className="fa-solid fa-circle-dot text-brand-400 text-[10px] mt-1.5 flex-shrink-0" />
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {tab === 'signals' && (
            <div className="space-y-2">
              <div className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-3">
                How the fault is simulated
              </div>
              {guide.howItWorks.map((item, i) => (
                <div key={i} className="flex items-start gap-3 bg-gray-800/60 rounded-lg px-3 py-2.5">
                  <div className="flex-shrink-0 w-5 h-5 rounded-full bg-brand-900 border border-brand-700 flex items-center justify-center">
                    <span className="text-[9px] font-bold text-brand-300">{i + 1}</span>
                  </div>
                  <p className="text-sm text-gray-300 leading-relaxed">{item}</p>
                </div>
              ))}
              {scenario.affected?.length > 0 && (
                <div className="mt-4">
                  <div className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-2">Affected stream IDs</div>
                  <div className="flex flex-wrap gap-1.5">
                    {scenario.affected.map((id) => (
                      <span key={id} className="text-[10px] font-mono bg-gray-800 text-gray-400 px-2 py-1 rounded border border-gray-700">
                        {id}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {tab === 'demo' && (
            <div className="space-y-3">
              <div className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-3">
                Step-by-step demo script
              </div>
              {guide.demoScript.map(({ step, title, text }) => (
                <div key={step} className="flex gap-3">
                  <div className="flex-shrink-0 w-7 h-7 rounded-full bg-brand-600 flex items-center justify-center">
                    <span className="text-[11px] font-bold text-white">{step}</span>
                  </div>
                  <div className="flex-1 bg-gray-800/50 rounded-xl px-4 py-3 border border-gray-700/50">
                    <div className="text-xs font-semibold text-white mb-1">{title}</div>
                    <p className="text-xs text-gray-400 leading-relaxed">{text}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

        </div>

        {/* Footer */}
        <div className="border-t border-gray-800 px-5 py-3 flex items-center justify-between">
          <div className="text-[10px] text-gray-600">
            <i className="fa-solid fa-keyboard mr-1.5" />
            Press <kbd className="px-1.5 py-0.5 bg-gray-800 rounded text-gray-400 font-mono">Esc</kbd> to close
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-brand-600 hover:bg-brand-700 text-white text-xs font-semibold rounded-lg transition-colors"
          >
            Close & Activate Scenario
          </button>
        </div>

      </div>
    </div>
  )
}
