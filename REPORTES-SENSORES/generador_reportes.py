# ============================================================
# generador_reportes.py — Genera PNG, PDF y CSV
# ============================================================
# Todas las funciones aceptan el parámetro 'sensores' con la
# lista de nombres a incluir en el reporte. Si se omite, se
# incluyen todos los definidos en SENSORES de configuracion.py.
#
# Política de gráficas:
#   - Cada sensor genera su propia imagen independiente
#     (2 subplots: temperatura arriba, humedad abajo).
#   - generar_imagenes_graficas() devuelve una lista de
#     tuplas (nombre_sensor, BytesIO) para que el bot pueda
#     enviar cada imagen por separado con su caption.
#   - El PDF inserta cada gráfica en su propia sección con
#     un salto de página entre sensores.
#
# Corrección de zona horaria:
#   matplotlib recibe objetos datetime con tzinfo pero los
#   renderiza en UTC. Se convierten a datetime naive en hora
#   local antes de graficar para que el eje X muestre la
#   hora correcta de Ciudad de México.
#
# Ejes Y fijos:
#   Temperatura: 0 – 40 °C  (marcas cada 5 °C)
#   Humedad:     0 – 100 %  (marcas cada 10 %)
# ============================================================

import io
import os
import tempfile
import statistics
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MultipleLocator
import pytz

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, Image as RLImage,
    PageBreak, KeepTogether,
)

from configuracion import SENSORES, ZONA_HORARIA

EJE_TEMP_MIN = 0
EJE_TEMP_MAX = 40
EJE_HUM_MIN  = 0
EJE_HUM_MAX  = 100

# Paleta de colores estilo Grafana oscuro para el área de datos
COLOR_FONDO_FIG   = "#181B1F"   # fondo de la figura
COLOR_FONDO_EJES  = "#1F2329"   # fondo de cada subplot
COLOR_GRID        = "#2C3038"   # líneas de cuadrícula
COLOR_TEXTO       = "#D8D9DA"   # etiquetas y títulos
COLOR_TICK        = "#9FA3A9"   # marcas del eje

# Helpers internos
def _nombres_validos(sensores: list[str] | None) -> list[str]:
    """Devuelve la lista de nombres de sensores a procesar."""
    if sensores is None:
        return list(SENSORES.keys())
    return [n for n in sensores if n in SENSORES]

def _a_local_naive(timestamps: list) -> list:
    """
    Convierte una lista de datetimes con tzinfo a datetimes
    naive en hora local (America/Mexico_City).
    matplotlib siempre muestra la hora naive tal cual,
    evitando así el desfase de 6 horas respecto a UTC.
    """
    tz = pytz.timezone(ZONA_HORARIA)
    resultado = []
    for t in timestamps:
        if t.tzinfo is not None:
            resultado.append(t.astimezone(tz).replace(tzinfo=None))
        else:
            resultado.append(t)
    return resultado

