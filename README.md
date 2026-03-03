# r8080-meter

Linux driver and Grafana dashboard for the **REED R8080** USB sound level meter.

Reads live dB SPL from the meter over USB, streams it into InfluxDB, and displays it on a pre-built Grafana dashboard with a gauge, time series, peak bars, and statistics. Optionally publishes to Home Assistant via MQTT.

![Dashboard screenshot](docs/screenshot.png)
<!-- TODO: add actual screenshot -->

## Hardware

- [REED R8080](https://www.reedinstruments.com/product/r8080-sound-level-meter-with-usb) sound level meter (USB HID, Holtek chipset)
- Any Linux machine with a USB port

## Quick start

### 1. Install the udev rule (USB permissions)

```bash
sudo cp 99-decibel-meter.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Unplug and replug the meter after this step.

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Start InfluxDB + Grafana

```bash
docker compose up -d
```

This starts:
- **InfluxDB 1.8** on port `9186` (mapped from 8086)
- **Grafana** on port `9100` (mapped from 3000), anonymous read access enabled

The Grafana dashboard is auto-provisioned — no manual setup needed.

### 4. Run the bridge

```bash
python3 r8080_influx.py
```

You should see live readings in the terminal:

```
  14:32:01   52.3 dB  ######################  [#1]
  14:32:03   48.7 dB  ##################  [#2]
```

To only log sounds above a certain level (reduces InfluxDB storage):

```bash
python3 r8080_influx.py --threshold 65
```

Readings below the threshold are still displayed in the terminal but not written to InfluxDB.

### 5. (Optional) Home Assistant via MQTT

To also publish readings to Home Assistant, pass your MQTT broker details:

```bash
python3 r8080_influx.py --threshold 65 \
  --mqtt-broker homeassistant.local \
  --mqtt-user YOUR_MQTT_USER \
  --mqtt-password YOUR_MQTT_PASSWORD
```

**Prerequisites on the Home Assistant side:**

1. Install the **Mosquitto broker** add-on (Settings → Add-ons → Mosquitto broker)
2. Create an MQTT user (Settings → People → Users → Add User), or use an existing one
3. Enable the **MQTT integration** (Settings → Devices & Services → Add Integration → MQTT)

Once the script connects, a sensor called **`sensor.r8080_sound_level`** will auto-appear in Home Assistant via MQTT discovery. It includes full device info (manufacturer, model) and supports history graphs out of the box.

| Option | Default | Description |
|--------|---------|-------------|
| `--mqtt-broker` | *(disabled)* | MQTT broker hostname. Omit to run without MQTT. |
| `--mqtt-port` | `1883` | MQTT broker port |
| `--mqtt-user` | *(none)* | MQTT username |
| `--mqtt-password` | *(none)* | MQTT password |

MQTT is fully optional — if omitted or if the broker is unreachable, the script continues logging to InfluxDB as usual.

#### Email alerts

To receive email notifications when the sound level exceeds a threshold, add an SMTP notifier to your Home Assistant `configuration.yaml` (edit via Settings → Add-ons → File Editor):

```yaml
notify:
  - name: email_alert
    platform: smtp
    server: smtp.gmail.com       # or your mail provider
    port: 587
    sender: your_email@gmail.com
    recipient: recipient@example.com
    username: your_email@gmail.com
    password: your_app_password   # use an App Password, not your real password
    encryption: starttls
```

Restart Home Assistant after saving. Then create an automation (Settings → Automations → Create Automation), or add to `automations.yaml`:

```yaml
- alias: "Loud noise email alert"
  trigger:
    - platform: numeric_state
      entity_id: sensor.r8080_sound_level
      above: 85
  condition: []
  action:
    - service: notify.email_alert
      data:
        title: "Noise Alert"
        message: "Sound level reached {{ states('sensor.r8080_sound_level') }} dB"
```

### 6. View the Grafana dashboard

Open [http://localhost:9100](http://localhost:9100) in your browser. The **REED R8080 Sound Level Meter** dashboard appears automatically.

Default Grafana credentials: `admin` / `r8080` (anonymous viewing is also enabled).

## Project structure

```
r8080-meter/
├── docker-compose.yml          # InfluxDB 1.8 + Grafana
├── grafana/provisioning/       # Auto-configured datasource + dashboard
├── r8080_influx.py             # Bridge: reads R8080 → writes InfluxDB
├── usb_reader.py               # R8080 USB driver
├── 99-decibel-meter.rules      # udev rule for USB permissions
└── requirements.txt            # pyusb, paho-mqtt
```

## Protocol documentation

The R8080 uses a Holtek HID chipset. The protocol was reverse engineered from `HTUSB.dll` (the Windows driver). Key findings:

### USB identifiers

| Field | Value |
|-------|-------|
| Vendor ID | `0x04D9` (Holtek Semiconductor) |
| Product ID | `0xE000` |
| Interface | HID |
| Endpoint IN | `0x81` (Interrupt) |
| Endpoint OUT | `0x02` (Interrupt) |

### HTUSB command framing

Commands use STX/ETX framing:

```
[0x02, CMD, D1, D2, D3, D4, 0x03]
```

The host communicates via two phases:

1. **WriteCmd** — Send a SET_REPORT control transfer with header `[0x43, 0x01, len_lo, len_hi, 0, 0, 0, 0]`, then write the command on the Interrupt OUT endpoint with a length prefix byte.

2. **ReadData** — Send a SET_REPORT control transfer with header `[0x43, 0x04, len_lo, len_hi, 0, 0, 0, 0]`, then read from Interrupt IN. The first byte is a count; payload follows.

### Acquire command

The "Acquire" command (`CMD = 0x41 = 'A'`) requests a live measurement:

```
Write: [0x07, 0x02, 0x41, 0x00, 0x00, 0x00, 0x00, 0x03]
              STX   'A'                           ETX
```

Response payload (after length byte):

```
[STX, status?, flags?, flags?, flags?, dB_hi, dB_lo, ETX]
```

**dB value** = `(response[5] * 256 + response[6]) / 10.0`

### Read cycle

Each read requires a full USB reset cycle (~600ms) to avoid STALL errors on subsequent commands. The complete cycle takes roughly 1 second, giving ~1 reading/sec.

### Quirks

- The WriteCmd SET_REPORT may STALL on the second cycle — this is expected and can be caught/ignored.
- A full `usb.core.Device.reset()` between reads is required for reliable operation.
- The device must be detached from the kernel HID driver before use.

## Troubleshooting

**"R8080 not found"** — Check that the meter is plugged in and turned on. Run `lsusb | grep 04d9` to verify it's detected. Make sure the udev rule is installed.

**Permission denied** — The udev rule sets `MODE="0666"` so any user can access the device. Replug the meter after installing the rule, or run with `sudo`.

**No data in Grafana** — Verify InfluxDB is running (`curl http://localhost:9186/ping`). Check that `r8080_influx.py` is printing readings to the terminal.

## License

MIT
