# ============================================================
# bot_telegram.py — Bot principal con comandos
# ============================================================
# Comandos disponibles:
#   /start   — Bienvenida e instrucciones
#   /status  — Lecturas actuales de todos los sensores
#   /png — Selecciona periodo y sensor → imagen PNG
#   /pdf — Selecciona periodo y sensor → PDF completo
#   /csv     — Selecciona periodo y sensor → archivo CSV
#   /alerts — Activar o desactivar alertas automáticas
#   /help   — Lista de comandos disponibles
#
# Flujo de selección:
#   1. Usuario ejecuta /grafica (o /reporte o /csv)
#   2. El bot pregunta el periodo de tiempo (11 opciones)
#   3. El bot pregunta el sensor (opciones dinámicas según SENSORES)
#   4. El bot genera y envía el archivo solicitado
#   5. El bot ofrece consultar otro periodo sin necesidad de
#      volver a escribir el comando
# ============================================================

import logging
import os.path
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

from configuracion import (
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, ZONA_HORARIA, SENSORES,
    ALERTA_TEMP_MAX, ALERTA_TEMP_MIN,
    ALERTA_HUM_MAX,  ALERTA_HUM_MIN,
    ALERTAS_ACTIVAS,
)
from cliente_prometheus import obtener_lecturas_actuales, obtener_historial, LAPSOS
from generador_reportes  import generar_imagenes_graficas, generar_reporte_pdf, generar_csv

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

alertas_activas = ALERTAS_ACTIVAS

# ----------------------------------------------------------------
# Prefijos de callback — se mantienen cortos para respetar el
# límite de 64 bytes que impone la API de Telegram.
# Flujo: "t:TIPO|l:LAPSO" → luego "s:TIPO|l:LAPSO|n:SENSOR_IDX"
# TIPO: g=grafica, r=reporte, c=csv
# ----------------------------------------------------------------
PRE_LAPSO  = "l:"   # primer paso: selección de lapso
PRE_SENSOR = "s:"   # segundo paso: selección de sensor

# Mapa de tipo corto a nombre largo (para logs y mensajes)
TIPO_NOMBRE = {"g": "gráfica", "r": "reporte PDF", "c": "CSV"}

# Índice numérico de sensores para mantener callbacks cortos
# Ej: 0=NodeMCU V3, 1=NodeMCU V3 2, 2=ESP32-C3, 99=Todos
TODOS_IDX = 99
_SENSORES_LISTA = list(SENSORES.keys())

def _sensor_por_idx(idx: int) -> list[str]:
    """Devuelve lista de nombres de sensores según el índice elegido."""
    if idx == TODOS_IDX:
        return _SENSORES_LISTA
    return [_SENSORES_LISTA[idx]]

# Construcción de teclados inline

def _teclado_lapsos(tipo: str) -> InlineKeyboardMarkup:
    """
    Teclado de selección de periodo.
    callback_data = "l:TIPO|CLAVE_LAPSO"   (ej. "l:g|6h")
    """
    botones = []
    fila    = []
    for clave, (etiq, _, _) in LAPSOS.items():
        dato = f"{PRE_LAPSO}{tipo}|{clave}"
        fila.append(InlineKeyboardButton(etiq, callback_data=dato))
        if len(fila) == 2:
            botones.append(fila)
            fila = []
    if fila:
        botones.append(fila)
    return InlineKeyboardMarkup(botones)

def _teclado_sensores(tipo: str, clave_lapso: str) -> InlineKeyboardMarkup:
    """
    Teclado de selección de sensor.
    callback_data = "s:TIPO|LAPSO|IDX_SENSOR"   (ej. "s:g|6h|0")
    Se añade siempre la opción 'Todos los sensores'.
    """
    botones = []
    for idx, nombre in enumerate(_SENSORES_LISTA):
        dato = f"{PRE_SENSOR}{tipo}|{clave_lapso}|{idx}"
        botones.append([InlineKeyboardButton(nombre, callback_data=dato)])
    # Opción de todos los sensores
    dato_todos = f"{PRE_SENSOR}{tipo}|{clave_lapso}|{TODOS_IDX}"
    botones.append([InlineKeyboardButton("📡 Todos los sensores", callback_data=dato_todos)])
    return InlineKeyboardMarkup(botones)

