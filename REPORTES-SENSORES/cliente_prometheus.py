# ============================================================
# cliente_prometheus.py — Consultas a la API de Prometheus
# ============================================================
# Formato de métricas:
#   dht22_temperatura{sensor_id="1",microcontrolador="nodemcu_v3"} 24.20
#   dht22_humedad{sensor_id="1",microcontrolador="nodemcu_v3"}     48.00
# ============================================================

import requests
from datetime import datetime, timedelta
import pytz

from configuracion import (
    PROMETHEUS_URL, SENSORES,
    HORAS_HISTORIAL, PASO_CONSULTA, ZONA_HORARIA,
)

# ----------------------------------------------------------------
# Unidades de tiempo y sus rangos válidos
# ----------------------------------------------------------------
UNIDADES = {
    "m":  ("minutos",  1,      44640),   # 5 min mínimo, ~31 días máximo
    "h":  ("horas",    1,      744),     # 1 h  mínimo, ~31 días máximo
    "d":  ("días",     1,      365),
    "w":  ("semanas",  1,      52),
    "mo": ("meses",    1,      12),
    "y":  ("años",     1,      5),
}

# Minutos por unidad (para convertir a minutos)
MINUTOS_POR_UNIDAD = {
    "m":  1,
    "h":  60,
    "d":  1440,
    "w":  10080,
    "mo": 43200,
    "y":  525600,
}

# Paso de muestreo según la cantidad de minutos totales
def _paso_para_minutos(minutos: int) -> str:
    if minutos <= 60:
        return "15s"
    elif minutos <= 360:
        return "1m"
    elif minutos <= 1440:
        return "2m"
    elif minutos <= 4320:
        return "5m"
    elif minutos <= 10080:
        return "10m"
    elif minutos <= 43200:
        return "30m"
    else:
        return "2h"


def _consulta_instantanea(metrica: str,
                           sensor_id: str,
                           microcontrolador: str) -> float | None:
    """Devuelve el valor actual de una métrica."""
    query = f'{metrica}{{sensor_id="{sensor_id}",microcontrolador="{microcontrolador}"}}'
    try:
        r = requests.get(f"{PROMETHEUS_URL}/api/v1/query",
                         params={"query": query}, timeout=5)
        r.raise_for_status()
        resultados = r.json().get("data", {}).get("result", [])
        if resultados:
            return float(resultados[0]["value"][1])
        return None
    except Exception as e:
        print(f"[Prometheus] Error consulta instantánea ({metrica}): {e}")
        return None


def _consulta_rango(metrica: str,
                    sensor_id: str,
                    microcontrolador: str,
                    minutos_atras: int,
                    paso: str):
    """Consulta una serie de tiempo. Devuelve (timestamps[], valores[])."""
    tz     = pytz.timezone(ZONA_HORARIA)
    fin    = datetime.now(tz)
    inicio = fin - timedelta(minutes=minutos_atras)
    query  = f'{metrica}{{sensor_id="{sensor_id}",microcontrolador="{microcontrolador}"}}'
    try:
        r = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            params={"query": query,
                    "start": inicio.timestamp(),
                    "end":   fin.timestamp(),
                    "step":  paso},
            timeout=10,
        )
        r.raise_for_status()
        resultados = r.json().get("data", {}).get("result", [])
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
# Detección del primer registro disponible
# ----------------------------------------------------------------

# Gap máximo (minutos) entre puntos para considerarlos CONTINUOS.
# Gaps más grandes = interrupción real del sensor.
_GAP_MAX_MINUTOS = 15


