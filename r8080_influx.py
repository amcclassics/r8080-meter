#!/usr/bin/env python3
"""
REED R8080 → InfluxDB bridge.
Reads live dB from the R8080 and writes to InfluxDB line protocol over HTTP.
"""
import sys
import time
import datetime
import urllib.request
import urllib.error

from usb_reader import find_usb_device, read_spl_value, R8080Device
import logging

INFLUXDB_URL = "http://localhost:9186/write?db=mute"
POLL_INTERVAL = 1  # seconds between reads (R8080 cycle takes ~1s)

logger = logging.getLogger("r8080_influx")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def write_influx(db_value: float):
    """Write a single dB reading to InfluxDB using line protocol."""
    timestamp_ns = int(time.time() * 1e9)
    line = f"spl,sensor=r8080 db={db_value:.1f} {timestamp_ns}"
    data = line.encode("utf-8")
    req = urllib.request.Request(INFLUXDB_URL, data=data, method="POST")
    try:
        urllib.request.urlopen(req, timeout=5)
    except urllib.error.URLError as e:
        logger.warning(f"InfluxDB write failed: {e}")


def main():
    logger.info("REED R8080 -> InfluxDB bridge starting")
    logger.info(f"InfluxDB endpoint: {INFLUXDB_URL}")

    dev = find_usb_device(None, None, logger)
    logger.info(f"Device type: {type(dev).__name__}")

    reading_count = 0
    try:
        while True:
            db = read_spl_value(dev, logger)
            now = datetime.datetime.now().strftime("%H:%M:%S")
            if db is not None:
                write_influx(db)
                reading_count += 1
                bar = "#" * int(max(0, db - 30))
                print(f"  {now}  {db:5.1f} dB  {bar}  [#{reading_count}]", flush=True)
            else:
                print(f"  {now}  -- no reading --", flush=True)
    except KeyboardInterrupt:
        logger.info(f"Stopped. {reading_count} readings sent to InfluxDB.")


if __name__ == "__main__":
    main()
