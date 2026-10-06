/**
 * app/api/moisture/route.js
 *
 * Next.js App Router API route — runs server-side on the Raspberry Pi.
 * Opens a persistent USB serial connection to the ESP32 and returns
 * the latest moisture reading as JSON.
 *
 * Enabled when: NEXT_PUBLIC_DEVICE_MODE=ESP32_SERIAL in .env.local
 *
 * ESP32 firmware (paste into Arduino IDE):
 * ─────────────────────────────────────────
 *   const int SENSOR_PIN = 34;
 *   const int DRY_VALUE  = 3200;   // calibrate: open air reading
 *   const int WET_VALUE  = 1100;   // calibrate: submerged reading
 *
 *   void setup() { Serial.begin(115200); }
 *
 *   void loop() {
 *     int   raw  = analogRead(SENSOR_PIN);
 *     float pct  = constrain(map(raw, DRY_VALUE, WET_VALUE, 0, 100), 0, 100);
 *     Serial.println(pct);
 *     delay(1000);
 *   }
 * ─────────────────────────────────────────
 *
 * Find your serial port on RPi:
 *   ls /dev/ttyUSB*   or   ls /dev/ttyACM*
 */

import { NextResponse } from "next/server";

// ── Serial port configuration ─────────────────────────────────────────────
const SERIAL_PORT = process.env.SERIAL_PORT     || "/dev/ttyUSB0";
const BAUD_RATE   = Number(process.env.BAUD_RATE || 115200);

// ── Module-level singleton ────────────────────────────────────────────────
// Next.js runs as a long-lived Node process when deployed with `next start`
// (which is what PM2 uses), so module-level state persists across requests.
let latestMoisture = null;  // last valid reading from the ESP32
let portError      = null;  // last serial error (shown to user)
let serialReady    = false;

/**
 * Lazily initialise the serial port the first time this module is loaded
 * on the server.  Subsequent requests reuse the same open connection.
 */
async function initSerial() {
  if (serialReady) return;

  const deviceMode = process.env.NEXT_PUBLIC_DEVICE_MODE || "MOCK";
  if (deviceMode !== "ESP32_SERIAL") return; // don't open port in MOCK mode

  try {
    // Dynamic import so the module doesn't break on dev laptops without the
    // serialport native addon.
    const { SerialPort }  = await import("serialport");
    const { ReadlineParser } = await import("@serialport/parser-readline");

    const port   = new SerialPort({ path: SERIAL_PORT, baudRate: BAUD_RATE });
    const parser = port.pipe(new ReadlineParser({ delimiter: "\n" }));

    parser.on("data", (line) => {
      const v = parseFloat(line.trim());
      if (Number.isFinite(v) && v >= 0 && v <= 100) {
        latestMoisture = parseFloat(v.toFixed(1));
        portError      = null;
      }
    });

    port.on("error", (err) => {
      portError  = err.message;
      serialReady = false;
    });

    port.on("open", () => {
      console.log(`[/api/moisture] Serial port ${SERIAL_PORT} opened at ${BAUD_RATE} baud`);
      serialReady = true;
      portError   = null;
    });

  } catch (err) {
    portError   = `Could not open serial port ${SERIAL_PORT}: ${err.message}`;
    serialReady = false;
    console.error("[/api/moisture]", portError);
  }
}

// Kick off serial init as soon as the module is first loaded
initSerial();

// ── GET /api/moisture ─────────────────────────────────────────────────────
export async function GET() {
  // If not in serial mode, return an informative error
  const deviceMode = process.env.NEXT_PUBLIC_DEVICE_MODE || "MOCK";
  if (deviceMode !== "ESP32_SERIAL") {
    return NextResponse.json(
      { error: `Device mode is '${deviceMode}'. Set NEXT_PUBLIC_DEVICE_MODE=ESP32_SERIAL to use this endpoint.` },
      { status: 400 }
    );
  }

  // Port failed to open
  if (portError) {
    return NextResponse.json(
      { error: portError, hint: `Check that the ESP32 is connected to ${SERIAL_PORT} and the baud rate is ${BAUD_RATE}.` },
      { status: 503 }
    );
  }

  // No reading yet (ESP32 just connected or hasn't sent a line)
  if (latestMoisture === null) {
    return NextResponse.json(
      { error: "Waiting for first reading from ESP32. Try again in 1–2 seconds." },
      { status: 503 }
    );
  }

  return NextResponse.json({
    moisture  : latestMoisture,
    unit      : "%",
    port      : SERIAL_PORT,
    timestamp : new Date().toISOString(),
  });
}

