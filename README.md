# Aurora UNS Simulator

Advanced, physics-based factory simulator for the Aurora Industries Battery Case Plant.
Publishes realistic MQTT data to all 73+ UNS topics with configurable fault injection.

## Quick start (local Mosquitto)

```bash
# 1. Install dependencies
cd uns-simulator
uv sync   # or: pip install paho-mqtt python-dotenv pyyaml

# 2. Copy env
cp .env.example .env
# Edit .env — set MQTT_HOST if not localhost

# 3. Run
uv run python -m src.main
# or:
python -m src.main --config config/factory.yaml
```

## What gets published

| Category     | Topics | Interval |
|-------------|--------|---------|
| Telemetry    | 29     | 5s      |
| Performance  | 3      | 30s     |
| Energy       | 10     | 30s     |
| Health       | 3      | 30s     |
| Alarms       | 13+    | 60s     |
| Process steps| 8      | 15s     |
| Batch events | —      | ~5 min  |

## Fault injection

Faults fire randomly (~15% probability per asset per hour by default).
Each fault modifies telemetry (e.g. pressure drops, temperature rises),
raises a structured alarm, and auto-recovers after 5 minutes.

Override in `config/factory.yaml`:
```yaml
simulation:
  fault_probability_per_hour: 0.05   # quieter demo
  recovery_time_s: 120               # faster recovery
```

## MES commands

Send to `aurora/<line>/mes/commands/line_start` or `line_stop` to
start/stop all assets on a line. The simulator ACKs on `aurora/<line>/mes/ack/<cmd_id>`.

## DPP trigger

Every ~5 minutes a batch-complete event fires on:
`aurora/line_04_inspection/cell_02/process/step_status`
with `result=pass` — this is the signal for the DPP generation pipeline.