def _formato_eje_x(ax, minutos: int):
    """Configura el formateador del eje X según la duración del lapso."""
    if minutos <= 60:
        fmt      = mdates.DateFormatter("%H:%M")
        loc_may  = mdates.MinuteLocator(interval=max(1, minutos // 6))
        loc_men  = mdates.MinuteLocator(interval=max(1, minutos // 12))
    elif minutos <= 1440:
        fmt      = mdates.DateFormatter("%H:%M")
        loc_may  = mdates.HourLocator(interval=max(1, minutos // 360))
        loc_men  = mdates.MinuteLocator(interval=30)
    elif minutos <= 10080:
        fmt      = mdates.DateFormatter("%d/%m %H:%M")
        loc_may  = mdates.HourLocator(interval=12)
        loc_men  = mdates.HourLocator(interval=3)
    else:
        fmt      = mdates.DateFormatter("%d/%m")
        loc_may  = mdates.DayLocator(interval=max(1, minutos // (60 * 24 * 6)))
        loc_men  = mdates.DayLocator(interval=1)

    ax.xaxis.set_major_formatter(fmt)
    ax.xaxis.set_major_locator(loc_may)
    ax.xaxis.set_minor_locator(loc_men)
    plt.setp(ax.xaxis.get_majorticklabels(),
             rotation=30, ha="right", fontsize=9, color=COLOR_TICK)

def _estilo_ejes(ax, ylabel: str, ymin: float, ymax: float,
                 ytick_step: int, minutos: int):
    """Aplica el estilo visual oscuro tipo Grafana a un eje."""
    ax.set_facecolor(COLOR_FONDO_EJES)
    ax.set_ylim(ymin, ymax)
    ax.set_yticks(range(int(ymin), int(ymax) + 1, ytick_step))
    ax.yaxis.set_minor_locator(MultipleLocator(ytick_step / 2))
    ax.set_ylabel(ylabel, fontsize=10, color=COLOR_TEXTO, labelpad=8)
    ax.tick_params(axis="y", colors=COLOR_TICK, labelsize=9)
    ax.tick_params(axis="x", colors=COLOR_TICK)
    ax.tick_params(which="minor", length=3, color=COLOR_GRID)

    # Cuadrícula mayor y menor
    ax.grid(which="major", color=COLOR_GRID, linewidth=0.7, alpha=0.8)
    ax.grid(which="minor", color=COLOR_GRID, linewidth=0.3, alpha=0.5)

    # Bordes del subplot
    for spine in ax.spines.values():
        spine.set_edgecolor(COLOR_GRID)

    _formato_eje_x(ax, minutos)

def _grafica_un_sensor(nombre: str, actual: dict, historial: dict,
                       etiqueta: str, minutos: int, ts_str: str) -> io.BytesIO:
    """
    Genera una imagen PNG estilo Grafana con 2 subplots
    (temperatura arriba, humedad abajo) para un único sensor.
    Los timestamps se convierten a hora local naive para
    que el eje X muestre la hora correcta.
    """
    cfg    = SENSORES[nombre]
    color  = cfg["color"]
    hist   = historial.get(nombre, {})
    sensor = actual.get(nombre, {})

    fig, (ax_t, ax_h) = plt.subplots(
        2, 1, figsize=(13, 8),
        gridspec_kw={"hspace": 0.45},
    )
    fig.patch.set_facecolor(COLOR_FONDO_FIG)
    fig.suptitle(
        f"{nombre}  |  {etiqueta}  |  {ts_str}",
        fontsize=12, fontweight="bold",
        color=COLOR_TEXTO, y=0.98,
    )

    # Temperatura
    tt = _a_local_naive(hist.get("tiempos_temp", []))
    tv = hist.get("valores_temp", [])

    if tt and tv:
        ax_t.plot(tt, tv, color=color, linewidth=1.8, zorder=3, label="Temperatura")
        ax_t.fill_between(tt, tv, EJE_TEMP_MIN,
                          alpha=0.18, color=color, zorder=2)
        # Puntos en los extremos
        ax_t.scatter([tt[0], tt[-1]], [tv[0], tv[-1]],
                     color=color, s=30, zorder=4)

    _estilo_ejes(ax_t, "Temperatura (°C)",
                 EJE_TEMP_MIN, EJE_TEMP_MAX, 5, minutos)

    val_temp = sensor.get("temperatura")
    if val_temp is not None:
        ax_t.axhline(y=val_temp, color=color, linewidth=1,
                     linestyle="--", alpha=0.85, zorder=3)
        ax_t.text(
            0.01, val_temp,
            f"  Actual: {val_temp:.1f} °C",
            transform=ax_t.get_yaxis_transform(),
            color=color, fontsize=8.5, va="bottom",
        )
    if tt and tv:
        # Anotación del último valor al final de la línea
        ax_t.annotate(
            f"{tv[-1]:.1f}°C",
            xy=(tt[-1], tv[-1]),
            xytext=(6, 0), textcoords="offset points",
            color=color, fontsize=8.5, va="center",
        )

    # Leyenda
    handles = [
        plt.Line2D([0], [0], color=color, linewidth=2, label="Temperatura"),
    ]
    if val_temp is not None:
        handles.append(
            plt.Line2D([0], [0], color=color, linewidth=1,
                       linestyle="--", label=f"Actual: {val_temp:.1f} °C")
        )
    ax_t.legend(handles=handles, fontsize=8.5, loc="upper left",
                facecolor="#2C3038", edgecolor=COLOR_GRID,
                labelcolor=COLOR_TEXTO)

    # Humedad
    ht = _a_local_naive(hist.get("tiempos_hum", []))
    hv = hist.get("valores_hum", [])

    if ht and hv:
        ax_h.plot(ht, hv, color=color, linewidth=1.8,
                  linestyle="-", zorder=3, label="Humedad")
        ax_h.fill_between(ht, hv, EJE_HUM_MIN,
                          alpha=0.15, color=color, zorder=2)
        ax_h.scatter([ht[0], ht[-1]], [hv[0], hv[-1]],
                     color=color, s=30, zorder=4)

    _estilo_ejes(ax_h, "Humedad (%)",
                 EJE_HUM_MIN, EJE_HUM_MAX, 10, minutos)

    val_hum = sensor.get("humedad")
    if val_hum is not None:
        ax_h.axhline(y=val_hum, color=color, linewidth=1,
                     linestyle="--", alpha=0.85, zorder=3)
        ax_h.text(
            0.01, val_hum,
            f"  Actual: {val_hum:.1f} %",
            transform=ax_h.get_yaxis_transform(),
            color=color, fontsize=8.5, va="bottom",
        )
    if ht and hv:
        ax_h.annotate(
            f"{hv[-1]:.1f}%",
            xy=(ht[-1], hv[-1]),
            xytext=(6, 0), textcoords="offset points",
            color=color, fontsize=8.5, va="center",
        )

    handles_h = [
        plt.Line2D([0], [0], color=color, linewidth=2, label="Humedad"),
    ]
    if val_hum is not None:
        handles_h.append(
            plt.Line2D([0], [0], color=color, linewidth=1,
                       linestyle="--", label=f"Actual: {val_hum:.1f} %")
        )
    ax_h.legend(handles=handles_h, fontsize=8.5, loc="upper left",
                facecolor="#2C3038", edgecolor=COLOR_GRID,
                labelcolor=COLOR_TEXTO)

    plt.subplots_adjust(left=0.07, right=0.96, top=0.93, bottom=0.1)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150,
                bbox_inches="tight", facecolor=COLOR_FONDO_FIG)
    plt.close(fig)
    buf.seek(0)
    return buf

# PNG — una imagen por sensor
def generar_imagenes_graficas(actual: dict, historial: dict,
                              sensores: list[str] | None = None
                              ) -> list[tuple[str, io.BytesIO]]:
    """
    Genera una imagen PNG independiente por cada sensor.
    Devuelve lista de tuplas (nombre_sensor, BytesIO).
    """
    nombres    = _nombres_validos(sensores)
    tz         = pytz.timezone(ZONA_HORARIA)
    ts_str     = datetime.now(tz).strftime("%d/%m/%Y %H:%M")
    lapso_info = historial.get("lapso_info", {})
    etiqueta   = lapso_info.get("etiqueta", "")
    minutos    = lapso_info.get("minutos", 360)

    return [
        (nombre,
         _grafica_un_sensor(nombre, actual, historial, etiqueta, minutos, ts_str))
        for nombre in nombres
    ]

# PDF — gráfica de cada sensor en su propia sección
def generar_reporte_pdf(actual: dict, historial: dict,
                        sensores: list[str] | None = None) -> io.BytesIO:
    """
    Genera un reporte PDF con:
      - Encabezado general
      - Tabla de lecturas actuales y estadísticas
      - Por cada sensor: gráfica individual + tabla de registros
    """
    nombres    = _nombres_validos(sensores)
    tz         = pytz.timezone(ZONA_HORARIA)
    ahora      = datetime.now(tz)
    ts_str     = ahora.strftime("%d/%m/%Y %H:%M:%S")
    lapso_info = historial.get("lapso_info", {})
    etiqueta   = lapso_info.get("etiqueta", "")
    minutos    = lapso_info.get("minutos", 360)
    tz_str     = ahora.strftime("%d/%m/%Y %H:%M")

    # Generar y guardar gráficas en temporales
    tmp_imgs = {}
    for nombre in nombres:
        buf = _grafica_un_sensor(nombre, actual, historial,
                                 etiqueta, minutos, tz_str)
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.write(buf.read())
        tmp.close()
        tmp_imgs[nombre] = tmp.name

    buf_pdf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf_pdf, pagesize=letter,
        leftMargin=0.6*inch, rightMargin=0.6*inch,
        topMargin=0.65*inch, bottomMargin=0.65*inch,
    )

    estilos    = getSampleStyleSheet()
    est_titulo = ParagraphStyle("Titulo", parent=estilos["Title"],
                                fontSize=17, spaceAfter=4,
                                textColor=colors.HexColor("#1A1A2E"))
    est_sub    = ParagraphStyle("Sub", parent=estilos["Normal"],
                                fontSize=9, spaceAfter=10,
                                textColor=colors.HexColor("#555555"))
    est_sec    = ParagraphStyle("Sec", parent=estilos["Heading2"],
                                fontSize=11, spaceBefore=10, spaceAfter=5,
                                textColor=colors.HexColor("#16213E"))
    est_sensor = ParagraphStyle("Sensor", parent=estilos["Heading1"],
                                fontSize=13, spaceBefore=8, spaceAfter=4,
                                textColor=colors.HexColor("#0F3460"))
    est_pie    = ParagraphStyle("Pie", parent=estilos["Normal"],
                                fontSize=7, textColor=colors.grey, alignment=1)
    est_cel    = ParagraphStyle("Cel", parent=estilos["Normal"],
                                fontSize=7, leading=9)

    contenido = []

    # Encabezado
    contenido.append(Paragraph("Reporte de Sensores DHT22", est_titulo))
    contenido.append(Paragraph(
        f"Generado: {ts_str} &nbsp;|&nbsp; Periodo: {etiqueta} &nbsp;|&nbsp; "
        f"Sensores: {', '.join(nombres)}", est_sub,
    ))
    contenido.append(Table(
        [[""]],
        colWidths=[7.3*inch],
        style=TableStyle([("LINEBELOW", (0,0), (-1,-1), 1.5,
                           colors.HexColor("#4ECDC4"))]),
    ))
    contenido.append(Spacer(1, 8))

    # Lecturas actuales
    contenido.append(Paragraph("Lecturas Actuales", est_sec))
    enc   = ["Sensor", "Temperatura (°C)", "Humedad (%)", "Estado"]
    filas = [enc]
    for nombre in nombres:
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
        ("ROWBACKGROUNDS",(0,1), (-1,-1),
         [colors.HexColor("#F0F4F8"), colors.white]),
        ("GRID",          (0,0), (-1,-1), 0.4, colors.HexColor("#CCCCCC")),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    contenido.append(t_actual)
    contenido.append(Spacer(1, 10))

    # Estadísticas
    contenido.append(Paragraph(f"Estadísticas — {etiqueta}", est_sec))
    enc_s   = ["Sensor", "Métrica", "Mínimo", "Máximo",
               "Promedio", "Desv. Est.", "Registros"]
    filas_s = [enc_s]
    for nombre in nombres:
        hist = historial.get(nombre, {})
        for clave, etiq, unidad in [
            ("valores_temp", "Temperatura", "C"),
            ("valores_hum",  "Humedad",     "%"),
        ]:
            vals = hist.get(clave, [])
            if vals:
                mn  = f"{min(vals):.2f} {unidad}"
                mx  = f"{max(vals):.2f} {unidad}"
                avg = f"{sum(vals)/len(vals):.2f} {unidad}"
                std = f"{statistics.stdev(vals):.4f}" if len(vals) > 1 else "N/A"
                n   = str(len(vals))
            else:
                mn = mx = avg = std = n = "N/D"
            filas_s.append([nombre, etiq, mn, mx, avg, std, n])
    t_stats = Table(
        filas_s,
        colWidths=[1.5*inch, 1.1*inch, 1.05*inch,
                   1.05*inch, 1.05*inch, 0.9*inch, 0.9*inch],
    )
    t_stats.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), colors.HexColor("#0F3460")),
        ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,0), 8),
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("FONTSIZE",      (0,1), (-1,-1), 7.5),
        ("ROWBACKGROUNDS",(0,1), (-1,-1),
         [colors.HexColor("#EAF2FF"), colors.white]),
        ("GRID",          (0,0), (-1,-1), 0.4, colors.HexColor("#CCCCCC")),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    contenido.append(t_stats)

    # Sección por sensor
    for nombre in nombres:
        contenido.append(PageBreak())
        color_sensor = colors.HexColor(SENSORES[nombre]["color"])
        contenido.append(Paragraph(f"Sensor: {nombre}", est_sensor))
        contenido.append(Table(
            [[""]],
            colWidths=[7.3*inch],
            style=TableStyle([
                ("LINEBELOW", (0,0), (-1,-1), 2, color_sensor),
            ]),
        ))
        contenido.append(Spacer(1, 6))
        contenido.append(Paragraph("Gráfica de Tendencia", est_sec))
        contenido.append(RLImage(tmp_imgs[nombre],
                                 width=7.3*inch, height=4.5*inch))
        contenido.append(Spacer(1, 10))

        hist      = historial.get(nombre, {})
        tt        = hist.get("tiempos_temp", [])
        tv        = hist.get("valores_temp", [])
        ht        = hist.get("tiempos_hum",  [])
        hv        = hist.get("valores_hum",  [])
        registros = {}
        for t, v in zip(tt, tv):
            registros.setdefault(
                t.strftime("%Y-%m-%d %H:%M:%S"), {})["temperatura"] = v
        for t, v in zip(ht, hv):
            registros.setdefault(
                t.strftime("%Y-%m-%d %H:%M:%S"), {})["humedad"] = v

        claves_ts = sorted(registros.keys())
        if not claves_ts:
            contenido.append(Paragraph(
                "Sin registros en este periodo.", est_sub))
            continue

        contenido.append(Paragraph(
            f"Registros Completos — {len(claves_ts)} puntos", est_sec))
        contenido.append(Paragraph(
            "Todos los puntos capturados por Prometheus en el periodo.",
            ParagraphStyle("nota", parent=estilos["Normal"], fontSize=8,
                           textColor=colors.HexColor("#666666"),
                           spaceAfter=6),
        ))

        enc_r   = [
            Paragraph("<b>#</b>",           est_cel),
            Paragraph("<b>Timestamp</b>",    est_cel),
            Paragraph("<b>Temp. (°C)</b>",   est_cel),
            Paragraph("<b>Humedad (%)</b>",  est_cel),
        ]
        filas_r = [enc_r]
        for i, ts_key in enumerate(claves_ts, 1):
            reg    = registros[ts_key]
            temp_v = reg.get("temperatura")
            hum_v  = reg.get("humedad")
            filas_r.append([
                Paragraph(str(i),                                            est_cel),
                Paragraph(ts_key,                                            est_cel),
                Paragraph(f"{temp_v:.2f}" if temp_v is not None else "N/D", est_cel),
                Paragraph(f"{hum_v:.2f}"  if hum_v  is not None else "N/D", est_cel),
            ])

        t_reg = Table(
            filas_r,
            colWidths=[0.45*inch, 2.0*inch, 1.4*inch, 1.4*inch],
            repeatRows=1,
        )
        t_reg.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0), color_sensor),
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
        contenido.append(KeepTogether([t_reg]))
        contenido.append(Spacer(1, 12))

    contenido.append(Spacer(1, 8))
    contenido.append(Paragraph(
        "Generado automáticamente por el sistema de monitoreo DHT22.",
        est_pie,
    ))

    doc.build(contenido)
    buf_pdf.seek(0)
    for ruta in tmp_imgs.values():
        os.unlink(ruta)
    return buf_pdf

