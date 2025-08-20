#include <Wire.h>
#include <Adafruit_MPL3115A2.h>

// Power by connecting Vin to 3-5V, GND to GND
// Uses I2C - connect SCL to the SCL pin, SDA to SDA pin
// See the Wire tutorial for pinouts for each Arduino
// http://arduino.cc/en/reference/wire
Adafruit_MPL3115A2 baro = Adafruit_MPL3115A2();
double current_pressure = 100300;
// Number of samples to average
const int N = 5;
// previous altitude
int prev_alt = 0.0;
// resolution
float res = 0.44;

void setup() {
  Serial.begin(9600);
  Serial.println("MPL3115A2...");

  if (!baro.begin()) {
    Serial.println("Couldnt find sensor");
    while (1) {delay(10);}
  }

  // Step 1: Set local sea-level pressure in Pascals
  // Example: If your weather app shows 1013.25 hPa => 101325 Pa
  baro.setMode(MPL3115A2_ALTIMETER);
  baro.setSeaPressure(current_pressure);

  Serial.println("Calibration done!");
}

void loop() {
  // Read pressure (optional)
  double pascals = baro.getPressure();
  Serial.print(pascals / 3377.0f); 
  Serial.println(" Inches (Hg)");

  // Take N altitude samples and average them
  float sum_alt = 0.0;
  for (int i = 0; i < N; i++) {
    sum_alt += baro.getAltitude();
    delay(10);  // small delay between samples for stability
  }
  float avg_alt = sum_alt / N;

  int alt = prev_alt;

  if (prev_alt==0.0){
    prev_alt = avg_alt;
  }

  if (avg_alt > prev_alt){
    avg_alt-=res;
  }
  else if(avg_alt < prev_alt){
    avg_alt+=res;
  }

  prev_alt = avg_alt;

  // Print averaged altitude
  Serial.print("ALT: ");
  Serial.print(avg_alt, 2);   // two decimals are enough
  Serial.println(" meters");

  // Temperature (optional)
  float tempC = baro.getTemperature();
  Serial.print(tempC);
  Serial.println("*C");

  Serial.println("------------------------");
  delay(50);  // main loop delay
}