//Lectura de Sensor DHT22
#include "DHT.h"
#include "DHT_U.h"

#define pinDatos 14 //GPI14 = D5 en ESP8266
#define modeloSensor DHT22

DHT sensorTH (pinDatos, modeloSensor);

void setup() {

  Serial.begin (115200);
  Serial.println ("***** Lectura DHT22 *****");

  sensorTH.begin();

}

void loop() {

  delay (3000);

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
