// ESP32-C3 SuperMini - SENSOR N.3

#include <DHT.h>
#include <WiFi.h>
#include <WebServer.h>

#define PIN_DATOS     4
#define DHT_VERSION   DHT22
#define WIFI_TIMEOUT  20000
#define DHT_INTERVALO 3000

DHT sensorTH(PIN_DATOS, DHT_VERSION);

const char* ssid     = "WDGTIC";
const char* password = "un@m_Dg+1C";

WebServer server(80);

float         ultimaTemp     = NAN;
float         ultimaHumedad  = NAN;
bool          lecturaValida  = false;
unsigned long ultimaLectura  = 0;
bool          servidorActivo = false;

void handleMetrics() {
  if (!lecturaValida) {
    server.send(503, "text/plain", "# sensor not ready\n");
    return;
  }
  char buf[256];
  snprintf(buf, sizeof(buf),
    "# TYPE dht22_temperatura gauge\n"
    "dht22_temperatura{sensor_id=\"3\",microcontrolador=\"esp32_c3\"} %.2f\n"
    "# TYPE dht22_humedad gauge\n"
    "dht22_humedad{sensor_id=\"3\",microcontrolador=\"esp32_c3\"} %.2f\n",
    ultimaTemp, ultimaHumedad
  );
  server.send(200, "text/plain; version=0.0.4", buf);
}

void handleRoot() {
  char html[512];
  snprintf(html, sizeof(html),
    "<!DOCTYPE HTML><html><head>"
    "<meta charset='UTF-8'>"
    "<meta http-equiv='refresh' content='5'>"
    "<title>ESP32-C3 - N.3</title>"
    "</head><body style='font-family:Arial;text-align:center;'>"
    "<h2>ESP32-C3 SuperMini - N.3: Monitoreo DHT22</h2>"
    "<p style='font-size:1.5em;'>Temp: <b>%.1f &deg;C</b></p>"
    "<p style='font-size:1.5em;'>Humedad: <b>%.1f %%</b></p>"
    "<p>RSSI: %d dBm</p>"
    "<hr><p><a href='/metrics'>Ir a /metrics</a></p>"
    "</body></html>",
    ultimaTemp, ultimaHumedad, WiFi.RSSI()
  );
  server.send(200, "text/html", html);
}

void iniciarServidor() {
  server.stop();
  delay(100);
  server.on("/",        handleRoot);
  server.on("/metrics", handleMetrics);
  server.begin();
  servidorActivo = true;
  Serial.println("[HTTP] http://" + WiFi.localIP().toString() + "/");
}

void conectarWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  servidorActivo = false;
  Serial.println("\n[WiFi] Conectando...");
  WiFi.disconnect();
  delay(1000);
  WiFi.begin(ssid, password);
  unsigned long inicio = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - inicio > WIFI_TIMEOUT) {
      Serial.println("[WiFi] Timeout — reiniciando...");
      delay(500);
      ESP.restart();
    }
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n[WiFi] Conectado — IP: " + WiFi.localIP().toString()
                 + "  RSSI: " + String(WiFi.RSSI()) + " dBm");
  iniciarServidor();
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  sensorTH.begin();
  delay(2000);

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  WiFi.setTxPower(WIFI_POWER_11dBm);

  conectarWiFi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    conectarWiFi();
    return;
  }

  if (!servidorActivo) {
    iniciarServidor();
  }

  if (millis() - ultimaLectura >= DHT_INTERVALO) {
    ultimaLectura = millis();
    float h = sensorTH.readHumidity();
    float t = sensorTH.readTemperature();
    if (!isnan(h) && !isnan(t)) {
      ultimaTemp    = t;
      ultimaHumedad = h;
      lecturaValida = true;
      Serial.printf("[DHT] T=%.1fC  H=%.1f%%  RSSI=%ddBm\n",
                    t, h, WiFi.RSSI());
    } else {
      Serial.println("[DHT] Lectura invalida");
    }
  }

  server.handleClient();
}