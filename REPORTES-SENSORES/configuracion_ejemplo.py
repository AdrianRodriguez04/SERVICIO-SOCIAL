# ============================================================
# configuracion.py — Configuración central del bot DHT22
# ============================================================

# Telegram
# Para obtener el token del bot, se debe crear un bot en Telegram usando el BotFather y copiar el token que se genera.
TELEGRAM_TOKEN   = ""

# Para obtener el chat ID, se puede crear un grupo en Telegram con el bot agregado y en la URL del grupo se encuentra el chat ID después del signo de #.
TELEGRAM_CHAT_ID = ""

# Prometheus
PROMETHEUS_URL = "http://localhost:9090"

# Sensores
# Para agregar un nuevo sensor se debe añadir una nueva entrada a este diccionario con la misma estructura.
SENSORES = {
    "dht22_nodemcuv3_n1": {
        "job":          "dht22_nodemcu_v3_n1",
        "instance":     "10.203.58.115:80",
        "color":        "#EA4343",
        "label_sensor_id": "1",
        "label_microcontrolador":   "nodemcu_v3",
        "metrica_temp": "dht22_temperatura",
        "metrica_hum":  "dht22_humedad",
    },
    "dht22_nodemcuv3_n2": {
        "job":          "dht22_nodemcu_v3_n2",
        "instance":     "10.203.58.41:80",
        "color":        "#F7B731",
        "label_sensor_id": "2",
        "label_microcontrolador":   "nodemcu_v3",
        "metrica_temp": "dht22_temperatura",
        "metrica_hum":  "dht22_humedad",
    },
    "dht22_esp32c3_n1": {
        "job":          "dht22_esp32c3_n1",
        "instance":     "10.203.58.133:80",
        "color":        "#4ECDC4",
        "label_sensor_id": "1",
        "label_microcontrolador":   "esp32_c3",
        "metrica_temp": "dht22_temperatura",
        "metrica_hum":  "dht22_humedad",
    },
    "dht22_esp32c3_n2": {
        "job":          "dht22_esp32c3_n2",
        "instance":     "10.203.58.110:80",
        "color":        "#FF39FF",
        "label_sensor_id": "2",
        "label_microcontrolador":   "esp32_c3",
        "metrica_temp": "dht22_temperatura",
        "metrica_hum":  "dht22_humedad",
    },
    "dht22_esp32c3_n3": {
        "job":          "dht22_esp32c3_n3",
        "instance":     "10.203.58.100:80",
        "color":        "#39FF39",
        "label_sensor_id": "3",
        "label_microcontrolador":   "esp32_c3",
        "metrica_temp": "dht22_temperatura",
        "metrica_hum":  "dht22_humedad",
    },
    "dht22_esp32c3_n4": {
        "job":          "dht22_esp32c3_n4",
        "instance":     "10.203.58.173:80",
        "color":        "#3939FF",
        "label_sensor_id": "4",
        "label_microcontrolador":   "esp32_c3",
        "metrica_temp": "dht22_temperatura",
        "metrica_hum":  "dht22_humedad",
    },
}

# Parametros de historial
HORAS_HISTORIAL = 6
PASO_CONSULTA   = "1m"
ZONA_HORARIA    = "America/Mexico_City"

# Umbrales de alertas
ALERTA_TEMP_MAX  = 30.0
ALERTA_TEMP_MIN  = 10.0
ALERTA_HUM_MAX   = 60.0
ALERTA_HUM_MIN   = 15.0
ALERTAS_ACTIVAS  = True