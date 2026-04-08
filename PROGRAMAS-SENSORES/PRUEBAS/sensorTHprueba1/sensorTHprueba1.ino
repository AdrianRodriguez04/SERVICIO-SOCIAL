//Lectura de Sensor DHT11

#include "DHT.h"

#define pinDatos 14 //GPI14 = D5 en ESP8266
#define modeloSensor DHT11

DHT sensorTH (pinDatos, modeloSensor);

void setup() {

  Serial.begin (115200);
  Serial.println ("***** Lectura DHT11 *****");

  sensorTH.begin();

}

void loop() {

  delay (2000);

  //Lee valores de temperatura y humedad
  float humedad = sensorTH.readHumidity();
  float temperatura = sensorTH.readTemperature();

  // Verifica si hubo error
  if (isnan(humedad) || isnan(temperatura)) {
    Serial.println("Error al leer el sensor DHT11");
    return;
  }

  //Mostrar valores leídos
  Serial.print ("Temperatura = ");
  Serial.print (temperatura);
  Serial.println (" ºC");
  Serial.print ("Humedad = ");
  Serial.print (humedad);
  Serial.println ("  %");
  
}
