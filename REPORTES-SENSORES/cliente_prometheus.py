# ============================================================
# cliente_prometheus.py — Consultas a la API de Prometheus
# ============================================================
# Métricas por sensor:
#   NodeMCU V3   -> dht22_temperature_celsius_n{sensor="dht22",node="nodemcu_v3"}
#   NodeMCU V3 2 -> dht22_temperature_celsius_n2{sensor="dht22",node="nodemcu_v3_2"}
#   ESP32-C3     -> dht22_temperature_celsius_e{sensor="dht22",node="esp32c3_mini"}
#
# Las funciones públicas aceptan un parámetro opcional
# 'sensores' con la lista de nombres a consultar.
# Si se omite, se consultan todos los sensores definidos
# en SENSORES de configuracion.py.
# ============================================================

import requests
from datetime import datetime, timedelta
import pytz

from configuracion import (
    PROMETHEUS_URL, SENSORES,
    HORAS_HISTORIAL, PASO_CONSULTA, ZONA_HORARIA,
)

# Lapsos de tiempo disponibles
# clave -> (etiqueta legible, minutos totales, paso Prometheus)
LAPSOS = {
    "5m":  ("Últimos 5 minutos",   5,       "15s"),
    "15m": ("Últimos 15 minutos",  15,      "15s"),
    "30m": ("Últimos 30 minutos",  30,      "30s"),
    "1h":  ("Última hora",         60,      "1m"),
    "3h":  ("Últimas 3 horas",     180,     "1m"),
    "6h":  ("Últimas 6 horas",     360,     "2m"),
    "12h": ("Últimas 12 horas",    720,     "5m"),
    "24h": ("Últimas 24 horas",    1440,    "5m"),
    "2d":  ("Últimos 2 días",      2880,    "10m"),
    "1w":  ("Última semana",       10080,   "30m"),
    "1mo": ("Último mes",          43200,   "2h"),
}

def _consulta_instantanea(metrica: str, node: str, sensor: str) -> float | None:
    """Devuelve el valor actual de una métrica filtrando por node y sensor."""
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
        print(f"[Prometheus] Error consulta instantánea ({metrica}): {e}")
        return None

def _consulta_rango(metrica: str, node: str, sensor: str,
                    minutos_atras: int, paso: str):
    """
    Consulta una serie de tiempo mediante range query.
    Devuelve (timestamps[], valores[]) o ([], []) si no hay datos.
    """
    tz     = pytz.timezone(ZONA_HORARIA)
    fin    = datetime.now(tz)
    inicio = fin - timedelta(minutes=minutos_atras)
    query  = f'{metrica}{{sensor="{sensor}",node="{node}"}}'
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
        datos      = r.json()
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

# API pública

def obtener_lecturas_actuales(sensores: list[str] | None = None) -> dict:
    """
    Devuelve los valores actuales de los sensores indicados.
    Si 'sensores' es None, consulta todos los definidos en SENSORES.

    Estructura de retorno:
    {
        "NombreSensor": {"temperatura": float | None, "humedad": float | None},
        "timestamp": datetime
    }
    """
    nombres = sensores if sensores is not None else list(SENSORES.keys())
    datos   = {"timestamp": datetime.now(pytz.timezone(ZONA_HORARIA))}
    for nombre in nombres:
        if nombre not in SENSORES:
            continue
        cfg  = SENSORES[nombre]
        temp = _consulta_instantanea(cfg["metrica_temp"], cfg["label_node"], cfg["label_sensor"])
        hum  = _consulta_instantanea(cfg["metrica_hum"],  cfg["label_node"], cfg["label_sensor"])
        datos[nombre] = {"temperatura": temp, "humedad": hum}
    return datos

def obtener_historial(clave_lapso: str = "6h",
                      sensores: list[str] | None = None) -> dict:
    """
    Devuelve el historial del lapso indicado para los sensores solicitados.
    Si 'sensores' es None, consulta todos los definidos en SENSORES.

    Estructura de retorno:
    {
        "NombreSensor": {
            "tiempos_temp": [...], "valores_temp": [...],
            "tiempos_hum":  [...], "valores_hum":  [...],
        },
        "lapso_info": {"clave": str, "etiqueta": str, "minutos": int}
    }
    """
    if clave_lapso not in LAPSOS:
        clave_lapso = "6h"

    etiqueta, minutos, paso = LAPSOS[clave_lapso]
    nombres  = sensores if sensores is not None else list(SENSORES.keys())

    historial = {
        "lapso_info": {
            "clave":    clave_lapso,
            "etiqueta": etiqueta,
            "minutos":  minutos,
        }
    }

    for nombre in nombres:
        if nombre not in SENSORES:
            continue
        cfg    = SENSORES[nombre]
        tt, tv = _consulta_rango(cfg["metrica_temp"], cfg["label_node"], cfg["label_sensor"], minutos, paso)
        ht, hv = _consulta_rango(cfg["metrica_hum"],  cfg["label_node"], cfg["label_sensor"], minutos, paso)
        historial[nombre] = {
            "tiempos_temp": tt, "valores_temp": tv,
            "tiempos_hum":  ht, "valores_hum":  hv,
        }

    return historial