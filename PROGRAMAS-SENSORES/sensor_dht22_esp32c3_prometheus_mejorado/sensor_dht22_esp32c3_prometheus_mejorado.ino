// Lectura de Sensor DHT22 via Web + Endpoint /metrics para Prometheus
// ESP32-C3 SuperMini

#include <DHT.h>
#include <WiFi.h>

#define PIN_DATOS     4
#define DHT_VERSION   DHT22
#define WIFI_TIMEOUT  20000
#define DHT_INTERVALO 3000

DHT sensorTH(PIN_DATOS, DHT_VERSION);

const char* ssid     = "WDGTIC";
const char* password = "un@m_Dg+1C";

WiFiServer server(80);

float ultimaTemp    = NAN;
float ultimaHumedad = NAN;
bool  lecturaValida = false;
unsigned long ultimaLectura = 0;

char   metricsBuffer[256];
size_t metricsLen = 0;


void actualizarMetrics() {
  if (!lecturaValida) return;
  metricsLen = snprintf(
    metricsBuffer, sizeof(metricsBuffer),
    "# TYPE dht22_temperature_celsius_e gauge\n"
    "dht22_temperature_celsius_e{sensor=\"dht22\",node=\"esp32c3_mini\"} %.2f\n"
    "# TYPE dht22_humidity_percent_e gauge\n"
    "dht22_humidity_percent_e{sensor=\"dht22\",node=\"esp32c3_mini\"} %.2f\n",
    ultimaTemp, ultimaHumedad
  );
}


void conectarWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.println("\n[WiFi] Conectando...");
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
  Serial.println("\n[WiFi] Conectado — IP: " + WiFi.localIP().toString());
  server.begin();
}


void setup() {
  Serial.begin(115200);
  delay(1000);
  sensorTH.begin();
  delay(2000);
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  conectarWiFi();
}


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


void loop() {

  if (WiFi.status() != WL_CONNECTED) {
    conectarWiFi();
    return;
  }

  leerSensor();

  WiFiClient client = server.available();
  if (!client) { delay(5); return; }

  unsigned long tInicio = millis();
  while (!client.available()) {
    if (millis() - tInicio > 2000) { client.stop(); return; }
    delay(1);  // ← cede tiempo al SO, evita WDT panic
  }

  String req = client.readStringUntil('\n');
  req.trim();

  while (client.connected() && client.available()) {
    String linea = client.readStringUntil('\n');
    linea.trim();
    if (linea.length() == 0) break;
    delay(1);  // ← idem
  }

  if (req.indexOf("GET /metrics") >= 0) {

    client.println("HTTP/1.1 200 OK");
    client.println("Content-Type: text/plain; version=0.0.4");
    client.println("Connection: close");
    client.print("Content-Length: ");
    client.println(metricsLen);
    client.println();
    client.write((uint8_t*)metricsBuffer, metricsLen);

  } else {

    char html[512];
    int len = snprintf(html, sizeof(html),
      "<!DOCTYPE HTML><html><head>"
      "<meta charset='UTF-8'>"
      "<meta http-equiv='refresh' content='5'>"
      "<title>ESP32-C3 Monitor</title>"
      "</head><body style='font-family:Arial;text-align:center;'>"
      "<h2>ESP32-C3 SuperMini: Monitoreo DHT22</h2>"
      "<p style='font-size:1.5em;'>Temp: <b>%.1f &deg;C</b></p>"
      "<p style='font-size:1.5em;'>Humedad: <b>%.1f %%</b></p>"
      "<hr><p><a href='/metrics'>Ir a /metrics</a></p>"
      "</body></html>",
      ultimaTemp, ultimaHumedad
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
