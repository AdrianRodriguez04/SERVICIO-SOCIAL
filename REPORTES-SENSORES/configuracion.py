# ============================================================
# configuracion.py — Configuración central del bot DHT22
# ============================================================

# Telegram
TELEGRAM_TOKEN   = "8707579631:AAGAsPDbN19y_ypB8pmuWDvxFpxtE_WD28c"
TELEGRAM_CHAT_ID = "5287582092"

# Prometheus
PROMETHEUS_URL = "http://localhost:9090"

# Sensores
# Para agregar un nuevo sensor se debe añadir una nueva entrada a este diccionario con la misma estructura.
SENSORES = {
    "sensor_dht22_nmcu_1": {
        "job":          "dht22_sensor_n",
        "instance":     "10.203.58.115:80",
        "color":        "#FF6B6B",
        "label_sensor": "dht22",
        "label_node":   "nodemcu_v3",
        "metrica_temp": "dht22_temperature_celsius_n",
        "metrica_hum":  "dht22_humidity_percent_n",
    },
    "sensor_dht22_nmcu_2": {
        "job":          "dht22_sensor_n2",
        "instance":     "10.203.58.41:80",
        "color":        "#F7B731",
        "label_sensor": "dht22",
        "label_node":   "nodemcu_v3_2",
        "metrica_temp": "dht22_temperature_celsius_n2",
        "metrica_hum":  "dht22_humidity_percent_n2",
    },
    "sensor_dht22_espc3": {
        "job":          "dht22_sensor_e",
        "instance":     "10.203.58.133:80",
        "color":        "#4ECDC4",
        "label_sensor": "dht22",
        "label_node":   "esp32c3_mini",
        "metrica_temp": "dht22_temperature_celsius_e",
        "metrica_hum":  "dht22_humidity_percent_e",
    },
}

# Parametros de historial
HORAS_HISTORIAL = 6
PASO_CONSULTA   = "1m"
ZONA_HORARIA    = "America/Mexico_City"

# Umbrales de alertas
ALERTA_TEMP_MAX  = 35.0
ALERTA_TEMP_MIN  = 10.0
ALERTA_HUM_MAX   = 85.0
ALERTA_HUM_MIN   = 20.0
ALERTAS_ACTIVAS  = True