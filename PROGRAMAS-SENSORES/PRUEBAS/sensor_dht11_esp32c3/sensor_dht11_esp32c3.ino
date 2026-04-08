#include <DHT.h>
#include <DHT_U.h>

#define DHTPIN 4      // Pin GPIO4 en la ESP32-C3
#define DHTTYPE DHT11 // Estoy trabajando con el DHT11 pero esta variable puede ser cambiada por DHT22

DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(115200);
  Serial.println(F("Iniciando lectura del sensor DHT11..."));
  dht.begin(); 
}

void loop() {
  // Agregar un pequeño retardo entre lecturas para no saturar el sensor
  delay(2000);         // Espera de 2 segundos entre cada lectura

  float h = dht.readHumidity();
  float t = dht.readTemperature();

  // Verificar lecturas
  if (isnan(h) || isnan(t)) {
    Serial.println(F("Error al leer el sensor DHT11."));
  } else {
    Serial.print(F("Humedad: "));
    Serial.print(h);
    Serial.print(F(" %\t"));
    Serial.print(F("Temperatura: "));
    Serial.print(t);
    Serial.println(F(" °C"));
  }
}