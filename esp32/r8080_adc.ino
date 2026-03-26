/*
 * REED R8080 DC Output → InfluxDB via ESP32 + ADS1115
 *
 * Reads the R8080's DC analog output (10mV/dB) through an ADS1115 16-bit ADC
 * and posts readings to InfluxDB over WiFi.
 *
 * Wiring:
 *   R8080 3.5mm tip   → ADS1115 A0
 *   R8080 3.5mm sleeve → GND
 *   ADS1115 SDA        → ESP32 GPIO 21
 *   ADS1115 SCL        → ESP32 GPIO 22
 *   ADS1115 VDD        → 3.3V
 *   ADS1115 GND        → GND
 *   ADS1115 ADDR       → GND (address 0x48)
 *
 * Libraries needed (install via Arduino Library Manager):
 *   - Adafruit ADS1X15
 *   - Adafruit BusIO
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_ADS1X15.h>

// ---- CONFIGURATION ---- //
const char* WIFI_SSID     = "YOUR_SSID";
const char* WIFI_PASSWORD = "YOUR_PASSWORD";

// InfluxDB endpoint — use your PC's LAN IP, not localhost
const char* INFLUXDB_URL  = "http://YOUR_PC_IP:9186/write?db=r8080";

// Minimum dB to log (matches your Python bridge threshold)
const float DB_THRESHOLD  = 65.0;

// How often to read and post (milliseconds)
const unsigned long POLL_INTERVAL_MS = 1000;

// R8080 DC output scale: 10mV per dB
const float MV_PER_DB = 10.0;
// ---- END CONFIGURATION ---- //

Adafruit_ADS1115 ads;

void setup() {
  Serial.begin(115200);
  Serial.println("\nR8080 ADC Bridge starting...");

  // Init ADS1115
  Wire.begin();
  if (!ads.begin()) {
    Serial.println("ERROR: ADS1115 not found. Check wiring.");
    while (1) delay(1000);
  }
  // Gain 1x = ±4.096V range, LSB = 0.125mV — good for 0-1.3V from R8080
  ads.setGain(GAIN_ONE);
  Serial.println("ADS1115 initialized (gain 1x, ±4.096V)");

  // Connect WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nConnected! IP: %s\n", WiFi.localIP().toString().c_str());
}

float readDB() {
  int16_t raw = ads.readADC_SingleEnded(0);
  // With GAIN_ONE, each LSB = 0.125mV
  float voltage_mv = raw * 0.125;
  float db = voltage_mv / MV_PER_DB;
  return db;
}

void writeInflux(float db) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected, skipping write");
    return;
  }

  HTTPClient http;
  http.begin(INFLUXDB_URL);
  http.addHeader("Content-Type", "text/plain");

  char body[64];
  snprintf(body, sizeof(body), "spl,sensor=r8080 db=%.1f", db);

  int code = http.POST(body);
  if (code != 204 && code != 200) {
    Serial.printf("InfluxDB error: %d\n", code);
  }
  http.end();
}

void loop() {
  unsigned long start = millis();

  float db = readDB();

  // Simple sanity check: R8080 range is 30-130 dB
  if (db >= 20.0 && db <= 140.0) {
    int bar_len = (int)(db - 30);
    if (bar_len < 0) bar_len = 0;
    if (bar_len > 100) bar_len = 100;

    if (db >= DB_THRESHOLD) {
      writeInflux(db);
      Serial.printf("%.1f dB  [logged]\n", db);
    } else {
      Serial.printf("%.1f dB  (below threshold)\n", db);
    }
  } else {
    Serial.printf("%.1f dB  (out of range, skipping)\n", db);
  }

  unsigned long elapsed = millis() - start;
  if (elapsed < POLL_INTERVAL_MS) {
    delay(POLL_INTERVAL_MS - elapsed);
  }
}