# CSV
def generar_csv(actual: dict, historial: dict,
                sensores: list[str] | None = None) -> tuple[io.BytesIO, str]:
    """
    Genera un CSV con todos los registros del lapso y sensores indicados.
    Devuelve (BytesIO listo para Telegram, nombre_de_archivo).
    Columnas: sensor, tipo, timestamp, valor, coordenadas.
    """
    nombres    = _nombres_validos(sensores)
    tz         = pytz.timezone(ZONA_HORARIA)
    ahora      = datetime.now(tz)
    lapso_info = historial.get("lapso_info", {})
    etiqueta   = lapso_info.get("etiqueta", "Personalizado")
    clave      = lapso_info.get("clave",    "custom")
    ts_nombre  = ahora.strftime("%Y%m%d_%H%M")

    lineas = [
        "# Exportación DHT22",
        "# Generado: " + ahora.strftime("%d/%m/%Y %H:%M:%S"),
        "# Periodo:  " + etiqueta,
        "# Sensores: " + ", ".join(nombres),
        "sensor,tipo,timestamp,valor,coordenadas(cm)",
    ]

    for nombre in nombres:
        hist = historial.get(nombre, {})
        coordenadas_dic = SENSORES[nombre].get("coordenadas")
        if coordenadas_dic is not None:
            coordenadas = f"({coordenadas_dic[0]},{coordenadas_dic[1]},{coordenadas_dic[2]})"
        else:
            coordenadas = "N/D"

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
                    + f"{v:.4f}" + ","
                    + f'"{coordenadas}"'
                )

    sufijo = "todos" if len(nombres) > 1 else nombres[0].lower().replace(" ", "_")
    buf    = io.BytesIO("\n".join(lineas).encode("utf-8"))
    buf.seek(0)
    return buf, f"dht22_{clave}_{sufijo}_{ts_nombre}.csv"