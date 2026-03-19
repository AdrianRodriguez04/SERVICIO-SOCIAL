# ============================================================
# cliente_prometheus.py — Consultas a la API de Prometheus
# ============================================================
# Cada sensor tiene sus propias metricas con labels especificos:
#   NodeMCU  -> dht22_temperature_celsius_n{sensor="dht22",node="nodemcu_v3"}
#   ESP32-C3 -> dht22_temperature_celsius_e{sensor="dht22",node="esp32c3_mini"}
# ============================================================

import requests
from datetime import datetime, timedelta
import pytz

from configuracion import (
    PROMETHEUS_URL, SENSORES,
    HORAS_HISTORIAL, PASO_CONSULTA, ZONA_HORARIA,
)

# ----------------------------------------------------------------
# Lapsos de tiempo disponibles para consulta
# clave -> (etiqueta legible, minutos totales, paso Prometheus)
# ----------------------------------------------------------------
LAPSOS = {
    "5m":   ("Últimos 5 minutos",   5,       "15s"),
    "15m":  ("Últimos 15 minutos",  15,      "15s"),
    "30m":  ("Últimos 30 minutos",  30,      "30s"),
    "1h":   ("Última hora",         60,      "1m"),
    "3h":   ("Últimas 3 horas",     180,     "1m"),
    "6h":   ("Últimas 6 horas",     360,     "2m"),
    "12h":  ("Últimas 12 horas",    720,     "5m"),
    "24h":  ("Últimas 24 horas",    1440,    "5m"),
    "2d":   ("Últimos 2 días",      2880,    "10m"),
    "1w":   ("Última semana",       10080,   "30m"),
    "1mo":  ("Último mes",          43200,   "2h"),
}


def _consulta_instantanea(metrica: str, node: str, sensor: str) -> float | None:
    """Devuelve el valor actual de una metrica filtrando por node y sensor."""
    query = f'{metrica}{{sensor="{sensor}",node="{node}"}}'
    try:
        r = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=5,
        )
        r.raise_for_status()
        datos = r.json()
        resultados = datos.get("data", {}).get("result", [])
        if resultados:
            return float(resultados[0]["value"][1])
        return None
    except Exception as e:
        print(f"[Prometheus] Error consulta instantanea ({metrica}): {e}")
        return None


def _consulta_rango(metrica: str, node: str, sensor: str,
                    minutos_atras: int, paso: str):
    """
    Consulta una serie de tiempo (range query).
    Devuelve (timestamps[], valores[]) o ([], []).
    """
    tz     = pytz.timezone(ZONA_HORARIA)
    fin    = datetime.now(tz)
    inicio = fin - timedelta(minutes=minutos_atras)

    query = f'{metrica}{{sensor="{sensor}",node="{node}"}}'
    try:
        r = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            params={
                "query": query,
                "start": inicio.timestamp(),
                "end":   fin.timestamp(),
                "step":  paso,
            },
            timeout=10,
        )
        r.raise_for_status()
        datos = r.json()
        resultados = datos.get("data", {}).get("result", [])
        if resultados:
            valores    = resultados[0]["values"]
            timestamps = [datetime.fromtimestamp(float(v[0]), tz) for v in valores]
            lecturas   = [float(v[1]) for v in valores]
            return timestamps, lecturas
        return [], []
    except Exception as e:
        print(f"[Prometheus] Error consulta rango ({metrica}): {e}")
        return [], []


# ----------------------------------------------------------------
# API publica
# ----------------------------------------------------------------

def obtener_lecturas_actuales() -> dict:
    """
    Devuelve los valores actuales de todos los sensores.
    {
        "NodeMCU V3": {"temperatura": 25.3, "humedad": 60.1},
        "ESP32-C3":   {"temperatura": 24.8, "humedad": 58.7},
        "timestamp":  datetime
    }
    """
    datos = {"timestamp": datetime.now(pytz.timezone(ZONA_HORARIA))}
    for nombre, cfg in SENSORES.items():
        temp = _consulta_instantanea(
            cfg["metrica_temp"], cfg["label_node"], cfg["label_sensor"]
        )
        hum = _consulta_instantanea(
            cfg["metrica_hum"], cfg["label_node"], cfg["label_sensor"]
        )
        datos[nombre] = {"temperatura": temp, "humedad": hum}
    return datos


def obtener_historial(clave_lapso: str = "6h") -> dict:
    """
    Devuelve el historial para el lapso indicado.
    clave_lapso debe ser una de las claves de LAPSOS (p.ej. '1h', '24h').
    {
        "NodeMCU V3": {
            "tiempos_temp": [...], "valores_temp": [...],
            "tiempos_hum":  [...], "valores_hum":  [...],
        },
        "lapso_info": {"clave": "6h", "etiqueta": "Últimas 6 horas", "minutos": 360}
    }
    """
    if clave_lapso not in LAPSOS:
        clave_lapso = "6h"

    etiqueta, minutos, paso = LAPSOS[clave_lapso]

    historial = {
        "lapso_info": {
            "clave":    clave_lapso,
            "etiqueta": etiqueta,
            "minutos":  minutos,
        }
    }

    for nombre, cfg in SENSORES.items():
        tt, tv = _consulta_rango(
            cfg["metrica_temp"], cfg["label_node"], cfg["label_sensor"],
            minutos, paso
        )
        ht, hv = _consulta_rango(
            cfg["metrica_hum"], cfg["label_node"], cfg["label_sensor"],
            minutos, paso
        )
        historial[nombre] = {
            "tiempos_temp": tt, "valores_temp": tv,
            "tiempos_hum":  ht, "valores_hum":  hv,
        }

    return historial

