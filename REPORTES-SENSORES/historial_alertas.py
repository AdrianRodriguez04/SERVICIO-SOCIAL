# ============================================================
# historial_alertas.py — Registro y exportación del historial
#                        de alertas lanzadas por el bot DHT22
# ============================================================
# Uso:
#   from historial_alertas import registrar_alerta, exportar_csv_alertas
#
#   registrar_alerta(sensor, coordenadas, tipo, estado, valor, limite)
#   buf, nombre = exportar_csv_alertas()
# ============================================================

import csv
import io
from datetime import datetime
from typing import Literal

import pytz

from configuracion import ZONA_HORARIA, SENSORES

# Lista en memoria con todas las alertas registradas en la sesión actual
_historial: list[dict] = []


def registrar_alerta(
    sensor: str,
    tipo: Literal["temperatura", "humedad"],
    estado: Literal["alto", "bajo"],
    valor: float,
    limite: float,
) -> None:
    """
    Registra una alerta en el historial en memoria.

    Parámetros
    ----------
    sensor  : clave del sensor tal como está definida en SENSORES
    tipo    : "temperatura" o "humedad"
    estado  : "alto" o "bajo"
    valor   : lectura que disparó la alerta
    limite  : umbral que se superó o no se alcanzó
    """
    tz = pytz.timezone(ZONA_HORARIA)
    ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

    cfg = SENSORES.get(sensor, {})
    coords = cfg.get("coordenadas", ("", "", ""))
    if isinstance(coords, (tuple, list)) and len(coords) == 3:
        coordenadas_str = f"({coords[0]},{coords[1]},{coords[2]})"
    else:
        coordenadas_str = str(coords)

    _historial.append({
        "timestamp": ts,
        "sensor": sensor,
        "coordenadas (cm)": coordenadas_str,
        "tipo": tipo,
        "estado": estado,
        "valor": round(valor, 2),
        "limite": limite,
    })


def exportar_csv_alertas() -> tuple[io.BytesIO, str]:
    """
    Exporta el historial de alertas como archivo CSV.

    Devuelve
    --------
    (buf, nombre_archivo)
        buf           : BytesIO listo para enviarse por Telegram
        nombre_archivo: nombre sugerido para el archivo
    """
    tz = pytz.timezone(ZONA_HORARIA)
    ahora = datetime.now(tz)
    ts_generado = ahora.strftime("%Y-%m-%d %H:%M:%S")
    ts_nombre   = ahora.strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"historial_alertas_{ts_nombre}.csv"

    output = io.StringIO()
    writer = csv.writer(output)

    # Cabecera de metadatos (igual al ejemplo de la imagen)
    writer.writerow(["#Historial de Alertas DHT22"])
    writer.writerow([f"#Generado: {ts_generado}"])

    # Cabecera de columnas
    writer.writerow([
        "timestamp",
        "sensor",
        "coordenadas (cm)",
        "tipo",
        "estado",
        "valor",
        "limite",
    ])

    # Filas de datos
    for entrada in _historial:
        writer.writerow([
            entrada["timestamp"],
            entrada["sensor"],
            entrada["coordenadas (cm)"],
            entrada["tipo"],
            entrada["estado"],
            entrada["valor"],
            entrada["limite"],
        ])

    buf = io.BytesIO(output.getvalue().encode("utf-8"))
    buf.seek(0)
    return buf, nombre_archivo


def total_alertas() -> int:
    """Devuelve el número de alertas registradas en la sesión actual."""
    return len(_historial)