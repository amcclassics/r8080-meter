#!/usr/bin/env python3
"""
Toggle dBA/dBC weighting on the REED R8080.

Protocol confirmed via Wireshark USB capture of official R8080.exe software:
  - Toggle command: STX 'C' 0 0 0 0 ETX  (07 02 43 00 00 00 00 03)
  - Each send toggles between dBA and dBC

Usage: python3 toggle_weighting.py
"""
from __future__ import annotations

import logging

from usb_reader import connect

logger = logging.getLogger("toggle_weighting")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main():
    dev = connect(logger)

    # Read current weighting
    reading = dev.read_spl()
    if reading:
        logger.info(f"Current weighting: {reading.weighting} ({reading.db} dB)")
    else:
        logger.warning("Could not read current state")

    # Toggle
    logger.info("Sending toggle command...")
    new_weighting = dev.toggle_weighting()

    if new_weighting:
        logger.info(f"Weighting changed to: {new_weighting}")
    else:
        logger.warning("Toggle sent but could not confirm new weighting")


if __name__ == "__main__":
    main()
