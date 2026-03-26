# r8080-meter

Linux driver and Grafana dashboard for the **REED R8080** USB sound level meter.

Reads live dB SPL from the meter over USB, streams it into InfluxDB, and displays it on a pre-built Grafana dashboard with a gauge, time series, peak bars, and statistics. Optionally publishes to Home Assistant via MQTT.

![Dashboard screenshot](docs/screenshot.png)
<!-- TODO: add actual screenshot -->

## Hardware

- [REED R8080](https://www.reedinstruments.com/product/r8080-sound-level-meter-with-usb) sound level meter (USB HID, Holtek chipset)
- Any Linux machine with a USB port (or ESP32 for standalone mode — see below)

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

## ESP32 standalone mode (no PC required)

Instead of reading the R8080 over USB, you can use its 3.5mm analog DC output with an ESP32 + ADS1115 ADC. The ESP32 reads the DC voltage, converts it to dB, and posts directly to InfluxDB over WiFi. No PC, no USB driver, no power cycle issues.

### Hardware needed

- ESP32 dev board (any variant)
- ADS1115 16-bit ADC breakout board
- 3.5mm TRS breakout board or cut aux cable
- USB power source for the ESP32 (wall adapter or power bank)
- R8080 meter running on AAA batteries (or USB battery eliminators for always-on)

### Wiring

```
R8080 3.5mm jack          ADS1115            ESP32
─────────────────         ──────────         ──────
Tip (Left/signal) ──────→ A0
Sleeve (Ground)   ──────→ GND  ────────────→ GND
                          VDD  ────────────→ 3.3V
                          SDA  ────────────→ GPIO 21
                          SCL  ────────────→ GPIO 22
                          ADDR ────────────→ GND (sets I2C address 0x48)
```

The Ring (Right) pin on the TRS breakout is unused — the R8080 is mono output.

### R8080 DC output specs (from manual)

| Parameter | Value |
|-----------|-------|
| Connector | 3.5mm sub-miniature phone jack |
| DC scale | 10mV per dB |
| AC scale | 1 Vrms at full scale of selected range |
| Voltage at 30 dB | 300 mV |
| Voltage at 130 dB | 1300 mV (1.3V) |

The ADS1115 at gain 1x handles 0–4.096V, so the full R8080 range (0.3–1.3V) fits easily. With 16-bit resolution, each LSB = 0.125mV = 0.0125 dB precision.

### Firmware setup

1. Open `esp32/r8080_adc.ino` in Arduino IDE
2. Install libraries via Library Manager:
   - **Adafruit ADS1X15**
   - **Adafruit BusIO**
3. Edit the configuration at the top of the file:
   ```cpp
   const char* WIFI_SSID     = "YOUR_SSID";
   const char* WIFI_PASSWORD = "YOUR_PASSWORD";
   const char* INFLUXDB_URL  = "http://YOUR_PC_IP:9186/write?db=r8080";
   ```
   Use your PC's LAN IP for InfluxDB (not `localhost` — the ESP32 is on the network).
4. Select your ESP32 board and upload

### How it works

- The ESP32 reads the ADS1115 every second
- Converts voltage to dB: `dB = voltage_mV / 10.0`
- Posts to InfluxDB using the same line protocol as the USB bridge: `spl,sensor=r8080 db=XX.X`
- Readings below the threshold (default 65 dB) are printed to serial but not logged
- The existing Grafana dashboard works with no changes

### Power

- **ESP32 + ADS1115**: powered by a single USB cable (5V from any adapter or power bank)
- **R8080 meter**: runs on 4x AAA batteries (~50 hour battery life per manual)

The entire setup is PC-independent once the ESP32 is flashed and InfluxDB/Grafana are running.

## Utility scripts

| Script | Description |
|--------|-------------|
| `toggle_weighting.py` | Toggle between dBA and dBC frequency weighting |
| `toggle_speed.py` | Toggle between Fast (125ms) and Slow (1s) response |
| `toggle_range.py` | Cycle measurement range: 30-130 → 30-90 → 50-110 → 70-130 |
| `erase_r8080.py` | Erase stored data in the meter's internal memory |
| `reset_r8080.py` | Send a USB-level reset to unfreeze the meter |
| `replug_r8080.py` | Unbind/rebind the USB device on Linux (simulates replug) |
| `probe_r8080.py` | Read a single measurement (for testing connectivity) |

These scripts require the meter to be connected via USB.

## Project structure

```
r8080-meter/
├── docker-compose.yml          # InfluxDB 1.8 + Grafana
├── grafana/provisioning/       # Auto-configured datasource + dashboard
├── r8080_influx.py             # Bridge: reads R8080 → writes InfluxDB
├── usb_reader.py               # R8080 USB driver
├── esp32/r8080_adc.ino         # ESP32 firmware: DC output → InfluxDB over WiFi
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
