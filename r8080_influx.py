#!/usr/bin/env python3
"""
REED R8080 → InfluxDB bridge.
Reads live dB from the R8080 and writes to InfluxDB line protocol over HTTP.
"""
import argparse
import time
import datetime
import urllib.request
import urllib.error

from usb_reader import connect
import logging

INFLUXDB_URL = "http://localhost:9186/write?db=r8080"
POLL_INTERVAL = 1  # seconds between reads (R8080 cycle takes ~1s)
DEFAULT_DB_THRESHOLD = 65  # minimum dB to log (set to 0 to log everything)

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
    parser = argparse.ArgumentParser(description="REED R8080 → InfluxDB bridge")
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_DB_THRESHOLD,
        help="Only log readings above this dB level (default: 0 = log everything)",
    )
    args = parser.parse_args()

    threshold = args.threshold
    logger.info("REED R8080 -> InfluxDB bridge starting")
    logger.info(f"InfluxDB endpoint: {INFLUXDB_URL}")
    if threshold > 0:
        logger.info(f"Threshold: only logging readings above {threshold:.1f} dB")

    dev = connect(logger)

    reading_count = 0
    skipped_count = 0
    try:
        while True:
            db = dev.read_spl()
            now = datetime.datetime.now().strftime("%H:%M:%S")
            if db is not None:
                bar = "#" * int(max(0, db - 30))
                if db >= threshold:
                    write_influx(db)
                    reading_count += 1
                    print(f"  {now}  {db:5.1f} dB  {bar}  [#{reading_count}]", flush=True)
                else:
                    skipped_count += 1
                    print(f"  {now}  {db:5.1f} dB  {bar}  (below threshold)", flush=True)
            else:
                print(f"  {now}  -- no reading --", flush=True)
    except KeyboardInterrupt:
        logger.info(f"Stopped. {reading_count} readings logged, {skipped_count} below threshold.")


if __name__ == "__main__":
    main()
