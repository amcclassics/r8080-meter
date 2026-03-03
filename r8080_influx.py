#!/usr/bin/env python3
"""
REED R8080 → InfluxDB bridge.
Reads live dB from the R8080 and writes to InfluxDB line protocol over HTTP.
Optionally publishes to MQTT for Home Assistant integration.
"""
import argparse
import json
import time
import datetime
import urllib.request
import urllib.error

from usb_reader import connect
import logging

INFLUXDB_URL = "http://localhost:9186/write?db=r8080"
POLL_INTERVAL = 1  # seconds between reads (R8080 cycle takes ~1s)
DEFAULT_DB_THRESHOLD = 65  # minimum dB to log (set to 0 to log everything)

MQTT_DISCOVERY_TOPIC = "homeassistant/sensor/r8080_spl/config"
MQTT_STATE_TOPIC = "r8080/spl/state"

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


def connect_mqtt(broker: str, port: int, user: str | None, password: str | None):
    """Connect to MQTT broker and publish HA discovery config. Returns client or None on failure."""
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        logger.error("paho-mqtt not installed. Run: pip install paho-mqtt")
        return None

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="r8080-meter")
    if user:
        client.username_pw_set(user, password)

    discovery_payload = json.dumps({
        "name": "R8080 Sound Level",
        "state_topic": MQTT_STATE_TOPIC,
        "unit_of_measurement": "dB",
        "device_class": "sound_pressure",
        "state_class": "measurement",
        "unique_id": "r8080_sound_level",
        "icon": "mdi:volume-high",
        "device": {
            "identifiers": ["r8080_meter"],
            "name": "REED R8080",
            "manufacturer": "REED Instruments",
            "model": "R8080",
        },
    })

    try:
        client.will_set(MQTT_STATE_TOPIC, payload="", retain=True)
        client.connect(broker, port)
        client.loop_start()
        client.publish(MQTT_DISCOVERY_TOPIC, payload=discovery_payload, retain=True)
        logger.info(f"MQTT discovery published to {broker}:{port}")
        return client
    except Exception as e:
        logger.warning(f"MQTT connection failed: {e} — continuing without MQTT")
        return None


def publish_mqtt(client, db_value: float):
    """Publish a dB reading to MQTT."""
    try:
        client.publish(MQTT_STATE_TOPIC, payload=f"{db_value:.1f}", retain=True)
    except Exception as e:
        logger.warning(f"MQTT publish failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="REED R8080 → InfluxDB bridge")
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_DB_THRESHOLD,
        help="Only log readings above this dB level (default: 65)",
    )
    parser.add_argument(
        "--mqtt-broker", type=str, default=None,
        help="MQTT broker hostname (e.g. homeassistant.local). Omit to disable MQTT.",
    )
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port (default: 1883)")
    parser.add_argument("--mqtt-user", type=str, default=None, help="MQTT username")
    parser.add_argument("--mqtt-password", type=str, default=None, help="MQTT password")
    args = parser.parse_args()

    threshold = args.threshold
    logger.info("REED R8080 -> InfluxDB bridge starting")
    logger.info(f"InfluxDB endpoint: {INFLUXDB_URL}")
    if threshold > 0:
        logger.info(f"Threshold: only logging readings above {threshold:.1f} dB")

    # Optional MQTT connection
    mqtt_client = None
    if args.mqtt_broker:
        mqtt_client = connect_mqtt(args.mqtt_broker, args.mqtt_port, args.mqtt_user, args.mqtt_password)
    else:
        logger.info("MQTT disabled (use --mqtt-broker to enable)")

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
                    if mqtt_client:
                        publish_mqtt(mqtt_client, db)
                    reading_count += 1
                    print(f"  {now}  {db:5.1f} dB  {bar}  [#{reading_count}]", flush=True)
                else:
                    skipped_count += 1
                    print(f"  {now}  {db:5.1f} dB  {bar}  (below threshold)", flush=True)
            else:
                print(f"  {now}  -- no reading --", flush=True)
    except KeyboardInterrupt:
        if mqtt_client:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()
        logger.info(f"Stopped. {reading_count} readings logged, {skipped_count} below threshold.")


if __name__ == "__main__":
    main()
