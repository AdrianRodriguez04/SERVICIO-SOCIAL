# ============================================================
# configuracion.py — Configuración central del bot DHT22
# ============================================================

# --- Telegram ---
TELEGRAM_TOKEN   = "" #Borrado por seguridad 
TELEGRAM_CHAT_ID = "" #Borrado ṕor seguridad

# --- Prometheus ---
PROMETHEUS_URL = "http://localhost:9090" 

# --- Sensores ---
SENSORES = {
    "NodeMCU V3": {
        "job":          "dht22_sensor_n",
        "instance":     "10.203.58.115:80",   
        "color":        "#FF6B6B",
        "label_sensor": "dht22",
        "label_node":   "nodemcu_v3",          
        "metrica_temp": "dht22_temperature_celsius_n",
        "metrica_hum":  "dht22_humidity_percent_n",
    },
    "ESP32-C3": {
        "job":          "dht22_sensor_e",
        "instance":     "10.203.58.133:80",   
        "color":        "#4ECDC4",
        "label_sensor": "dht22",
        "label_node":   "esp32c3_mini",        
        "metrica_temp": "dht22_temperature_celsius_e",
        "metrica_hum":  "dht22_humidity_percent_e",
    },
}

# --- Parametros de historial ---
HORAS_HISTORIAL = 6
PASO_CONSULTA   = "1m"
ZONA_HORARIA    = "America/Mexico_City"

# --- Umbrales de alertas ---
ALERTA_TEMP_MAX  = 40.0
ALERTA_TEMP_MIN  = 5.0
ALERTA_HUM_MAX   = 85.0
ALERTA_HUM_MIN   = 20.0
ALERTAS_ACTIVAS  = True
