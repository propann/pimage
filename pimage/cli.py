from __future__ import annotations

import argparse
import logging
from pathlib import Path

from pimage.config import ConfigError, load_config
from pimage.logging_utils import setup_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="pimage camera app")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--check-config", action="store_true", help="Validate config and exit")
    args = parser.parse_args()

    log_file = setup_logging(Path("logs"), debug=args.debug)
    logger = logging.getLogger("pimage")
    logger.info("Logging initialized at %s", log_file)

    try:
        config = load_config()
    except ConfigError as exc:
        logger.error("Invalid configuration: %s", exc)
        return 2

    if args.check_config:
        logger.info("Configuration valid: %s", config)
        return 0

    from app_photo import main as app_main

    return app_main()
