# ============================================================
# bot_telegram.py — Bot principal con comandos
# ============================================================
# Comandos:
#   /start   — Bienvenida
#   /estado  — Lecturas actuales (texto)
#   /grafica — Selecciona lapso → imagen PNG
#   /reporte — Selecciona lapso → PDF completo
#   /csv     — Selecciona lapso → archivo CSV
#   /alertas — Activar/desactivar alertas automáticas
#   /ayuda   — Lista de comandos
# ============================================================

import logging
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

from configuracion import (
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, ZONA_HORARIA,
    ALERTA_TEMP_MAX, ALERTA_TEMP_MIN,
    ALERTA_HUM_MAX,  ALERTA_HUM_MIN,
    ALERTAS_ACTIVAS,
)
from cliente_prometheus import obtener_lecturas_actuales, obtener_historial, LAPSOS
from generador_reportes  import generar_imagen_grafica, generar_reporte_pdf, generar_csv

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

alertas_activas = ALERTAS_ACTIVAS

# Prefijos para los callbacks de los botones inline
PRE_GRAFICA = "grafica:"
PRE_REPORTE = "reporte:"
PRE_CSV     = "csv:"


# ================================================================
# Teclado inline de lapsos
# ================================================================

def _teclado_lapsos(prefijo: str) -> InlineKeyboardMarkup:
    """Teclado con los 11 lapsos disponibles, 2 botones por fila."""
    botones = []
    fila    = []
    for i, (clave, (etiq, _, _)) in enumerate(LAPSOS.items()):
        fila.append(InlineKeyboardButton(etiq, callback_data=prefijo + clave))
        if len(fila) == 2:
            botones.append(fila)
            fila = []
    if fila:
        botones.append(fila)
    return InlineKeyboardMarkup(botones)


# ================================================================
# Helpers de formato y envío
# ================================================================

def _fmt(valor, unidad="", decimales=1) -> str:
    if valor is None:
        return "Sin datos"
    return f"{valor:.{decimales}f}{unidad}"


def _emoji_estado(temp, hum) -> str:
    if temp is None or hum is None:
        return "❓"
    if temp > ALERTA_TEMP_MAX or hum > ALERTA_HUM_MAX:
        return "🔴"
    if temp < ALERTA_TEMP_MIN or hum < ALERTA_HUM_MIN:
        return "🔵"
    return "🟢"


async def _enviar_estado_texto(app, chat_id):
    """Lecturas actuales en texto con Markdown."""
    actual = obtener_lecturas_actuales()
    ts     = actual["timestamp"].strftime("%d/%m/%Y %H:%M:%S")
    lineas = [f"📡 *Monitoreo DHT22*\n_{ts}_\n"]
    for nombre in ["NodeMCU V3", "ESP32-C3"]:
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


async def _enviar_grafica(app, chat_id, clave_lapso: str):
    """PNG con gráficas de tendencia para el lapso elegido."""
    actual    = obtener_lecturas_actuales()
    historial = obtener_historial(clave_lapso)
    buf       = generar_imagen_grafica(actual, historial)
    etiqueta  = LAPSOS[clave_lapso][0]
    tz        = pytz.timezone(ZONA_HORARIA)
    ts        = datetime.now(tz).strftime("%d/%m/%Y %H:%M")
    await app.bot.send_photo(
        chat_id=chat_id,
        photo=buf,
        caption=f"📊 Gráfica DHT22 — {etiqueta}\n🕐 {ts}",
    )


async def _enviar_pdf(app, chat_id, clave_lapso: str):
    """PDF con tabla completa de registros para el lapso elegido."""
    actual    = obtener_lecturas_actuales()
    historial = obtener_historial(clave_lapso)
    buf       = generar_reporte_pdf(actual, historial)
    tz        = pytz.timezone(ZONA_HORARIA)
    ts        = datetime.now(tz).strftime("%Y%m%d_%H%M")
    etiqueta  = LAPSOS[clave_lapso][0]
    await app.bot.send_document(
        chat_id=chat_id,
        document=buf,
        filename=f"reporte_dht22_{clave_lapso}_{ts}.pdf",
        caption=f"📄 Reporte PDF DHT22 — {etiqueta}",
    )


async def _enviar_csv(app, chat_id, clave_lapso: str):
    """CSV con todos los registros del lapso elegido."""
    actual    = obtener_lecturas_actuales()
    historial = obtener_historial(clave_lapso)
    buf, nombre_archivo = generar_csv(actual, historial)
    etiqueta  = LAPSOS[clave_lapso][0]
    tz        = pytz.timezone(ZONA_HORARIA)
    ts        = datetime.now(tz).strftime("%d/%m/%Y %H:%M")
    await app.bot.send_document(
        chat_id=chat_id,
        document=buf,
        filename=nombre_archivo,
        caption=(
            f"📋 *CSV DHT22 — {etiqueta}*\n"
            f"🕐 {ts}\n\n"
            "Columnas: `sensor, tipo, timestamp, valor`\n"
            "Compatible con Excel, pandas y MATLAB (`readtable`)."
        ),
        parse_mode="Markdown",
    )


