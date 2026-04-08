//Lectura de Sensor DHT11/DHT22 via Web

#include "DHT.h"
#include "DHT_U.h"
#include "ESP8266WiFi.h"

#define pinDatos 14 //GPI14 = D5 en ESP8266
#define DHTversion DHT22 //DHT11 o DHT22

DHT sensorTH (pinDatos, DHTversion);

const char* ssid = "WDGTIC";
const char* password = "un@m_Dg+1C";

WiFiServer server(80);

void setup() {

  Serial.begin (115200);
  Serial.println ("***** Lectura DHT22 *****");

  sensorTH.begin();

  Serial.println("Conectando a WiFi...");
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {

    delay(500);
    Serial.print(".");

  }

  Serial.println("\nWiFi conectado");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());

  server.begin();

}

void loop() {

  // Espera cliente
  WiFiClient client = server.available();
  if (!client) {
    return;
  }

  //Lee valores de temperatura y humedad
  float humedad = sensorTH.readHumidity();
  float temperatura = sensorTH.readTemperature();

  // Verifica si hubo error
  if (isnan(humedad) || isnan(temperatura)) {
    return;
  }

  // Respuesta HTTP
  client.println("HTTP/1.1 200 OK");
  client.println("Content-Type: text/html");
  client.println("Connection: close");
  client.println();

  // Pagina HTML
  client.println("<!DOCTYPE HTML>");
  client.println("<html>");
  client.println("<head>");
  client.println("<meta charset='UTF-8'>");
  client.println("<meta http-equiv='refresh' content='5'>"); 
  client.println("<title>Monitor DHT11</title>");
  client.println("</head>");
  client.println("<body style='font-family: Arial; text-align: center;'>");
  client.println("<h2>Monitoreo de Temperatura y Humedad</h2>");

  // Mostrar datos del sensor
  client.print("<p><b>Temperatura:</b> ");
  client.print(temperatura);
  client.println(" °C</p>");

  client.print("<p><b>Humedad:</b> ");
  client.print(humedad);
  client.println(" %</p>");

  client.println("</body>");
  client.println("</html>");

  delay(3000);  // Pequeña pausa de 3 segundos
  
}
