from __future__ import annotations

import sys
import time
from typing import NamedTuple, Optional

try:
    import usb.core
    import usb.util
except ImportError:
    usb = None

# REED R8080 identifiers (Holtek Semiconductor)
R8080_VENDOR_ID = 0x04D9
R8080_PRODUCT_ID = 0xE000


class SPLReading(NamedTuple):
    db: float
    weighting: str  # "dBA" or "dBC"
    speed: str      # "Fast" or "Slow"
    range: str      # "30-130", "30-80", "50-100", "60-130"


class R8080Device:
    """
    REED R8080 Sound Level Meter driver.

    Protocol discovered by reverse engineering HTUSB.dll:
    - Commands use STX/ETX framing: [0x02, CMD, D1, D2, D3, D4, 0x03]
    - HTUSB WriteCmd header sent via SET_REPORT(Output): [0x43, 0x01, len, 0, 0, 0, 0, 0]
    - Command data sent on Interrupt OUT with length prefix: [count, data...]
    - HTUSB ReadData header: [0x43, 0x04, len, 0, 0, 0, 0, 0]
    - Response read from Interrupt IN: [count, data...]
    - Acquire command ('A' = 0x41) returns live measurement
    - dB value = (response[5] * 256 + response[6]) / 10.0
    """

    EP_IN = 0x81
    EP_OUT = 0x02

    MAX_CONSECUTIVE_FAILURES = 5

    # Status flags in response data[1]
    FLAG_DBA = 0x08   # bit 3: 1=dBA, 0=dBC
    FLAG_FAST = 0x10  # bit 4: 1=Fast, 0=Slow

    # Range codes in response data[3]
    RANGE_MAP = {
        0x88: "30-130",
        0x11: "30-90",
        0x22: "50-110",
        0x44: "70-130",
    }

    def __init__(self, logger):
        self.dev = None
        self.logger = logger
        self._consecutive_failures = 0

    def connect(self):
        self.dev = usb.core.find(idVendor=R8080_VENDOR_ID, idProduct=R8080_PRODUCT_ID)
        if not self.dev:
            raise RuntimeError("R8080 not found")
        try:
            if self.dev.is_kernel_driver_active(0):
                self.dev.detach_kernel_driver(0)
        except Exception:
            pass
        self.dev.set_configuration()

    def _drain(self):
        while True:
            try:
                self.dev.read(self.EP_IN, 32, timeout=100)
            except Exception:
                break

    def _send_header(self, cmd_type, length):
        self.dev.ctrl_transfer(
            0x21, 0x09, 0x0200, 0,
            bytes([0x43, cmd_type, length & 0xFF, (length >> 8) & 0xFF, 0, 0, 0, 0]),
            timeout=1000,
        )

    def _reset(self):
        self.dev.reset()
        time.sleep(0.6)
        self.connect()

    def record_failure(self) -> bool:
        """Record a failed read. Returns True if a USB reset was performed."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
            self.logger.warning(
                f"{self._consecutive_failures} consecutive failures, resetting USB device"
            )
            try:
                self._reset()
                self._consecutive_failures = 0
                return True
            except Exception as exc:
                self.logger.error(f"USB reset failed: {exc}")
        return False

    def send_command(self, cmd_data: bytes) -> Optional[bytes]:
        """Send a framed command and return the response payload, or None."""
        try:
            self._send_header(0x01, len(cmd_data))
        except Exception:
            pass

        self.dev.write(self.EP_OUT, bytes([len(cmd_data)]) + cmd_data, timeout=1000)
        self._drain()

        try:
            self._send_header(0x04, 32)
        except Exception:
            pass

        for _ in range(5):
            try:
                raw = bytes(self.dev.read(self.EP_IN, 32, timeout=1500))
                cnt = raw[0]
                return raw[1:cnt + 1]
            except usb.core.USBError:
                time.sleep(0.1)
        return None

    def toggle_weighting(self) -> Optional[str]:
        """Toggle dBA/dBC weighting. Returns the new weighting or None on failure."""
        cmd = bytes([0x02, 0x43, 0x00, 0x00, 0x00, 0x00, 0x03])
        self.send_command(cmd)
        # Read back current state with an Acquire
        reading = self.read_spl()
        if reading:
            return reading.weighting
        return None

    def toggle_range(self) -> Optional[str]:
        """Cycle to next range (30-130 -> 30-80 -> 50-100 -> 60-130). Returns new range or None."""
        cmd = bytes([0x02, 0x4C, 0x00, 0x00, 0x00, 0x00, 0x03])
        self.send_command(cmd)
        reading = self.read_spl()
        if reading:
            return reading.range
        return None

    def toggle_speed(self) -> Optional[str]:
        """Toggle Fast/Slow response speed. Returns the new speed or None on failure."""
        cmd = bytes([0x02, 0x46, 0x00, 0x00, 0x00, 0x00, 0x03])
        self.send_command(cmd)
        reading = self.read_spl()
        if reading:
            return reading.speed
        return None

    def erase_memory(self) -> bool:
        """Erase stored memory. Returns True if device echoed confirmation."""
        erase_cmd = bytes([0x02]) + b'erase' + bytes([0x03])
        resp = self.send_command(erase_cmd)
        return resp is not None and resp[0:7] == erase_cmd

    def read_spl(self) -> Optional[SPLReading]:
        """Read current dB level and weighting from the R8080. Returns SPLReading or None."""
        try:
            cmd = bytes([0x02, 0x41, 0x00, 0x00, 0x00, 0x00, 0x03])
            data = self.send_command(cmd)
            if data and len(data) > 6:
                db_val = (data[5] * 256 + data[6]) / 10.0
                weighting = "dBA" if (data[1] & self.FLAG_DBA) else "dBC"
                speed = "Fast" if (data[1] & self.FLAG_FAST) else "Slow"
                range_str = self.RANGE_MAP.get(data[3], f"unknown(0x{data[3]:02x})")
                self._consecutive_failures = 0
                return SPLReading(round(db_val, 1), weighting, speed, range_str)
            return None
        except Exception as exc:
            self.logger.warning(f"R8080 read failed: {exc}")
            return None


def connect(logger) -> R8080Device:
    """Connect to the R8080 and return the device. Exits if not found."""
    if usb is None:
        logger.error("pyusb is not installed. Cannot read R8080.")
        sys.exit(1)

    dev = R8080Device(logger)
    try:
        dev.connect()
        logger.info(f"REED R8080 connected (VID=0x{R8080_VENDOR_ID:04X}, PID=0x{R8080_PRODUCT_ID:04X})")
        return dev
    except Exception as exc:
        logger.error(f"R8080 not found: {exc}")
        sys.exit(1)
