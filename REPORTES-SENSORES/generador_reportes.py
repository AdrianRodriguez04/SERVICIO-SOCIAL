# ============================================================
# generador_reportes.py — Genera PNG (grafica) y PDF (reporte)
# ============================================================

import io
import os
import tempfile
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pytz

from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, Image as RLImage, PageBreak,
    KeepTogether,
)

from configuracion import SENSORES, ZONA_HORARIA

# Ejes fijos para todas las graficas
EJE_TEMP_MIN = 0
EJE_TEMP_MAX = 40
EJE_HUM_MIN  = 0
EJE_HUM_MAX  = 100


def _formato_eje_x(ax, minutos: int):
    """Ajusta el formateador del eje X segun el lapso."""
    if minutos <= 60:
        fmt   = mdates.DateFormatter("%H:%M")
        loc   = mdates.MinuteLocator(interval=max(1, minutos // 6))
    elif minutos <= 1440:
        fmt   = mdates.DateFormatter("%H:%M")
        loc   = mdates.HourLocator(interval=max(1, minutos // 360))
    elif minutos <= 10080:
        fmt   = mdates.DateFormatter("%d/%m %H:%M")
        loc   = mdates.HourLocator(interval=12)
    else:
        fmt   = mdates.DateFormatter("%d/%m")
        loc   = mdates.DayLocator(interval=max(1, minutos // (60*24*6)))
    ax.xaxis.set_major_formatter(fmt)
    ax.xaxis.set_major_locator(loc)
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")


# ----------------------------------------------------------------
# PNG
# ----------------------------------------------------------------

def generar_imagen_grafica(actual: dict, historial: dict) -> io.BytesIO:
    """
    Genera imagen PNG con 4 subplots (2 sensores x 2 metricas).
    Ejes Y fijos: temp 0-40 C, humedad 0-100 %.
    """
    tz         = pytz.timezone(ZONA_HORARIA)
    ts_str     = datetime.now(tz).strftime("%d/%m/%Y %H:%M")
    lapso_info = historial.get("lapso_info", {})
    etiqueta   = lapso_info.get("etiqueta", "")
    minutos    = lapso_info.get("minutos", 360)

    fig, ejes = plt.subplots(2, 2, figsize=(14, 8))
    fig.suptitle(
        f"Monitoreo DHT22 — {ts_str}  ({etiqueta})",
        fontsize=14, fontweight="bold", color="#333333"
    )
    fig.patch.set_facecolor("#F8F9FA")

    nombres = list(SENSORES.keys())

    for col, nombre in enumerate(nombres):
        cfg    = SENSORES[nombre]
        color  = cfg["color"]
        hist   = historial.get(nombre, {})
        sensor = actual.get(nombre, {})

        # --- Temperatura (fila 0) ---
        ax_t = ejes[0][col]
        tt = hist.get("tiempos_temp", [])
        tv = hist.get("valores_temp", [])
        if tt and tv:
            ax_t.plot(tt, tv, color=color, linewidth=2, label="Temperatura")
            ax_t.fill_between(tt, tv, alpha=0.15, color=color)
        ax_t.set_title(nombre, fontsize=11, fontweight="bold", color="#444")
        ax_t.set_ylabel("Temperatura (°C)", fontsize=9)
        ax_t.set_ylim(EJE_TEMP_MIN, EJE_TEMP_MAX)
        ax_t.set_yticks(range(EJE_TEMP_MIN, EJE_TEMP_MAX + 1, 5))
        _formato_eje_x(ax_t, minutos)
        ax_t.grid(True, alpha=0.3)
        ax_t.set_facecolor("#FFFFFF")
        if sensor.get("temperatura") is not None:
            ax_t.axhline(
                y=sensor["temperatura"],
                color=color, linestyle="--", alpha=0.7,
                label=f"Actual: {sensor['temperatura']:.1f}°C"
            )
        ax_t.legend(fontsize=8, loc="upper left")

        # --- Humedad (fila 1) ---
        ax_h = ejes[1][col]
        ht = hist.get("tiempos_hum", [])
        hv = hist.get("valores_hum", [])
        if ht and hv:
            ax_h.plot(ht, hv, color=color, linewidth=2, linestyle="--", label="Humedad")
            ax_h.fill_between(ht, hv, alpha=0.12, color=color)
        ax_h.set_ylabel("Humedad (%)", fontsize=9)
        ax_h.set_ylim(EJE_HUM_MIN, EJE_HUM_MAX)
        ax_h.set_yticks(range(EJE_HUM_MIN, EJE_HUM_MAX + 1, 10))
        _formato_eje_x(ax_h, minutos)
        ax_h.grid(True, alpha=0.3)
        ax_h.set_facecolor("#FFFFFF")
        if sensor.get("humedad") is not None:
            ax_h.axhline(
                y=sensor["humedad"],
                color=color, linestyle=":", alpha=0.7,
                label=f"Actual: {sensor['humedad']:.1f}%"
            )
        ax_h.legend(fontsize=8, loc="upper left")

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


# ----------------------------------------------------------------
# PDF
# ----------------------------------------------------------------

def generar_reporte_pdf(actual: dict, historial: dict) -> io.BytesIO:
    """
    Genera PDF con:
      - Encabezado y resumen del lapso
      - Lecturas actuales
      - Estadisticas del lapso
      - Tabla COMPLETA de todos los registros del lapso (paginada)
      - Grafica embebida
    """
    tz         = pytz.timezone(ZONA_HORARIA)
    ahora      = datetime.now(tz)
    ts_str     = ahora.strftime("%d/%m/%Y %H:%M:%S")
    lapso_info = historial.get("lapso_info", {})
    etiqueta   = lapso_info.get("etiqueta", "")

    # Grafica temporal
    buf_grafica = generar_imagen_grafica(actual, historial)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.write(buf_grafica.read())
    tmp.close()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.6*inch, rightMargin=0.6*inch,
        topMargin=0.65*inch, bottomMargin=0.65*inch,
    )

    estilos = getSampleStyleSheet()
    est_titulo = ParagraphStyle(
        "Titulo", parent=estilos["Title"],
        fontSize=17, spaceAfter=4,
        textColor=colors.HexColor("#1A1A2E"),
    )
    est_sub = ParagraphStyle(
        "Sub", parent=estilos["Normal"],
        fontSize=9, spaceAfter=10,
        textColor=colors.HexColor("#555555"),
    )
    est_sec = ParagraphStyle(
        "Sec", parent=estilos["Heading2"],
        fontSize=11, spaceBefore=10, spaceAfter=5,
        textColor=colors.HexColor("#16213E"),
    )
    est_pie = ParagraphStyle(
        "Pie", parent=estilos["Normal"],
        fontSize=7, textColor=colors.grey, alignment=1
    )
    est_cel = ParagraphStyle(
        "Cel", parent=estilos["Normal"],
        fontSize=7, leading=9,
    )

    contenido = []

    # ---- Encabezado ----
    contenido.append(Paragraph("Reporte de Sensores DHT22", est_titulo))
    contenido.append(Paragraph(
        f"Generado: {ts_str} &nbsp;&nbsp;|&nbsp;&nbsp; Periodo: {etiqueta}", est_sub
    ))
    contenido.append(Table(
        [[""]],
        colWidths=[7.3*inch],
        style=TableStyle([("LINEBELOW", (0,0), (-1,-1), 1.5, colors.HexColor("#4ECDC4"))]),
    ))
    contenido.append(Spacer(1, 8))

    # ---- Lecturas actuales ----
    contenido.append(Paragraph("Lecturas Actuales", est_sec))
    enc = ["Sensor", "Temperatura (°C)", "Humedad (%)", "Estado"]
    filas = [enc]
    for nombre in SENSORES.keys():
        s    = actual.get(nombre, {})
        tmp_ = s.get("temperatura")
        hum  = s.get("humedad")
        if tmp_ is None or hum is None:
            estado = "Sin datos"
        elif tmp_ > 35 or hum > 80:
            estado = "Alto"
        elif tmp_ < 10 or hum < 25:
            estado = "Bajo"
        else:
            estado = "Normal"
        filas.append([
            nombre,
            f"{tmp_:.2f}" if tmp_ is not None else "N/D",
            f"{hum:.2f}"  if hum  is not None else "N/D",
            estado,
        ])
    t_actual = Table(filas, colWidths=[2.1*inch, 1.9*inch, 1.7*inch, 1.6*inch])
    t_actual.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), colors.HexColor("#16213E")),
        ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,0), 9),
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("FONTSIZE",      (0,1), (-1,-1), 9),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.HexColor("#F0F4F8"), colors.white]),
        ("GRID",          (0,0), (-1,-1), 0.4, colors.HexColor("#CCCCCC")),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    contenido.append(t_actual)
    contenido.append(Spacer(1, 10))

    # ---- Estadisticas ----
    contenido.append(Paragraph(f"Estadisticas — {etiqueta}", est_sec))
    enc_s = ["Sensor", "Metrica", "Minimo", "Maximo", "Promedio", "Desv. Est.", "Registros"]
    filas_s = [enc_s]
    for nombre in SENSORES.keys():
        hist = historial.get(nombre, {})
        for clave, etiq, unidad in [
            ("valores_temp", "Temperatura", "C"),
            ("valores_hum",  "Humedad",     "%"),
        ]:
            vals = hist.get(clave, [])
            if vals:
                import statistics
                mn  = f"{min(vals):.2f} {unidad}"
                mx  = f"{max(vals):.2f} {unidad}"
                avg = f"{sum(vals)/len(vals):.2f} {unidad}"
                std = f"{statistics.stdev(vals):.4f}" if len(vals) > 1 else "N/A"
                n   = str(len(vals))
            else:
                mn = mx = avg = std = n = "N/D"
            filas_s.append([nombre, etiq, mn, mx, avg, std, n])
    t_stats = Table(filas_s,
                    colWidths=[1.5*inch, 1.1*inch, 1.05*inch, 1.05*inch, 1.05*inch, 0.9*inch, 0.9*inch])
    t_stats.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), colors.HexColor("#0F3460")),
        ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,0), 8),
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("FONTSIZE",      (0,1), (-1,-1), 7.5),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.HexColor("#EAF2FF"), colors.white]),
        ("GRID",          (0,0), (-1,-1), 0.4, colors.HexColor("#CCCCCC")),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LINEBELOW",     (0,2), (-1,2), 1, colors.HexColor("#4ECDC4")),
    ]))
    contenido.append(t_stats)
    contenido.append(Spacer(1, 10))

    # ---- Grafica ----
    contenido.append(Paragraph("Graficas de Tendencia", est_sec))
    contenido.append(RLImage(tmp.name, width=7.3*inch, height=4.1*inch))
    contenido.append(Spacer(1, 6))

    # ---- Tabla COMPLETA de registros ----
    contenido.append(PageBreak())
    contenido.append(Paragraph(
        f"Registros Completos — {etiqueta}", est_sec
    ))
    contenido.append(Paragraph(
        "Todos los puntos de datos capturados por Prometheus en el periodo seleccionado.",
        ParagraphStyle("nota", parent=estilos["Normal"], fontSize=8,
                       textColor=colors.HexColor("#666666"), spaceAfter=6)
    ))

    # Construir tabla por sensor
    for nombre in SENSORES.keys():
        hist    = historial.get(nombre, {})
        tt      = hist.get("tiempos_temp", [])
        tv      = hist.get("valores_temp", [])
        ht      = hist.get("tiempos_hum",  [])
        hv      = hist.get("valores_hum",  [])

        # Alinear por timestamp: construir dict ts -> {temp, hum}
        registros = {}
        for t, v in zip(tt, tv):
            key = t.strftime("%Y-%m-%d %H:%M:%S")
            registros.setdefault(key, {})["temperatura"] = v
        for t, v in zip(ht, hv):
            key = t.strftime("%Y-%m-%d %H:%M:%S")
            registros.setdefault(key, {})["humedad"] = v

        # Ordenar por tiempo
        claves_ts = sorted(registros.keys())

        if not claves_ts:
            contenido.append(Paragraph(
                f"  {nombre}: sin registros en este periodo.", est_sub
            ))
            continue

        # Encabezado de la tabla de registros
        enc_r  = [
            Paragraph("<b>#</b>",            est_cel),
            Paragraph("<b>Timestamp</b>",     est_cel),
            Paragraph("<b>Temp. (°C)</b>",    est_cel),
            Paragraph("<b>Humedad (%)</b>",   est_cel),
        ]
        filas_r = [enc_r]
        for i, ts_key in enumerate(claves_ts, 1):
            reg  = registros[ts_key]
            temp_v = reg.get("temperatura")
            hum_v  = reg.get("humedad")
            filas_r.append([
                Paragraph(str(i),                                                   est_cel),
                Paragraph(ts_key,                                                   est_cel),
                Paragraph(f"{temp_v:.2f}" if temp_v is not None else "N/D",        est_cel),
                Paragraph(f"{hum_v:.2f}"  if hum_v  is not None else "N/D",        est_cel),
            ])

        t_reg = Table(
            filas_r,
            colWidths=[0.45*inch, 2.0*inch, 1.4*inch, 1.4*inch],
            repeatRows=1,
        )

        # Color de fondo de encabezado segun sensor
        color_enc = colors.HexColor(SENSORES[nombre]["color"])

        t_reg.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0), color_enc),
            ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
            ("FONTSIZE",      (0,0), (-1,0), 7.5),
            ("ALIGN",         (0,0), (-1,-1), "CENTER"),
            ("FONTSIZE",      (0,1), (-1,-1), 7),
            ("ROWBACKGROUNDS",(0,1), (-1,-1),
             [colors.HexColor("#F9F9F9"), colors.white]),
            ("GRID",          (0,0), (-1,-1), 0.3, colors.HexColor("#DDDDDD")),
            ("TOPPADDING",    (0,0), (-1,-1), 3),
            ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ]))

        titulo_sensor = Paragraph(
            f"Sensor: <b>{nombre}</b> &nbsp;—&nbsp; {len(claves_ts)} registros",
            ParagraphStyle("ts", parent=estilos["Normal"],
                           fontSize=9, spaceBefore=10, spaceAfter=4,
                           textColor=colors.HexColor("#16213E"))
        )
        contenido.append(KeepTogether([titulo_sensor]))
        contenido.append(t_reg)
        contenido.append(Spacer(1, 12))

    # ---- Pie ----
    contenido.append(Spacer(1, 8))
    contenido.append(Paragraph(
        "Generado automaticamente por el bot de monitoreo DHT22 · NodeMCU V3 &amp; ESP32-C3",
        est_pie
    ))

    doc.build(contenido)
    buf.seek(0)
    os.unlink(tmp.name)
    return buf