# Helpers de formato y envío

def _fmt(valor, unidad="", decimales=1) -> str:
    """Formatea un valor numérico para mostrarlo al usuario."""
    if valor is None:
        return "Sin datos"
    return f"{valor:.{decimales}f}{unidad}"

def _emoji_estado(temp, hum) -> str:
    """Devuelve un emoji de color según el estado del sensor."""
    if temp is None or hum is None:
        return "❓"
    if temp > ALERTA_TEMP_MAX or hum > ALERTA_HUM_MAX:
        return "🔴"
    if temp < ALERTA_TEMP_MIN or hum < ALERTA_HUM_MIN:
        return "🔵"
    return "🟢"

async def _enviar_estado_texto(app, chat_id):
    """Envía las lecturas actuales de todos los sensores en texto."""
    actual = obtener_lecturas_actuales()
    ts     = actual["timestamp"].strftime("%d/%m/%Y %H:%M:%S")
    lineas = [f"📡 *Monitoreo DHT22*\n_{ts}_\n"]
    for nombre in SENSORES.keys():
        s   = actual.get(nombre, {})
        tmp = s.get("temperatura")
        hum = s.get("humedad")
        ico = _emoji_estado(tmp, hum)
        lineas.append(
            f"{ico} *{nombre}*\n"
            f"  🌡️ Temperatura: `{_fmt(tmp, ' °C')}`\n"
            f"  💧 Humedad:     `{_fmt(hum, ' %')}`\n"
        )
    await app.bot.send_message(
        chat_id=chat_id,
        text="\n".join(lineas),
        parse_mode="Markdown",
    )

async def _enviar_grafica(app, chat_id, clave_lapso: str, nombres_sensores: list[str]):
    """Genera y envía la imagen PNG para los sensores indicados."""
    actual    = obtener_lecturas_actuales()
    historial = obtener_historial(clave_lapso, nombres_sensores)
    imagenes  = generar_imagenes_graficas(actual, historial, nombres_sensores)
    etiqueta  = LAPSOS[clave_lapso][0]
    ts        = datetime.now(pytz.timezone(ZONA_HORARIA)).strftime("%d/%m/%Y %H:%M")
    for nombre, buf in imagenes:
        await app.bot.send_photo(
            chat_id=chat_id,
            photo=buf,
            caption=f"📊 Gráfica DHT22 — {etiqueta}\nSensor: {nombre}\n🕐 {ts}",
        )

async def _enviar_pdf(app, chat_id, clave_lapso: str, nombres_sensores: list[str]):
    """Genera y envía el reporte PDF para los sensores indicados."""
    actual    = obtener_lecturas_actuales()
    historial = obtener_historial(clave_lapso, nombres_sensores)
    buf       = generar_reporte_pdf(actual, historial, nombres_sensores)
    etiqueta  = LAPSOS[clave_lapso][0]
    ts        = datetime.now(pytz.timezone(ZONA_HORARIA)).strftime("%Y%m%d_%H%M")
    await app.bot.send_document(
        chat_id=chat_id,
        document=buf,
        filename=f"reporte_dht22_{clave_lapso}_{ts}.pdf",
        caption=f"📄 Reporte PDF DHT22 — {etiqueta}",
    )

async def _enviar_csv(app, chat_id, clave_lapso: str, nombres_sensores: list[str]):
    """Genera y envía el archivo CSV para los sensores indicados."""
    actual    = obtener_lecturas_actuales()
    historial = obtener_historial(clave_lapso, nombres_sensores)
    buf, nombre_archivo = generar_csv(actual, historial, nombres_sensores)
    etiqueta  = LAPSOS[clave_lapso][0]
    ts        = datetime.now(pytz.timezone(ZONA_HORARIA)).strftime("%d/%m/%Y %H:%M")
    await app.bot.send_document(
        chat_id=chat_id,
        document=buf,
        filename=nombre_archivo,
        caption=(
            f"📋 *CSV DHT22 — {etiqueta}*\n"
            f"🕐 {ts}\n\n"
            "Columnas: `sensor, tipo, timestamp, valor`\n"
        ),
        parse_mode="MarkdownV2",
    )

