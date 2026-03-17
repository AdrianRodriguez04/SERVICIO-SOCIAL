#include <WiFi.h>
#include <DHT.h>
#include <esp_task_wdt.h>

#define PIN_DATOS 4
#define DHT_VERSION DHT22

#define WDT_TIMEOUT 15
#define WIFI_TIMEOUT 25000
#define DHT_INTERVALO 3000

DHT sensorTH(PIN_DATOS, DHT_VERSION);

const char* ssid = "WDGTIC";
const char* password = "un@m_Dg+1C";

WiFiServer server(80);

float ultimaTemp = NAN;
float ultimaHumedad = NAN;
bool lecturaValida = false;

unsigned long ultimaLectura = 0;
bool servidorActivo = false;

char metricsBuffer[256];
size_t metricsLen = 0;


// Construir métricas

void actualizarMetrics() {

  if (!lecturaValida) return;

  metricsLen = snprintf(
    metricsBuffer,
    sizeof(metricsBuffer),

    "# TYPE dht22_temperature_celsius_e gauge\n"
    "dht22_temperature_celsius_e{sensor=\"dht22\",node=\"esp32c3_mini\"} %.2f\n"
    "# TYPE dht22_humidity_percent_e gauge\n"
    "dht22_humidity_percent_e{sensor=\"dht22\",node=\"esp32c3_mini\"} %.2f\n",

    ultimaTemp,
    ultimaHumedad
  );
}


// Servidor

void iniciarServidor() {

  server.stop();
  delay(50);

  server.begin();
  servidorActivo = true;

  Serial.println("[HTTP] Servidor iniciado");
}


// WiFi

void conectarWiFi() {

  if (WiFi.status() == WL_CONNECTED) return;

  servidorActivo = false;

  Serial.println("[WiFi] Conectando...");

  WiFi.disconnect(true);
  delay(500);

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  unsigned long inicio = millis();

  while (WiFi.status() != WL_CONNECTED) {

    if (millis() - inicio > WIFI_TIMEOUT) {

      Serial.println("[WiFi] Timeout reiniciando");
      ESP.restart();
    }

    esp_task_wdt_reset();
    delay(250);
    Serial.print(".");
  }

  Serial.println("");
  Serial.print("[WiFi] IP: ");
  Serial.println(WiFi.localIP());

  iniciarServidor();
}


// Lectura sensor

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
  else {

    Serial.println("[DHT] Lectura invalida");
  }
}


// Setup

void setup() {

  Serial.begin(115200);
  delay(1000);

  Serial.println("ESP32-C3 DHT22 Prometheus");

  esp_task_wdt_config_t wdt_config = {
    .timeout_ms = WDT_TIMEOUT * 1000,
    .idle_core_mask = 0,
    .trigger_panic = true
  };

  esp_task_wdt_reconfigure(&wdt_config);
  esp_task_wdt_add(NULL);

  sensorTH.begin();
  delay(2000);

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(false);
  WiFi.persistent(false);

  conectarWiFi();
}


// Loop

void loop() {

  esp_task_wdt_reset();

  if (WiFi.status() != WL_CONNECTED) {
    conectarWiFi();
    return;
  }

  leerSensor();

  WiFiClient client = server.available();

  if (!client) {
    delay(1);
    return;
  }

  unsigned long timeout = millis();

  while (!client.available()) {

    if (millis() - timeout > 300) {
      client.stop();
      return;
    }

    esp_task_wdt_reset();
    delay(1);
  }

  char request[100];
  int len = client.readBytesUntil('\r', request, sizeof(request)-1);
  request[len] = 0;
  client.readBytesUntil('\n', request, sizeof(request));


  // /metrics 

  if (strstr(request, "/metrics") != NULL) {

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
      "<title>ESP32-C3 Monitor</title>"
      "</head><body style='font-family:Arial;text-align:center;'>"
      "<h2>ESP32-C3: Monitoreo DHT22</h2>"
      "<p style='font-size:1.5em;'>Temp: <b>%.1f &deg;C</b></p>"
      "<p style='font-size:1.5em;'>Humedad: <b>%.1f %%</b></p>"
      "<br><p><a href='/metrics'>metrics</a></p>"
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

  delay(1);
  yield();  
}
