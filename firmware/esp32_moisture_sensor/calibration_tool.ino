/*
 * Optional: Calibration & Diagnostic Sketch
 * Upload this first if you want to find the exact DRY_ADC and WET_ADC values
 * for your specific sensor board.
 */

#include <Arduino.h>

const int AO_PIN = 4; // GPIO 4 (ADC1_CH4 on ESP32-C6)

void setup() {
  Serial.begin(115200);
  delay(1000);
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
  pinMode(AO_PIN, INPUT);

  Serial.println("\n--- LM393 Sensor Calibration Tool ---");
  Serial.println("1. Leave sensor dry in the air: note 'Dry Raw ADC'");
  Serial.println("2. Touch wet paper/fiber sample: note 'Wet Raw ADC'");
}

void loop() {
  long total = 0;
  for (int i = 0; i < 20; i++) {
    total += analogRead(AO_PIN);
    delay(10);
  }
  int raw = total / 20;
  float voltage = (raw / 4095.0) * 3.3;

  Serial.print("Raw ADC: ");
  Serial.print(raw);
  Serial.print(" | Approx Voltage: ");
  Serial.print(voltage, 2);
  Serial.println(" V");

  delay(1000);
}