async def _verificar_alertas(app):
    """
    Verifica los umbrales de todos los sensores y envía
    una notificación si algún valor está fuera de rango.
    """
    if not alertas_activas:
        return
    actual = obtener_lecturas_actuales()
    for nombre in SENSORES.keys():
        s   = actual.get(nombre, {})
        tmp = s.get("temperatura")
        hum = s.get("humedad")
        msgs = []
        if tmp is not None:
            if tmp > ALERTA_TEMP_MAX:
                msgs.append(f"🔴 Temperatura alta: `{tmp:.1f}°C` (máx {ALERTA_TEMP_MAX}°C)")
            elif tmp < ALERTA_TEMP_MIN:
                msgs.append(f"🔵 Temperatura baja: `{tmp:.1f}°C` (mín {ALERTA_TEMP_MIN}°C)")
        if hum is not None:
            if hum > ALERTA_HUM_MAX:
                msgs.append(f"🔴 Humedad alta: `{hum:.1f}%` (máx {ALERTA_HUM_MAX}%)")
            elif hum < ALERTA_HUM_MIN:
                msgs.append(f"🔵 Humedad baja: `{hum:.1f}%` (mín {ALERTA_HUM_MIN}%)")
        if msgs:
            await app.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=f"⚠️ *Alerta — {nombre}*\n" + "\n".join(msgs),
                parse_mode="Markdown",
            )

# Handlers de comandos

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    texto = (
        "👋 *Bot de Monitoreo DHT22*\n\n"
        "Bienvenido\\. Este sistema le permite consultar en tiempo real "
        "los datos de temperatura y humedad registrados por los sensores DHT22\\.\n\n"
        "*Comandos disponibles:*\n"
        "• /status  — Lecturas actuales de todos los sensores\n"
        "• /png — Gráfica PNG \\(seleccione periodo y sensor\\)\n"
        "• /pdf — Reporte PDF completo \\(seleccione periodo y sensor\\)\n"
        "• /csv     — Archivo CSV \\(seleccione periodo y sensor\\)\n"
        "• /plan   — Plano de distribución de los sensores\n"
        "• /alerts — Activar o desactivar alertas automáticas\n"
        "• /help   — Mostrar comandos\n"
    )
    await update.message.reply_text(texto, parse_mode="MarkdownV2")

async def cmd_estado(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Consultando sensores, por favor espere...")
    await _enviar_estado_texto(ctx.application, update.effective_chat.id)

async def cmd_grafica(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 Por favor seleccione el periodo de tiempo para la gráfica:",
        reply_markup=_teclado_lapsos("g"),
    )

async def cmd_reporte(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📄 Por favor seleccione el periodo de tiempo para el reporte PDF:",
        reply_markup=_teclado_lapsos("r"),
    )

async def cmd_csv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Por favor seleccione el periodo de tiempo para el archivo CSV:",
        reply_markup=_teclado_lapsos("c"),
    )

