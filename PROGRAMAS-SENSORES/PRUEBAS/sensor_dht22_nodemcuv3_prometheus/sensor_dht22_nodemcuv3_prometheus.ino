// Lectura de Sensor DHT22 via Web + Endpoint /metrics para Prometheus (Versión NodeMCU V3)
#include "DHT.h"
#include "DHT_U.h"
#include "ESP8266WiFi.h"

#define pinDatos 14       // GPI14 - D5 
#define DHTversion DHT22 // Especifico el sensor DHT22

DHT sensorTH(pinDatos, DHTversion);

const char* ssid     = "WDGTIC";
const char* password = "un@m_Dg+1C";

WiFiServer server(80);

void setup() {
  Serial.begin(115200);
  Serial.println("\n***** NodeMCU V3: Lectura DHT22 con Prometheus *****");

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
  Serial.println("Rutas disponibles:");
  Serial.println("  http://<IP>/        -> Pagina HTML");
  Serial.println("  http://<IP>/metrics -> Metricas para Prometheus");

  server.begin();
}

void loop() {
  // Espera cliente
  WiFiClient client = server.available();
  if (!client) return;

  // Esperar a que el cliente mande datos (timeout 3s)
  unsigned long timeout = millis();
  while (client.available() == 0) {
    if (millis() - timeout > 3000) {
      client.stop();
      return;
    }
    delay(10);
  }

  // Leer headers HTTP
  String requestLine = "";
  bool primeraLinea = true;

  while (client.connected()) {
    if (client.available()) {
      String linea = client.readStringUntil('\n');
      linea.trim();

      if (primeraLinea) {
        requestLine = linea; 
        primeraLinea = false;
      }
      // Línea vacía = fin de headers
      if (linea.length() == 0) {
        break;
      }
    }
  }

  // Lectura del sensor
  float humedad     = sensorTH.readHumidity();
  float temperatura = sensorTH.readTemperature();

  // Error en la lectura
  if (isnan(humedad) || isnan(temperatura)) {
    client.println("HTTP/1.1 503 Service Unavailable");
    client.println("Content-Type: text/plain");
    client.println("Connection: close");
    client.println();
    client.println("Error: no se pudo leer el sensor DHT11");
    client.stop();
    return;
  }

  //  Ruta /metrics -> Formato Prometheus
  if (requestLine.indexOf("GET /metrics") >= 0) {
    String body = "";

    body += "# HELP dht22_temperature_celsius Temperatura leida por el sensor DHT22 y el NodeMCU V3\n";
    body += "# TYPE dht22_temperature_celsius gauge\n";
    body += "dht22_temperature_celsius{sensor=\"dht22\",node=\"nodemcu_v3\"} ";
    body += String(temperatura, 2);
    body += "\n";

    body += "# HELP dht22_humidity_percent Humedad relativa leida por el sensor DHT22 y el NodeMCU V3\n";
    body += "# TYPE dht22_humidity_percent gauge\n";
    body += "dht22_humidity_percent{sensor=\"dht22\",node=\"nodemcu_v3\"} ";
    body += String(humedad, 2);
    body += "\n";

    client.println("HTTP/1.1 200 OK");
    client.println("Content-Type: text/plain; version=0.0.4; charset=utf-8");
    client.println("Connection: close");
    client.println();
    client.print(body);

  //  Ruta / -> Pagina HTML
  } else {
    client.println("HTTP/1.1 200 OK");
    client.println("Content-Type: text/html");
    client.println("Connection: close");
    client.println();

    client.println("<!DOCTYPE HTML><html><head><meta charset='UTF-8'>");
    client.println("<meta http-equiv='refresh' content='5'>");
    client.println("<title>NodeMCU V3 Monitor</title></head>");
    client.println("<body style='font-family: Arial; text-align: center;'>");
    client.println("<h2>NodeMCU V3: Monitoreo DHT22</h2>");
    client.print("<p style='font-size: 1.5em;'>Temp: <b>");
    client.print(temperatura);
    client.println(" &deg;C</b></p>");
    client.print("<p style='font-size: 1.5em;'>Humedad: <b>");
    client.print(humedad);
    client.println(" %</b></p>");
    client.println("<hr><p><a href='/metrics'>Ir a /metrics</a></p>");
    client.println("</body></html>");
  }

  delay(10);
  client.stop();
}
