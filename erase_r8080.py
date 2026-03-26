#!/usr/bin/env python3
"""
Erase stored memory on the REED R8080.

Protocol confirmed via Wireshark USB capture of official R8080.exe software:
  - Erase command: STX 'erase' ETX  (07 02 65 72 61 73 65 03)
  - Device echoes back 'erase' in response to confirm acceptance
  - No confirmation step required

Usage: python3 erase_r8080.py [--confirm]
  Without --confirm, performs a dry run (tests communication only).
"""
from __future__ import annotations

import argparse
import time
import logging

from usb_reader import connect

logger = logging.getLogger("erase_r8080")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main():
    parser = argparse.ArgumentParser(description="Erase REED R8080 stored memory")
    parser.add_argument("--confirm", action="store_true",
                        help="Actually erase (without this flag, tests communication only)")
    args = parser.parse_args()

    dev = connect(logger)

    if not args.confirm:
        logger.info("DRY RUN — testing communication only (use --confirm to erase)")
        reading = dev.read_spl()
        if reading:
            logger.info(f"Communication OK: {reading.db} {reading.weighting}")
        else:
            logger.error("Communication failed — no reading from device")
        return

    logger.warning("ERASING STORED MEMORY — this cannot be undone!")
    time.sleep(1)

    if dev.erase_memory():
        logger.info("Device echoed 'erase' — memory erased successfully.")
    else:
        logger.error("Erase may have failed — no confirmation from device.")


if __name__ == "__main__":
    main()