# ----------------------------------------------------------------
# CSV — exportación de todos los registros del lapso
# ----------------------------------------------------------------

def generar_csv(actual: dict, historial: dict) -> tuple[io.BytesIO, str]:
    """
    Genera un CSV con todos los registros del lapso seleccionado.
    Devuelve (BytesIO listo para Telegram, nombre_de_archivo).

    Columnas:
        sensor     — nombre del sensor
        tipo       — 'temperatura_C' o 'humedad_pct'
        timestamp  — fecha y hora local (YYYY-MM-DD HH:MM:SS)
        valor      — lectura numérica con 4 decimales
    """
    tz         = pytz.timezone(ZONA_HORARIA)
    ahora      = datetime.now(tz)
    lapso_info = historial.get("lapso_info", {})
    etiqueta   = lapso_info.get("etiqueta", "Personalizado")
    clave      = lapso_info.get("clave",    "custom")
    ts_nombre  = ahora.strftime("%Y%m%d_%H%M")

    lineas = [
        "# Exportacion DHT22",
        "# Generado: " + ahora.strftime("%d/%m/%Y %H:%M:%S"),
        "# Periodo:  " + etiqueta,
        "# Sensores: " + ", ".join(SENSORES.keys()),
        "sensor,tipo,timestamp,valor",
    ]

    for nombre in SENSORES.keys():
        hist = historial.get(nombre, {})
        for clave_t, clave_v, tipo in [
            ("tiempos_temp", "valores_temp", "temperatura_C"),
            ("tiempos_hum",  "valores_hum",  "humedad_pct"),
        ]:
            tiempos = hist.get(clave_t, [])
            valores = hist.get(clave_v, [])
            for t, v in zip(tiempos, valores):
                lineas.append(
                    f'"{nombre}",'
                    + tipo + ","
                    + t.strftime("%Y-%m-%d %H:%M:%S") + ","
                    + f"{v:.4f}"
                )

    buf = io.BytesIO("\n".join(lineas).encode("utf-8"))
    buf.seek(0)
    return buf, f"dht22_{clave}_{ts_nombre}.csv"