async def _verificar_alertas(app):
    """Revisa umbrales y envía aviso si algún sensor está fuera de rango."""
    if not alertas_activas:
        return
    actual = obtener_lecturas_actuales()
    for nombre in ["NodeMCU V3", "ESP32-C3"]:
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


# ================================================================
# Handlers de comandos
# ================================================================

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    texto = (
        "👋 *Bot de Monitoreo DHT22*\n\n"
        "Monitoreando *NodeMCU V3* y *ESP32\\-C3* vía Prometheus\\.\n\n"
        "Comandos disponibles:\n"
        "• /estado  — Lecturas actuales\n"
        "• /grafica — Gráfica PNG \\(elija el periodo\\)\n"
        "• /reporte — PDF completo \\(elija el periodo\\)\n"
        "• /csv     — Archivo CSV \\(elija el periodo\\)\n"
        "• /alertas — Activar/desactivar alertas\n"
        "• /ayuda   — Esta ayuda\n"
    )
    await update.message.reply_text(texto, parse_mode="MarkdownV2")


async def cmd_estado(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Consultando sensores...")
    await _enviar_estado_texto(ctx.application, update.effective_chat.id)


async def cmd_grafica(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 Selecciona el periodo para la gráfica:",
        reply_markup=_teclado_lapsos(PRE_GRAFICA),
    )


async def cmd_reporte(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📄 Selecciona el periodo para el reporte PDF:",
        reply_markup=_teclado_lapsos(PRE_REPORTE),
    )


async def cmd_csv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Selecciona el periodo para el archivo CSV:",
        reply_markup=_teclado_lapsos(PRE_CSV),
    )


async def cmd_alertas(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global alertas_activas
    alertas_activas = not alertas_activas
    estado = "✅ activadas" if alertas_activas else "🔕 desactivadas"
    await update.message.reply_text(f"Alertas automáticas {estado}.")


async def cmd_ayuda(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)


# ================================================================
# Handler de callbacks (botones inline)
# ================================================================

async def callback_lapso(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    data    = query.data
    chat_id = query.message.chat_id

    if data.startswith(PRE_GRAFICA):
        clave = data[len(PRE_GRAFICA):]
        etiq  = LAPSOS.get(clave, ("?",))[0]
        await query.edit_message_text(f"⏳ Generando gráfica — {etiq}...")
        await _enviar_grafica(ctx.application, chat_id, clave)
        await ctx.application.bot.send_message(
            chat_id=chat_id,
            text="📊 ¿Ver otro periodo?",
            reply_markup=_teclado_lapsos(PRE_GRAFICA),
        )

    elif data.startswith(PRE_REPORTE):
        clave = data[len(PRE_REPORTE):]
        etiq  = LAPSOS.get(clave, ("?",))[0]
        await query.edit_message_text(f"⏳ Generando reporte PDF — {etiq}...")
        await _enviar_pdf(ctx.application, chat_id, clave)
        await ctx.application.bot.send_message(
            chat_id=chat_id,
            text="📄 ¿Ver otro periodo?",
            reply_markup=_teclado_lapsos(PRE_REPORTE),
        )

    elif data.startswith(PRE_CSV):
        clave = data[len(PRE_CSV):]
        etiq  = LAPSOS.get(clave, ("?",))[0]
        await query.edit_message_text(f"⏳ Generando CSV — {etiq}...")
        await _enviar_csv(ctx.application, chat_id, clave)
        await ctx.application.bot.send_message(
            chat_id=chat_id,
            text="📋 ¿Ver otro periodo?",
            reply_markup=_teclado_lapsos(PRE_CSV),
        )


# ================================================================
# Tareas programadas
# ================================================================

async def verificacion_alertas(app: Application):
    try:
        await _verificar_alertas(app)
    except Exception as e:
        log.error(f"Error en verificación de alertas: {e}")

# ================================================================
# Main
# ================================================================

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("estado",  cmd_estado))
    app.add_handler(CommandHandler("grafica", cmd_grafica))
    app.add_handler(CommandHandler("reporte", cmd_reporte))
    app.add_handler(CommandHandler("csv",     cmd_csv))
    app.add_handler(CommandHandler("alertas", cmd_alertas))
    app.add_handler(CommandHandler("ayuda",   cmd_ayuda))
    app.add_handler(CallbackQueryHandler(callback_lapso))

    async def post_init(application: Application):
        await application.bot.set_my_commands([
            BotCommand("estado",  "Lecturas actuales de los sensores"),
            BotCommand("grafica", "Gráfica PNG — elija el periodo"),
            BotCommand("reporte", "Reporte PDF completo — elija el periodo"),
            BotCommand("csv",     "Exportar datos en CSV — elija el periodo"),
            BotCommand("alertas", "Activar/desactivar alertas automáticas"),
            BotCommand("ayuda",   "Mostrar comandos"),
        ])

    app.post_init = post_init

    scheduler = AsyncIOScheduler(timezone=ZONA_HORARIA)
    scheduler.add_job(
        verificacion_alertas,
        trigger=CronTrigger(minute="*/5", timezone=ZONA_HORARIA),
        args=[app],
        id="chequeo_alertas",
    )

    scheduler.start()
    log.info("Scheduler iniciado. Bot corriendo...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
