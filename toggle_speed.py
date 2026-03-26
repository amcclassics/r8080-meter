#!/usr/bin/env python3
"""
Toggle Fast/Slow response speed on the REED R8080.

Protocol confirmed via Wireshark USB capture of official R8080.exe software:
  - Toggle command: STX 'F' 0 0 0 0 ETX  (07 02 46 00 00 00 00 03)
  - Each send toggles between Fast and Slow

Usage: python3 toggle_speed.py
"""
from __future__ import annotations

import logging

from usb_reader import connect

logger = logging.getLogger("toggle_speed")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main():
    dev = connect(logger)

    # Read current state
    reading = dev.read_spl()
    if reading:
        logger.info(f"Current: {reading.db} {reading.weighting} {reading.speed}")
    else:
        logger.warning("Could not read current state")

    # Toggle
    logger.info("Sending toggle command...")
    new_speed = dev.toggle_speed()

    if new_speed:
        logger.info(f"Speed changed to: {new_speed}")
    else:
        logger.warning("Toggle sent but could not confirm new speed")


if __name__ == "__main__":
    main()
