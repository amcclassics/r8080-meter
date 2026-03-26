#!/usr/bin/env python3
"""
Probe R8080 commands to discover what each one does.
Sends various commands found in the R8080.exe binary and logs responses.
"""
from __future__ import annotations

import sys
import time
import logging

import usb.core
import usb.util

VENDOR_ID = 0x04D9
PRODUCT_ID = 0xE000
EP_IN = 0x81
EP_OUT = 0x02

logger = logging.getLogger("probe_r8080")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def connect():
    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if not dev:
        logger.error("R8080 not found")
        sys.exit(1)
    try:
        if dev.is_kernel_driver_active(0):
            dev.detach_kernel_driver(0)
    except Exception:
        pass
    dev.set_configuration()
    logger.info("R8080 connected")
    return dev


def send_header(dev, cmd_type, length):
    dev.ctrl_transfer(
        0x21, 0x09, 0x0200, 0,
        bytes([0x43, cmd_type, length & 0xFF, (length >> 8) & 0xFF, 0, 0, 0, 0]),
        timeout=1000,
    )


def drain(dev):
    while True:
        try:
            dev.read(EP_IN, 32, timeout=100)
        except Exception:
            break


def send_command(dev, cmd_data: bytes, label: str) -> bytes | None:
    """Send a framed command and read the response."""
    logger.info(f"Sending {label}: {cmd_data.hex(' ')}")

    try:
        send_header(dev, 0x01, len(cmd_data))
    except Exception:
        pass

    payload = bytes([len(cmd_data)]) + cmd_data
    dev.write(EP_OUT, payload, timeout=1000)
    drain(dev)

    try:
        send_header(dev, 0x04, 32)
    except Exception:
        pass

    for attempt in range(5):
        try:
            raw = bytes(dev.read(EP_IN, 32, timeout=1500))
            cnt = raw[0]
            data = raw[1:cnt + 1]
            logger.info(f"  Response ({cnt} bytes): {data.hex(' ')}")
            ascii_repr = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
            logger.info(f"  ASCII: {ascii_repr}")
            return data
        except usb.core.USBError:
            time.sleep(0.1)
            continue

    logger.warning(f"  No response for {label}")
    return None


def main():
    dev = connect()

    commands = [
        ("Acquire 'A' (baseline)", bytes([0x02, 0x41, 0x00, 0x00, 0x00, 0x00, 0x03])),
        ("Command 'B'", bytes([0x02, 0x42, 0x00, 0x00, 0x00, 0x00, 0x03])),
        ("Command 'D'", bytes([0x02, 0x44, 0x00, 0x00, 0x00, 0x00, 0x03])),
        ("Command 'E'", bytes([0x02, 0x45, 0x00, 0x00, 0x00, 0x00, 0x03])),
        ("Command 'K'", bytes([0x02, 0x4B, 0x00, 0x00, 0x00, 0x00, 0x03])),
        ("Command 'L'", bytes([0x02, 0x4C, 0x00, 0x00, 0x00, 0x00, 0x03])),
        ("Command 'R'", bytes([0x02, 0x52, 0x00, 0x00, 0x00, 0x00, 0x03])),
        ("Command 'S'", bytes([0x02, 0x53, 0x00, 0x00, 0x00, 0x00, 0x03])),
        ("Literal 'boot'", bytes([0x02]) + b'boot' + bytes([0x00, 0x00, 0x03])),
        ("Literal 'erase'", bytes([0x02]) + b'erase' + bytes([0x03])),
        ("Command 'Y'", bytes([0x02, 0x59, 0x00, 0x00, 0x00, 0x00, 0x03])),
    ]

    for label, cmd in commands:
        send_command(dev, cmd, label)
        time.sleep(0.5)
        print()

    logger.info("Probe complete.")


if __name__ == "__main__":
    main()
