#include <Wire.h>
#include <Adafruit_MPL3115A2.h>

Adafruit_MPL3115A2 baro = Adafruit_MPL3115A2();

// Set your local sea-level pressure in Pascals
// You can get this once from any weather app or site
#define SEA_LEVEL_PRESSURE 1008.10  // Example: 1006.50 hPa = 100650 Pa

void setup() {
  Serial.begin(115200);
  if (!baro.begin()) {
    Serial.println("Could not find a valid MPL3115A2 sensor!");
    while (1);
  }

  // Tell sensor our sea-level pressure for accurate altitude readings
  baro.setSeaPressure(SEA_LEVEL_PRESSURE);

  Serial.println("MPL3115A2 Altimeter Calibration Complete");
}

void loop() {
  float pressure = baro.getPressure();
  float altitude = baro.getAltitude();
  float temperature = baro.getTemperature();

  Serial.print("Pressure = ");
  Serial.print(pressure, 2);
  Serial.println(" hPa");

  Serial.print("Altitude = ");
  Serial.print(altitude, 2);
  Serial.println(" m");

  Serial.print("Temperature = ");
  Serial.print(temperature, 2);
  Serial.println(" C");

  Serial.println("-----------------");
  delay(2000);
}