async def cmd_alertas(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global alertas_activas
    alertas_activas = not alertas_activas
    estado = "✅ activadas" if alertas_activas else "🔕 desactivadas"
    await update.message.reply_text(f"Alertas automáticas {estado}.")

async def cmd_ayuda(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)


async def cmd_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Envía el plano de distribución de sensores en la instalación.
    """
    ruta = os.path.join("recursos", "plano_sensores.png")
    if not os.path.isfile(ruta):
        await update.message.reply_text(
            "No se encontro el archivo del plano.\n"
            "Verifique que exista la ruta: recursos/plano_sensores.png"
        )
        return
    caption = (
        "🧭 *Plano de distribucion de sensores DHT22*"
    )
    with open(ruta, "rb") as f:
        await update.message.reply_photo(photo=f, caption=caption, parse_mode="Markdown")

# Handler de callbacks (botones inline)

async def callback_lapso(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Primer paso: el usuario eligió el periodo.
    Se le presenta ahora el teclado de selección de sensor.
    """
    query = update.callback_query
    await query.answer()
    # Formato: "l:TIPO|CLAVE"  ej. "l:g|6h"
    _, resto   = query.data.split(":", 1)
    tipo, clave = resto.split("|", 1)
    etiqueta   = LAPSOS.get(clave, ("?",))[0]
    nombre_tipo = TIPO_NOMBRE.get(tipo, tipo)

    await query.edit_message_text(
        f"Periodo seleccionado: *{etiqueta}*\n\n"
        f"Ahora indique de qué sensor desea obtener la {nombre_tipo}:",
        parse_mode="Markdown",
        reply_markup=_teclado_sensores(tipo, clave),
    )

async def callback_sensor(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Segundo paso: el usuario eligió el sensor.
    Se genera y envía el archivo solicitado.
    """
    query = update.callback_query
    await query.answer()
    # Formato: "s:TIPO|LAPSO|IDX"  ej. "s:g|6h|0"
    _, resto        = query.data.split(":", 1)
    tipo, clave, idx_str = resto.split("|", 2)
    idx             = int(idx_str)
    nombres_sensores = _sensor_por_idx(idx)
    etiqueta        = LAPSOS.get(clave, ("?",))[0]
    nombre_tipo     = TIPO_NOMBRE.get(tipo, tipo)
    sensores_str    = "todos los sensores" if idx == TODOS_IDX else nombres_sensores[0]

    await query.edit_message_text(
        f"⏳ Generando {nombre_tipo} — {etiqueta} — {sensores_str}...\n"
        "Por favor espere."
    )

    try:
        if tipo == "g":
            await _enviar_grafica(ctx.application, query.message.chat_id, clave, nombres_sensores)
        elif tipo == "r":
            await _enviar_pdf(ctx.application, query.message.chat_id, clave, nombres_sensores)
        elif tipo == "c":
            await _enviar_csv(ctx.application, query.message.chat_id, clave, nombres_sensores)
    except Exception as e:
        log.error(f"Error generando {nombre_tipo}: {e}")
        await ctx.application.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ Ocurrió un error al generar el archivo. Por favor intente nuevamente.",
        )
        return

    # Ofrecer consultar otro periodo
    await ctx.application.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"✅ {nombre_tipo.capitalize()} enviado correctamente.\n\n"
             "¿Desea consultar otro periodo?",
        reply_markup=_teclado_lapsos(tipo),
    )

# Tarea en segundo plano: verificación de alertas cada 5 minutos

async def verificacion_alertas(app: Application):
    """Tarea periódica que revisa los umbrales y envía alertas si corresponde."""
    try:
        await _verificar_alertas(app)
    except Exception as e:
        log.error(f"Error en verificación de alertas: {e}")

# Main

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handlers de comandos
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("status",  cmd_estado))
    app.add_handler(CommandHandler("png",     cmd_grafica))
    app.add_handler(CommandHandler("pdf",     cmd_reporte))
    app.add_handler(CommandHandler("csv",     cmd_csv))
    app.add_handler(CommandHandler("plan",    cmd_plan))
    app.add_handler(CommandHandler("alerts",  cmd_alertas))
    app.add_handler(CommandHandler("help",    cmd_ayuda))

    # Handlers de botones inline — el orden importa
    app.add_handler(CallbackQueryHandler(callback_lapso,  pattern=f"^{PRE_LAPSO}"))
    app.add_handler(CallbackQueryHandler(callback_sensor, pattern=f"^{PRE_SENSOR}"))

    async def post_init(application: Application):
        await application.bot.set_my_commands([
            BotCommand("status",  "Lecturas actuales de todos los sensores"),
            BotCommand("png",     "Gráfica PNG — seleccione periodo y sensor"),
            BotCommand("pdf",     "Reporte PDF completo — seleccione periodo y sensor"),
            BotCommand("csv",     "Exportar datos en CSV — seleccione periodo y sensor"),
            BotCommand("plan",    "Plano de distribución de los sensores"),
            BotCommand("alerts",  "Activar o desactivar alertas automáticas"),
            BotCommand("help",    "Mostrar comandos disponibles"),
        ])

    app.post_init = post_init

    # Scheduler: solo verificación de alertas en segundo plano
    scheduler = AsyncIOScheduler(timezone=ZONA_HORARIA)
    scheduler.add_job(
        verificacion_alertas,
        trigger=CronTrigger(minute="*/5", timezone=ZONA_HORARIA),
        args=[app],
        id="chequeo_alertas",
    )
    scheduler.start()
    log.info("Bot iniciado. Reportes bajo demanda del usuario. Alertas activas cada 5 min.")

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()