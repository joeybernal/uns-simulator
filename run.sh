#!/bin/bash
cd "$(dirname "$0")"
if [ ! -d venv ]; then
  echo "Creating venv..."
  python3 -m venv venv
fi
./venv/bin/pip install -r requirements.txt -q
echo ""
echo "  UNS Simulator — IoTAuto GmbH Frankfurt Paint Shop"
echo "  Dashboard: http://localhost:8080"
echo "  MQTT:      mqtt.iotdemozone.com:1883"
echo ""
./venv/bin/python simulator.py
