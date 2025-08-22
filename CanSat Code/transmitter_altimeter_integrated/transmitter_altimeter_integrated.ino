#include <Wire.h>
#include <SPI.h>
#include <LoRa.h>
#include <Adafruit_MPL3115A2.h>

// LoRa pins (adjust if needed)
#define ss 5
#define rst 14
#define dio0 2

// Create MPL3115A2 object
Adafruit_MPL3115A2 baro = Adafruit_MPL3115A2();

// Set your local sea-level pressure in hPa
#define SEA_LEVEL_PRESSURE 1008.10

void setup() {
  Serial.begin(115200);
  while (!Serial);

  Serial.println("Initializing MPL3115A2...");
  if (!baro.begin()) {
    Serial.println("Could not find a valid MPL3115A2 sensor!");
    while (1);
  }

  // Set sea-level pressure for accurate altitude readings
  baro.setSeaPressure(SEA_LEVEL_PRESSURE);
  Serial.println("MPL3115A2 Initialized!");

  Serial.println("Initializing LoRa...");
  LoRa.setPins(ss, rst, dio0);

  // Start LoRa at 433 MHz
  while (!LoRa.begin(433E6)) {
    Serial.print(".");
    delay(500);
  }

  LoRa.setSyncWord(0xA5);
  Serial.println("\nLoRa Initialization OK!");
}

void loop() {
  // === Read data from MPL3115A2 ===
  float pressure = baro.getPressure();      // in hPa
  float altitude = baro.getAltitude();      // in meters
  float temperature = baro.getTemperature();// in °C

  // === Prepare timestamp ===
  unsigned long timestamp = millis();  // in ms since boot

  // === Prepare message ===
  String message = "CAN-TI-" + String(timestamp) +
                   "; A-" + String(altitude, 2) +
                   "; T-" + String(temperature, 2) +
                   "; P-" + String(pressure / 100.0, 2) + // convert hPa to bar
                   "; X-0; Y-0; Z-0; YX-0; YY-0; YZ-0;";

  // === Send data via LoRa ===
  Serial.print("Sending message: ");
  Serial.println(message);

  LoRa.beginPacket();
  LoRa.print(message);
  LoRa.endPacket();

  Serial.println("Message sent!");
  Serial.println("-----------------------------");

  delay(2000); // send every 2 seconds
}
