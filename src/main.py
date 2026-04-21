"""
Aurora UNS Simulator — entry point
Usage:
  uv run python -m src.main
  uv run python -m src.main --config config/factory.yaml
  MQTT_HOST=broker.example.com uv run python -m src.main
"""
from __future__ import annotations
import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    stream=sys.stdout,
)

from .factory.orchestrator import FactoryOrchestrator


def main():
    parser = argparse.ArgumentParser(description="Aurora UNS Simulator")
    parser.add_argument("--config", default="config/factory.yaml",
                        help="Path to factory config YAML (default: config/factory.yaml)")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        # try relative to this file
        config_path = Path(__file__).parent.parent / args.config
    if not config_path.exists():
        print(f"ERROR: config not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    orchestrator = FactoryOrchestrator(config_path)
    orchestrator.run()


if __name__ == "__main__":
    main()