def _primer_timestamp_real(query: str, tz) -> "datetime | None":
    """
    Obtiene el timestamp EXACTO del primer registro almacenado en
    Prometheus para la métrica indicada.

    Estrategia en 2 pasos para no sobrecargar Prometheus:

    Paso A — consulta instantánea con min_over_time[730d]:
      Devuelve UN solo punto numérico = el valor mínimo de los últimos
      2 años. No transfiere series completas. Si Prometheus tiene el
      primer registro real dentro de 730 días, lo encontramos aquí
      en < 1 segundo.

    Paso B (fallback) — búsqueda binaria con bloques:
      Si el método A falla, divide el rango en ~30 bloques y localiza
      el bloque más antiguo que contiene datos, luego afina con paso
      fino dentro de ese bloque.
    """
    ahora  = datetime.now(tz)
    hace2a = ahora - timedelta(days=730)

    # ── Paso A: /api/v1/query con min_over_time ─────────────────
    # Usamos `min_over_time` en lugar de `timestamp` porque Prometheus
    # no tiene una función nativa "primer timestamp". En su lugar
    # pedimos el mínimo de la serie en 730 días con paso vacío.
    # Para obtener el timestamp real usamos query_range con ventana
    # completa pero paso GRANDE (1 día) — solo queremos el primer
    # punto alineado al día, luego lo afinamos.
    try:
        r = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            params={
                "query": query,
                "start": hace2a.timestamp(),
                "end":   ahora.timestamp(),
                "step":  "1d",          # ~730 puntos máximo, muy liviano
            },
            timeout=10,
        )
        r.raise_for_status()
        res = r.json().get("data", {}).get("result", [])
        if res and res[0]["values"]:
            # El primer valor puede estar alineado al día, no al minuto exacto.
            # Guardamos el día del primer punto y lo afinamos en Paso B.
            primer_ts_dia = float(res[0]["values"][0][0])
            primer_dia    = datetime.fromtimestamp(primer_ts_dia, tz)

            # Afinar: consulta de ese día ± 1 día con paso de 1 min
            inicio_fino = primer_dia - timedelta(hours=1)
            fin_fino    = primer_dia + timedelta(days=2)
            if fin_fino > ahora:
                fin_fino = ahora
            r2 = requests.get(
                f"{PROMETHEUS_URL}/api/v1/query_range",
                params={
                    "query": query,
                    "start": inicio_fino.timestamp(),
                    "end":   fin_fino.timestamp(),
                    "step":  "1m",
                },
                timeout=10,
            )
            r2.raise_for_status()
            res2 = r2.json().get("data", {}).get("result", [])
            if res2 and res2[0]["values"]:
                primer_ts_exacto = float(res2[0]["values"][0][0])
                dt = datetime.fromtimestamp(primer_ts_exacto, tz)
                if hace2a <= dt <= ahora:
                    return dt
            # Si la afinación falla, devolvemos el día aproximado
            return primer_dia
    except Exception as e:
        print(f"[Prometheus] Paso A fallido: {e}")

    # ── Paso B: búsqueda binaria en bloques ─────────────────────
    ventanas_min = [
        60, 360, 1440, 4320, 10080, 20160,
        43200, 129600, 262800, 525600, 1051200,
    ]
    ventana_max = None
    for v in ventanas_min:
        inicio_v = ahora - timedelta(minutes=v)
        try:
            r = requests.get(
                f"{PROMETHEUS_URL}/api/v1/query_range",
                params={
                    "query": query,
                    "start": inicio_v.timestamp(),
                    "end":   ahora.timestamp(),
                    "step":  f"{max(v // 2, 1)}m",
                },
                timeout=6,
            )
            r.raise_for_status()
            res = r.json().get("data", {}).get("result", [])
            if res and res[0]["values"]:
                ventana_max = v
        except Exception:
            pass

    if ventana_max is None:
        return None

    # Dividir en ~30 bloques y localizar el más antiguo con datos
    bloque_min = max(ventana_max // 30, 60)
    primer_dt  = ahora
    n_bloques  = ventana_max // bloque_min
    for i in range(n_bloques, -1, -1):
        fin_b   = ahora - timedelta(minutes=i * bloque_min)
        ini_b   = fin_b - timedelta(minutes=bloque_min)
        lim_ini = ahora - timedelta(minutes=ventana_max)
        if ini_b < lim_ini:
            ini_b = lim_ini
        try:
            r = requests.get(
                f"{PROMETHEUS_URL}/api/v1/query_range",
                params={
                    "query": query,
                    "start": ini_b.timestamp(),
                    "end":   fin_b.timestamp(),
                    "step":  f"{max(bloque_min // 5, 1)}m",
                },
                timeout=6,
            )
            r.raise_for_status()
            res = r.json().get("data", {}).get("result", [])
            if res and res[0]["values"]:
                ts_b = datetime.fromtimestamp(float(res[0]["values"][0][0]), tz)
                if ts_b < primer_dt:
                    primer_dt = ts_b
        except Exception:
            pass

    return primer_dt if primer_dt < ahora else None


def _minutos_disponibles_para_sensor(sid: str, mc: str, tz) -> int:
    """
    Devuelve los minutos transcurridos desde el PRIMER REGISTRO REAL
    del sensor hasta ahora. Las desconexiones intermedias se ignoran:
    el historial disponible es desde el primer punto hasta el presente.
    Los gaps se rellenan en obtener_historial_por_minutos con el último
    valor conocido (forward-fill).
    """
    ahora = datetime.now(tz)
    query = (f'dht22_temperatura{{sensor_id="{sid}",'
             f'microcontrolador="{mc}"}}')

    primer_dt = _primer_timestamp_real(query, tz)
    if primer_dt is None:
        print(f"[Prometheus] Sin historial para sid={sid} mc={mc}")
        return 60

    minutos_totales = int((ahora - primer_dt).total_seconds() / 60)
    minutos_totales = max(minutos_totales, 5)
    print(f"[Prometheus] sid={sid} mc={mc}: primer registro hace "
          f"{minutos_totales} min ({primer_dt.strftime('%d/%m/%Y %H:%M')})")
    return minutos_totales


def obtener_minutos_disponibles(nombres_sensores: list[str] | None = None) -> int:
    """
    Devuelve los minutos de historial disponibles desde el PRIMER REGISTRO
    REAL de cada sensor hasta ahora, tomando el mínimo entre todos los
    sensores consultados (el más restrictivo).

    Las desconexiones intermedias se ignoran; los gaps se rellenan
    con el último valor conocido al construir el historial.
    """
    tz      = pytz.timezone(ZONA_HORARIA)
    nombres = nombres_sensores if nombres_sensores else list(SENSORES.keys())
    minutos_minimo = None

    for nombre in nombres:
        if nombre not in SENSORES:
            continue
        cfg = SENSORES[nombre]
        sid = cfg["label_sensor_id"]
        mc  = cfg["label_microcontrolador"]

        minutos_sensor = _minutos_disponibles_para_sensor(sid, mc, tz)
        print(f"[Prometheus] {nombre}: {minutos_sensor} min disponibles")

        if minutos_minimo is None or minutos_sensor < minutos_minimo:
            minutos_minimo = minutos_sensor

    return minutos_minimo if minutos_minimo else 60


# ----------------------------------------------------------------
# API pública
# ----------------------------------------------------------------

def obtener_lecturas_actuales(sensores: list[str] | None = None) -> dict:
    """Devuelve los valores actuales de los sensores indicados."""
    nombres = sensores if sensores is not None else list(SENSORES.keys())
    datos   = {"timestamp": datetime.now(pytz.timezone(ZONA_HORARIA))}
    for nombre in nombres:
        if nombre not in SENSORES:
            continue
        cfg  = SENSORES[nombre]
        sid  = cfg["label_sensor_id"]
        mc   = cfg["label_microcontrolador"]
        temp = _consulta_instantanea(cfg["metrica_temp"], sid, mc)
        hum  = _consulta_instantanea(cfg["metrica_hum"],  sid, mc)
        datos[nombre] = {"temperatura": temp, "humedad": hum}
    return datos



def _forward_fill(
    timestamps: list,
    valores: list,
    minutos_rango: int,
    paso: str,
    tz,
) -> tuple:
    """
    Rellena los huecos de una serie temporal con el último valor
    conocido (forward-fill / zero-order hold).

    Si Prometheus no tiene datos para un slot de tiempo (porque el
    sensor estuvo desconectado), se repite el último valor válido
    hasta que aparezca un dato nuevo. Si el slot es anterior al
    primer registro, se deja sin rellenar (no se inventa nada antes
    del arranque del sensor).

    Parámetros
    ----------
    timestamps : lista de datetime con tz
    valores    : lista de float paralela a timestamps
    minutos_rango : cuántos minutos hacia atrás cubre la consulta
    paso       : string de paso de Prometheus (ej. "1m", "5m", "2h")
    tz         : zona horaria

    Retorna (timestamps_rellenos, valores_rellenos)
    """
    if not timestamps:
        return timestamps, valores

    # Convertir el paso a segundos
    _PASO_SEG = {
        "15s": 15, "30s": 30,
        "1m": 60, "2m": 120, "5m": 300, "10m": 600,
        "15m": 900, "30m": 1800,
        "1h": 3600, "2h": 7200, "4h": 14400,
        "6h": 21600, "12h": 43200, "1d": 86400,
    }
    paso_seg = _PASO_SEG.get(paso)
    if paso_seg is None:
        # Intentar parsear "Nm" o "Nh"
        try:
            if paso.endswith("m"):
                paso_seg = int(paso[:-1]) * 60
            elif paso.endswith("h"):
                paso_seg = int(paso[:-1]) * 3600
            elif paso.endswith("s"):
                paso_seg = int(paso[:-1])
            elif paso.endswith("d"):
                paso_seg = int(paso[:-1]) * 86400
            else:
                return timestamps, valores   # no reconocido, devolver sin cambios
        except ValueError:
            return timestamps, valores

    ahora      = datetime.now(tz)
    fin_rango  = ahora
    ini_rango  = ahora - timedelta(minutes=minutos_rango)

    # El primer punto real marca el inicio del sensor; no rellenamos antes
    primer_real = timestamps[0]
    inicio_grid = max(ini_rango, primer_real)

    # Construir grid uniforme
    grid = []
    t    = inicio_grid
    while t <= fin_rango + timedelta(seconds=paso_seg // 2):
        grid.append(t)
        t += timedelta(seconds=paso_seg)

    if not grid:
        return timestamps, valores

    # Índice de búsqueda en la serie original (ordenada por tiempo)
    resultado_ts  = []
    resultado_val = []
    ultimo_val    = None
    j             = 0   # puntero en timestamps originales

    for slot in grid:
        # Avanzar j hasta el último punto original <= slot
        while j < len(timestamps) and timestamps[j] <= slot + timedelta(seconds=paso_seg // 2):
            ultimo_val = valores[j]
            j += 1

        if ultimo_val is not None:
            resultado_ts.append(slot)
            resultado_val.append(ultimo_val)
        # Si aún no hay ningún punto anterior al slot, lo omitimos
        # (no inventamos datos antes del primer registro real)

    return resultado_ts, resultado_val


def obtener_historial_por_minutos(minutos: int,
                                   sensores: list[str] | None = None) -> dict:
    """
    Devuelve el historial para exactamente `minutos` minutos hacia atrás.
    El paso de muestreo se calcula automáticamente según la cantidad.

    Estructura de retorno:
    {
        "nombre_sensor": {
            "tiempos_temp": [...], "valores_temp": [...],
            "tiempos_hum":  [...], "valores_hum":  [...],
        },
        "lapso_info": {"minutos": int, "etiqueta": str}
    }
    """
    nombres = sensores if sensores is not None else list(SENSORES.keys())
    paso    = _paso_para_minutos(minutos)

    # Construir etiqueta legible
    if minutos < 60:
        etiqueta = f"Últimos {minutos} minutos"
    elif minutos < 1440:
        h = minutos // 60
        etiqueta = f"Últimas {h} hora{'s' if h > 1 else ''}"
    elif minutos < 10080:
        d = minutos // 1440
        etiqueta = f"Últimos {d} día{'s' if d > 1 else ''}"
    elif minutos < 43200:
        w = minutos // 10080
        etiqueta = f"Últimas {w} semana{'s' if w > 1 else ''}"
    elif minutos < 525600:
        mo = minutos // 43200
        etiqueta = f"Últimos {mo} mes{'es' if mo > 1 else ''}"
    else:
        y = minutos // 525600
        etiqueta = f"Últimos {y} año{'s' if y > 1 else ''}"

    historial = {
        "lapso_info": {"minutos": minutos, "etiqueta": etiqueta, "clave": "custom"}
    }

    tz = pytz.timezone(ZONA_HORARIA)

    for nombre in nombres:
        if nombre not in SENSORES:
            continue
        cfg    = SENSORES[nombre]
        sid    = cfg["label_sensor_id"]
        mc     = cfg["label_microcontrolador"]
        tt, tv = _consulta_rango(cfg["metrica_temp"], sid, mc, minutos, paso)
        ht, hv = _consulta_rango(cfg["metrica_hum"],  sid, mc, minutos, paso)

        # ── Forward-fill: rellenar gaps con el último valor conocido ──
        # Genera una serie temporal uniforme desde el primer punto hasta
        # ahora con el paso calculado, y para cada slot sin dato usa
        # el último valor registrado antes de ese momento.
        tt, tv = _forward_fill(tt, tv, minutos, paso, tz)
        ht, hv = _forward_fill(ht, hv, minutos, paso, tz)

        historial[nombre] = {
            "tiempos_temp": tt, "valores_temp": tv,
            "tiempos_hum":  ht, "valores_hum":  hv,
        }

    return historial


# Mantener compatibilidad con llamadas anteriores que usen obtener_historial
def obtener_historial(clave_lapso: str = "6h",
                      sensores: list[str] | None = None) -> dict:
    """
    Wrapper de compatibilidad. Convierte la clave de lapso
    a minutos y llama a obtener_historial_por_minutos.
    """
    LAPSOS_COMPAT = {
        "5m": 5, "15m": 15, "30m": 30, "1h": 60, "3h": 180,
        "6h": 360, "12h": 720, "24h": 1440, "2d": 2880,
        "1w": 10080, "1mo": 43200,
    }
    minutos = LAPSOS_COMPAT.get(clave_lapso, 360)
    return obtener_historial_por_minutos(minutos, sensores)
