#!/usr/bin/env python3
"""
Cycle measurement range on the REED R8080.

Protocol confirmed via Wireshark USB capture of official R8080.exe software:
  - Toggle command: STX 'L' 0 0 0 0 ETX  (07 02 4c 00 00 00 00 03)
  - Cycles: 30-130 -> 30-90 -> 50-110 -> 70-130 -> 30-130

Usage: python3 toggle_range.py
"""
from __future__ import annotations

import logging

from usb_reader import connect

logger = logging.getLogger("toggle_range")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main():
    dev = connect(logger)

    # Read current state
    reading = dev.read_spl()
    if reading:
        logger.info(f"Current: {reading.db} {reading.weighting} {reading.speed} range={reading.range}")
    else:
        logger.warning("Could not read current state")

    # Toggle
    logger.info("Sending range toggle command...")
    new_range = dev.toggle_range()

    if new_range:
        logger.info(f"Range changed to: {new_range}")
    else:
        logger.warning("Toggle sent but could not confirm new range")


if __name__ == "__main__":
    main()
