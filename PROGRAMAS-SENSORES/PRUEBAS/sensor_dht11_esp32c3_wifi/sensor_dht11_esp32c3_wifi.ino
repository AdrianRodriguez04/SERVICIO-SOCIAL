#include <WiFi.h>
#include <WebServer.h>
#include <DHT.h>

// Credenciales WiFi
const char* ssid = "WDGTIC";
const char* password = "un@m_Dg+1C";

#define DHTPIN 4
#define DHTTYPE DHT11

DHT dht(DHTPIN, DHTTYPE);
WebServer server(80); // Servidor en el puerto 80

void handleRoot() {
  float h = dht.readHumidity();
  float t = dht.readTemperature();
  
  // Estructura HTML para mostrar los datos
  String html = "<html><head><meta charset='UTF-8'><meta http-equiv='refresh' content='5'>";
  html += "<title>ESP32-C3 Monitor</title></head><body>";
  html += "<h1>Datos del Sensor DHT11</h1>";
  
  if (isnan(h) || isnan(t)) {
    html += "<p style='color:red;'>Error al leer el sensor</p>";
  } else {
    html += "<p>Temperatura: <b>" + String(t) + " °C</b></p>";
    html += "<p>Humedad: <b>" + String(h) + " %</b></p>";
  }
  
  html += "</body></html>";
  server.send(200, "text/html", html);
}

void setup() {
  Serial.begin(115200);
  dht.begin();

  // Conexión WiFi
  WiFi.begin(ssid, password);
  Serial.print("Conectando a WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  
  Serial.println("\nConectado!");
  Serial.print("Dirección IP: ");
  Serial.println(WiFi.localIP()); // Esta es la IP que pondrás en tu navegador

  // Configurar rutas del servidor
  server.on("/", handleRoot);
  server.begin();
}

void loop() {
  server.handleClient(); // Maneja las peticiones de los usuarios
}