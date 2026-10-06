/**
 * sensor.js  –  Moisture sensor adapter for PALF-Vision AI
 *
 * ┌─────────────────────────────────────────────────────────────────┐
 * │  HARDWARE SETUP (Raspberry Pi 4 + ESP32)                        │
 * │                                                                  │
 * │  Wiring:                                                         │
 * │    Capacitive moisture sensor → ESP32 analog pin (e.g. GPIO34)  │
 * │    ESP32 → RPi 4 via USB serial  OR  WiFi (same LAN)            │
 * │                                                                  │
 * │  Communication options:                                          │
 * │                                                                  │
 * │  A) ESP32_SERIAL  (recommended for RPi)                          │
 * │     ESP32 prints readings to Serial at 115200 baud.              │
 * │     RPi backend reads /dev/ttyUSB0 and exposes /api/moisture.    │
 * │                                                                  │
 * │  B) ESP32_HTTP  (WiFi — ESP32 hosts its own tiny HTTP server)    │
 * │     ESP32 runs a WiFiServer / AsyncWebServer.                    │
 * │     Frontend calls NEXT_PUBLIC_ESP32_URL/moisture directly.      │
 * │                                                                  │
 * │  C) MOCK  (default / dev)                                        │
 * │     Returns the value manually typed by the user.                │
 * │                                                                  │
 * │  Set NEXT_PUBLIC_DEVICE_MODE in .env.local to switch.            │
 * └─────────────────────────────────────────────────────────────────┘
 */

export const DEVICE_MODE =
  process.env.NEXT_PUBLIC_DEVICE_MODE || "MOCK"; // "MOCK" | "ESP32_SERIAL" | "ESP32_HTTP"

export const ESP32_URL =
  process.env.NEXT_PUBLIC_ESP32_URL || "http://192.168.1.100"; // ESP32 IP in WiFi mode


/* ──────────────────────────────────────────────────────────────────
   ESP32 FIRMWARE REFERENCE
   ──────────────────────────────────────────────────────────────────

   Paste this into your ESP32 Arduino sketch:

   ─── Serial mode (ESP32_SERIAL) ──────────────────────────────────
   const int SENSOR_PIN = 34;   // ADC1 channel on ESP32
   const int DRY_VALUE  = 3200; // calibrate: reading in open air
   const int WET_VALUE  = 1100; // calibrate: reading submerged

   void setup() {
     Serial.begin(115200);
   }

   void loop() {
     int raw = analogRead(SENSOR_PIN);
     // Map raw ADC to 0–100 % moisture
     float moisture = map(raw, DRY_VALUE, WET_VALUE, 0, 100);
     moisture = constrain(moisture, 0, 100);
     Serial.println(moisture);   // Backend reads this line
     delay(1000);
   }
   ─────────────────────────────────────────────────────────────────

   ─── HTTP mode (ESP32_HTTP) — requires WiFi + AsyncWebServer ─────
   #include <WiFi.h>
   #include <AsyncTCP.h>
   #include <ESPAsyncWebServer.h>

   const char* ssid     = "YOUR_SSID";
   const char* password = "YOUR_PASS";
   const int   SENSOR_PIN = 34;
   const int   DRY_VALUE  = 3200;
   const int   WET_VALUE  = 1100;
   AsyncWebServer server(80);

   void setup() {
     WiFi.begin(ssid, password);
     while (WiFi.status() != WL_CONNECTED) delay(500);

     server.on("/moisture", HTTP_GET, [](AsyncWebServerRequest *req){
       int raw = analogRead(SENSOR_PIN);
       float m = constrain(map(raw, DRY_VALUE, WET_VALUE, 0, 100), 0, 100);
       req->send(200, "application/json",
                 "{\"moisture\":" + String(m, 1) + "}");
     });
     server.begin();
   }

   void loop() {}
   ─────────────────────────────────────────────────────────────────

   ─── RPi backend serial reader (ESP32_SERIAL) ────────────────────
   // backend/routes/moisture.js  (Express)
   const SerialPort = require("serialport");
   const Readline   = require("@serialport/parser-readline");
   let latestMoisture = null;

   const port   = new SerialPort("/dev/ttyUSB0", { baudRate: 115200 });
   const parser = port.pipe(new Readline({ delimiter: "\n" }));
   parser.on("data", line => {
     const v = parseFloat(line.trim());
     if (Number.isFinite(v)) latestMoisture = v;
   });

   router.get("/api/moisture", (req, res) => {
     if (latestMoisture === null)
       return res.status(503).json({ error: "No reading yet." });
     res.json({ moisture: latestMoisture });
   });
   ─────────────────────────────────────────────────────────────────
*/


