// NodeMCU V3 (ESP8266) - SENSOR N.1

#include <DHT.h>
#include <ESP8266WiFi.h>

// Configuración
#define PIN_DATOS    14
#define DHT_VERSION  DHT22
#define WIFI_TIMEOUT 20000
#define DHT_INTERVALO 3000

DHT sensorTH(PIN_DATOS, DHT_VERSION);

const char* ssid     = "WDGTIC";
const char* password = "un@m_Dg+1C";

WiFiServer server(80);

float ultimaTemp    = NAN;
float ultimaHumedad = NAN;
bool  lecturaValida = false;

unsigned long ultimaLectura = 0;

// buffer cacheado para Prometheus
char metricsBuffer[256];
size_t metricsLen = 0;

// Construir métricas

void actualizarMetrics() {

  if (!lecturaValida) return;

  metricsLen = snprintf(
    metricsBuffer,
    sizeof(metricsBuffer),

    "# TYPE dht22_temperatura gauge\n"
    "dht22_temperatura{sensor_id=\"1\",microcontrolador=\"nodemcu_v3\"} %.2f\n"
    "# TYPE dht22_humedad gauge\n"
    "dht22_humedad{sensor_id=\"1\",microcontrolador=\"nodemcu_v3\"} %.2f\n",

    ultimaTemp,
    ultimaHumedad
  );
}

// Reconexión WiFi 

void conectarWiFi() {

  if (WiFi.status() == WL_CONNECTED) return;

  Serial.println("\n[WiFi] Reconectando...");

  WiFi.disconnect();
  delay(500);

  WiFi.begin(ssid, password);

  unsigned long inicio = millis();

  while (WiFi.status() != WL_CONNECTED) {

    if (millis() - inicio > WIFI_TIMEOUT) {

      Serial.println("[WiFi] Timeout — reiniciando...");
      ESP.restart();
    }

    delay(500);
    Serial.print(".");
  }

  Serial.println("\n[WiFi] Conectado");
  Serial.print("[WiFi] IP: ");
  Serial.println(WiFi.localIP());

  server.begin();
}

// Setup

void setup() {

  Serial.begin(115200);
  delay(1000);

  Serial.println("\n** SENSOR-ID: 1 - MICROCONTROLADOR: NodeMCU V3 **");

  sensorTH.begin();
  delay(2000);

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);

  conectarWiFi();

  Serial.println("Rutas disponibles:");
  Serial.println("http://<IP>/");
  Serial.println("http://<IP>/metrics");
}

// Lectura del sensor

void leerSensor() {

  if (millis() - ultimaLectura < DHT_INTERVALO) return;

  ultimaLectura = millis();

  float h = sensorTH.readHumidity();
  float t = sensorTH.readTemperature();

  if (!isnan(h) && !isnan(t)) {

    ultimaTemp = t;
    ultimaHumedad = h;
    lecturaValida = true;

    actualizarMetrics();
  }
}

// Loop

void loop() {

  yield();

  if (WiFi.status() != WL_CONNECTED) {
    conectarWiFi();
    return;
  }

  leerSensor();

  WiFiClient client = server.available();

  if (!client) {
    delay(5);
    return;
  }

  unsigned long tInicio = millis();

  while (!client.available()) {

    if (millis() - tInicio > 2000) {
      client.stop();
      return;
    }

    yield();
    delay(1);
  }

  String requestLine = client.readStringUntil('\n');
  requestLine.trim();

  while (client.connected() && client.available()) {

    String linea = client.readStringUntil('\n');
    linea.trim();

    if (linea.length() == 0) break;

    yield();
  }

  // /metrics

  if (requestLine.indexOf("GET /metrics") >= 0) {

    client.println("HTTP/1.1 200 OK");
    client.println("Content-Type: text/plain; version=0.0.4");
    client.println("Connection: close");
    client.print("Content-Length: ");
    client.println(metricsLen);
    client.println();

    client.write((uint8_t*)metricsBuffer, metricsLen);
  }

  // Página web

  else {

    char html[512];

    int len = snprintf(
      html,
      sizeof(html),

      "<!DOCTYPE HTML><html><head>"
      "<meta charset='UTF-8'>"
      "<meta http-equiv='refresh' content='5'>"
      "<title>NodeMCU V3 - N.1</title>"
      "</head><body style='font-family:Arial;text-align:center;'>"
      "<h2>NodeMCU V3 - N.1: Monitoreo DHT22</h2>"
      "<p style='font-size:1.5em;'>Temp: <b>%.1f &deg;C</b></p>"
      "<p style='font-size:1.5em;'>Humedad: <b>%.1f %%</b></p>"
      "<hr><p><a href='/metrics'>Ir a /metrics</a></p>"
      "</body></html>",

      ultimaTemp,
      ultimaHumedad
    );

    client.println("HTTP/1.1 200 OK");
    client.println("Content-Type: text/html");
    client.println("Connection: close");
    client.print("Content-Length: ");
    client.println(len);
    client.println();

    client.write((uint8_t*)html, len);
  }

  client.stop();
}
