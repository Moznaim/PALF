/*
 * PALF-Vision AI: Pineapple Leaf Fiber Moisture Sensor
 * Target Microcontroller: ESP32-C6-WROOM-1 (or ESP32-C6 DevKit)
 * Sensor: LM393 Rain/Water Detection Board
 *
 * ────────────────────────────────────────────────────────────────
 * HARDWARE CONNECTIONS:
 * ────────────────────────────────────────────────────────────────
 *   LM393 Board Pin      ESP32-C6 Pin
 *   -----------------    ------------------------------------------
 *   VCC                  3V3  (IMPORTANT: Do NOT use 5V!)
 *   GND                  GND
 *   AO (Analog Out)      GPIO 4 (ADC1_CH4)
 *   DO (Digital Out)     Not connected (or optional GPIO 5)
 *
 * ────────────────────────────────────────────────────────────────
 * COMPATIBILITY WITH PALF-VISION WEB APPLICATION:
 * ────────────────────────────────────────────────────────────────
 *   - app/api/moisture/route.js expects a clean line with just a number
 *     like "11.5" followed by newline (\n).
 *   - Baud rate: 115200
 *
 * ────────────────────────────────────────────────────────────────
 * CALIBRATION:
 * ────────────────────────────────────────────────────────────────
 *   LM393 analog output is INVERTED:
 *     - Open air / completely dry fiber  => Highest voltage (~3200-4095 raw ADC)
 *     - Water drops / saturated wet fiber => Lower voltage   (~500-1200 raw ADC)
 *
 *   Adjust DRY_ADC and WET_ADC below based on your serial readings.
 */

#include <Arduino.h>

// ── Pin definitions ─────────────────────────────────────────────
const int AO_PIN = 4;        // ADC1 channel 4 on ESP32-C6

// ── Calibration points (12-bit ADC: 0 to 4095) ──────────────────
// Tip: Start with these defaults. If your reading stays at 0%,
// check your open-air raw reading and update DRY_ADC.
const int DRY_ADC = 3600;    // Reading when sensor is completely dry
const int WET_ADC =  900;    // Reading when sensor is touching saturated water

// ── Sampling settings ───────────────────────────────────────────
const int NUM_SAMPLES     = 10;   // Moving average count to eliminate analog jitter
const int SAMPLE_DELAY_MS = 10;   // Delay between individual analog readings
const int LOOP_DELAY_MS   = 1000; // Emit reading every 1 second

void setup() {
  // Initialize Serial for Raspberry Pi USB communication
  Serial.begin(115200);

  // Allow USB serial time to establish
  delay(1000);

  // ESP32-C6 ADC configuration
  analogReadResolution(12);               // 0 to 4095
  analogSetAttenuation(ADC_11db);         // Measure full range up to ~3.1V

  pinMode(AO_PIN, INPUT);
}

void loop() {
  // Take multiple samples to smooth out electrical noise
  long total = 0;
  for (int i = 0; i < NUM_SAMPLES; i++) {
    total += analogRead(AO_PIN);
    delay(SAMPLE_DELAY_MS);
  }
  float avgRaw = (float)total / (float)NUM_SAMPLES;

  // Invert and map:
  // When raw == DRY_ADC  => moisture = 0%
  // When raw == WET_ADC  => moisture = 100%
  float moisture = ((float)(DRY_ADC - avgRaw) / (float)(DRY_ADC - WET_ADC)) * 100.0;

  // Clamp within realistic fiber moisture range (0.0% to 100.0%)
  if (moisture < 0.0) moisture = 0.0;
  if (moisture > 100.0) moisture = 100.0;

  // Output ONLY the moisture number to match Next.js /api/moisture parser
  // Format: "11.5"
  Serial.println(moisture, 1);

  delay(LOOP_DELAY_MS);
}