/* ──────────────────────────────────────────────────────────────────
   A) ESP32_SERIAL — read via backend /api/moisture
   ────────────────────────────────────────────────────────────────── */

/**
 * Fetches the latest moisture reading from the RPi backend,
 * which in turn reads from the ESP32 over USB serial.
 *
 * ENABLE ON RASPI 4:
 *   1. Set NEXT_PUBLIC_DEVICE_MODE=ESP32_SERIAL in .env.local
 *   2. Run the backend serial reader (see firmware reference above)
 *   3. Uncomment the fetch call below
 *
 * @returns {Promise<number>} moisture percentage (0–100)
 */
export async function readFromSerial() {
  // ── UNCOMMENT ON RASPBERRY PI ──
  //
  // const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000";
  // const res = await fetch(`${apiUrl}/api/moisture`);
  // if (!res.ok) throw new Error("Could not read from moisture sensor.");
  // const data = await res.json();
  // return parseFloat(data.moisture);

  throw new Error(
    "ESP32_SERIAL mode is not yet active. " +
    "Set up the backend serial reader on the Raspberry Pi, " +
    "then uncomment the fetch call in lib/sensor.js."
  );
}


/* ──────────────────────────────────────────────────────────────────
   B) ESP32_HTTP — call the ESP32's own HTTP server directly
   ────────────────────────────────────────────────────────────────── */

/**
 * Fetches the moisture reading directly from the ESP32's HTTP server.
 * The ESP32 must be on the same LAN as the RPi / client browser.
 *
 * ENABLE:
 *   1. Set NEXT_PUBLIC_DEVICE_MODE=ESP32_HTTP in .env.local
 *   2. Set NEXT_PUBLIC_ESP32_URL=http://<esp32-ip> in .env.local
 *   3. Uncomment the fetch call below
 *
 * @returns {Promise<number>} moisture percentage (0–100)
 */
export async function readFromEsp32Http() {
  // ── UNCOMMENT WHEN ESP32 HTTP SERVER IS READY ──
  //
  // const res = await fetch(`${ESP32_URL}/moisture`, { signal: AbortSignal.timeout(3000) });
  // if (!res.ok) throw new Error("ESP32 HTTP server did not respond.");
  // const data = await res.json();
  // return parseFloat(data.moisture);

  throw new Error(
    "ESP32_HTTP mode is not yet active. " +
    "Flash the HTTP firmware to the ESP32, set NEXT_PUBLIC_ESP32_URL, " +
    "then uncomment the fetch call in lib/sensor.js."
  );
}


/* ──────────────────────────────────────────────────────────────────
   UNIFIED READ  (used by the dashboard — auto-selects mode)
   ────────────────────────────────────────────────────────────────── */

/**
 * High-level moisture read function.  The dashboard calls this.
 * Routes to the correct adapter based on NEXT_PUBLIC_DEVICE_MODE.
 *
 * In MOCK mode returns null — the UI will keep using manual input.
 *
 * @returns {Promise<number|null>}
 */
export async function readMoisture() {
  switch (DEVICE_MODE) {
    case "ESP32_SERIAL": return readFromSerial();
    case "ESP32_HTTP":   return readFromEsp32Http();
    default:             return null; // MOCK — user types value manually
  }
}

/**
 * Returns true if a real sensor is configured (not MOCK).
 * Used by the UI to show/hide the "Read from sensor" button.
 */
export const hasSensor = () => DEVICE_MODE !== "MOCK";
