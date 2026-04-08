# ============================================================
# bot_telegram.py — Bot principal con comandos
# ============================================================
# Comandos disponibles:
#   /start   — Bienvenida e instrucciones
#   /status  — Lecturas actuales de todos los sensores
#   /png     — Gráfica PNG
#   /pdf     — Reporte PDF completo
#   /csv     — Archivo CSV
#   /plan    — Plano de distribución de sensores
#   /alerts  — Activar o desactivar alertas automáticas
#   /help    — Lista de comandos disponibles
#
# Flujo de selección (4 pasos, 100% por botones):
#   1. Usuario ejecuta /png /pdf /csv
#   2. Bot pregunta el sensor (individual o todos)
#   3. Bot pregunta la unidad de tiempo (solo las disponibles
#      según el historial real de Prometheus, tolerando gaps ≤10 min)
#   4. Bot muestra las cantidades disponibles para esa unidad
#      (solo las que caben en el historial real)
#   5. Bot genera y envía el archivo
#
# Opciones predefinidas por unidad:
#   Minutos:  5, 15, 30, 45
#   Horas:    1, 3, 6, 12, 18
#   Días:     1, 2, 3, 4, 5, 6
#   Semanas:  1, 2, 3
#   Meses:    1 … 11
#   Años:     1 … 5
#
# Estado por usuario: cada user_id tiene su propio estado
# para soportar múltiples usuarios simultáneos en el grupo.
# ============================================================

import logging
import os.path
from datetime import datetime

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)

from configuracion import (
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, ZONA_HORARIA, SENSORES,
    ALERTA_TEMP_MAX, ALERTA_TEMP_MIN,
    ALERTA_HUM_MAX,  ALERTA_HUM_MIN,
    ALERTAS_ACTIVAS,
)
from servidor_dashboard import ServidorDashboard
from cliente_prometheus import (
    obtener_lecturas_actuales,
    obtener_historial_por_minutos,
    obtener_minutos_disponibles,
    UNIDADES, MINUTOS_POR_UNIDAD,
)
from generador_reportes import generar_imagenes_graficas, generar_reporte_pdf, generar_csv

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# Servidor web para /dashboard
_servidor_dashboard = ServidorDashboard(puerto=8765)

alertas_activas = ALERTAS_ACTIVAS

# ----------------------------------------------------------------
# Estado de conversación por usuario
# ----------------------------------------------------------------
_estado_usuario: dict[int, dict] = {}

# Prefijos callback
PRE_SENSOR   = "sen:"
PRE_UNIDAD   = "uni:"
PRE_CANTIDAD = "can:"

TIPO_NOMBRE = {"g": "gráfica", "r": "reporte PDF", "c": "CSV"}
TODOS_IDX   = 99
_SENSORES_LISTA = list(SENSORES.keys())

# Opciones predefinidas por unidad (en la propia unidad, no en minutos)
_OPCIONES_UNIDAD: dict[str, list[int]] = {
    "m":  [5, 15, 30, 45],
    "h":  [1, 3, 6, 12, 18],
    "d":  [1, 2, 3, 4, 5, 6],
    "w":  [1, 2, 3],
    "mo": list(range(1, 12)),   # 1 … 11
    "y":  list(range(1, 6)),    # 1 … 5
}

# Etiquetas de unidad para los botones
_ETIQ_UNIDAD = {
    "m":  "⏱ Minutos",
    "h":  "🕐 Horas",
    "d":  "📅 Días",
    "w":  "🗓 Semanas",
    "mo": "📆 Meses",
    "y":  "🗃 Años",
}

# Singular / plural corto para mostrar en botones de cantidad
_ETIQ_SINGULAR = {
    "m":  "min",
    "h":  "h",
    "d":  "día",
    "w":  "sem",
    "mo": "mes",
    "y":  "año",
}
_ETIQ_PLURAL = {
    "m":  "min",
    "h":  "h",
    "d":  "días",
    "w":  "sem",
    "mo": "meses",
    "y":  "años",
}


def _sensor_por_idx(idx: int) -> list[str]:
    if idx == TODOS_IDX:
        return _SENSORES_LISTA
    return [_SENSORES_LISTA[idx]]


# ----------------------------------------------------------------
# Teclados inline
# ----------------------------------------------------------------

def _teclado_sensores(tipo: str) -> InlineKeyboardMarkup:
    """Teclado de selección de sensor. callback_data = "sen:TIPO|IDX" """
    botones = []
    for idx, nombre in enumerate(_SENSORES_LISTA):
        botones.append([InlineKeyboardButton(
            nombre, callback_data=f"{PRE_SENSOR}{tipo}|{idx}"
        )])
    botones.append([InlineKeyboardButton(
        "📡 Todos los sensores",
        callback_data=f"{PRE_SENSOR}{tipo}|{TODOS_IDX}"
    )])
    return InlineKeyboardMarkup(botones)


def _teclado_unidades(tipo: str, minutos_disponibles: int) -> InlineKeyboardMarkup | None:
    """
    Muestra solo las unidades cuya opción MÁS PEQUEÑA cabe en el historial.
    callback_data = "uni:TIPO|UNIDAD"
    """
    botones = []
    fila    = []
    for clave in ["m", "h", "d", "w", "mo", "y"]:
        opcion_min = _OPCIONES_UNIDAD[clave][0]          # la más pequeña (ej. 5 min, 1 h …)
        minutos_min = opcion_min * MINUTOS_POR_UNIDAD[clave]
        if minutos_disponibles >= minutos_min:
            fila.append(InlineKeyboardButton(
                _ETIQ_UNIDAD[clave],
                callback_data=f"{PRE_UNIDAD}{tipo}|{clave}"
            ))
            if len(fila) == 2:
                botones.append(fila)
                fila = []
    if fila:
        botones.append(fila)
    return InlineKeyboardMarkup(botones) if botones else None


def _teclado_cantidades(tipo: str, unidad: str,
                         minutos_disponibles: int) -> InlineKeyboardMarkup | None:
    """
    Muestra solo las cantidades de la unidad elegida que caben
    en el historial real disponible.
    callback_data = "can:TIPO|UNIDAD|VALOR"
    """
    opciones_validas = []
    for val in _OPCIONES_UNIDAD[unidad]:
        minutos_necesarios = val * MINUTOS_POR_UNIDAD[unidad]
        if minutos_disponibles >= minutos_necesarios:
            opciones_validas.append(val)

    if not opciones_validas:
        return None

    etiq = _ETIQ_SINGULAR if True else _ETIQ_PLURAL   # usamos fn abajo
    botones = []
    fila    = []
    for val in opciones_validas:
        label_unidad = _ETIQ_SINGULAR[unidad] if val == 1 else _ETIQ_PLURAL[unidad]
        fila.append(InlineKeyboardButton(
            f"{val} {label_unidad}",
            callback_data=f"{PRE_CANTIDAD}{tipo}|{unidad}|{val}"
        ))
        if len(fila) == 3:
            botones.append(fila)
            fila = []
    if fila:
        botones.append(fila)
    return InlineKeyboardMarkup(botones)


# ----------------------------------------------------------------
# Helpers de envío
# ----------------------------------------------------------------

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
        chat_id=chat_id, text="\n".join(lineas), parse_mode="Markdown"
    )


async def _generar_y_enviar(app, chat_id: int, tipo: str,
                             minutos: int, nombres_sensores: list[str]):
    """Obtiene el historial y envía el archivo según el tipo."""
    actual    = obtener_lecturas_actuales(nombres_sensores)
    historial = obtener_historial_por_minutos(minutos, nombres_sensores)
    etiqueta  = historial["lapso_info"]["etiqueta"]
    ts_fmt    = datetime.now(pytz.timezone(ZONA_HORARIA)).strftime("%Y%m%d_%H%M")

    if tipo == "g":
        imagenes = generar_imagenes_graficas(actual, historial, nombres_sensores)
        ts_cap   = datetime.now(pytz.timezone(ZONA_HORARIA)).strftime("%d/%m/%Y %H:%M")
        for nombre, buf in imagenes:
            await app.bot.send_photo(
                chat_id=chat_id,
                photo=buf,
                caption=f"📊 Gráfica DHT22 — {etiqueta}\nSensor: {nombre}\n🕐 {ts_cap}",
            )
    elif tipo == "r":
        buf = generar_reporte_pdf(actual, historial, nombres_sensores)
        await app.bot.send_document(
            chat_id=chat_id,
            document=buf,
            filename=f"reporte_dht22_{ts_fmt}.pdf",
            caption=f"📄 Reporte PDF DHT22 — {etiqueta}",
        )
    elif tipo == "c":
        buf, nombre_arch = generar_csv(actual, historial, nombres_sensores)
        ts_cap = datetime.now(pytz.timezone(ZONA_HORARIA)).strftime("%d/%m/%Y %H:%M")
        await app.bot.send_document(
            chat_id=chat_id,
            document=buf,
            filename=nombre_arch,
            caption=(
                f"📋 CSV DHT22 — {etiqueta}\n"
                f"🕐 {ts_cap}\n"
                "Columnas: sensor, tipo, timestamp, valor"
            ),
        )


async def _verificar_alertas(app):
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


# ----------------------------------------------------------------
# Handlers de comandos
# ----------------------------------------------------------------

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    texto = (
        "👋 *Bot de Monitoreo DHT22*\n\n"
        "Bienvenido\\. Este sistema le permite consultar en tiempo real "
        "los datos de temperatura y humedad registrados por los sensores DHT22\\.\n\n"
        "*Comandos disponibles:*\n"
        "• /status  — Lecturas actuales de todos los sensores\n"
        "• /png     — Gráfica PNG\n"
        "• /pdf     — Reporte PDF completo\n"
        "• /csv     — Archivo CSV\n"
        "• /dashboard — Dashboard de Grafana \(enlace temporal\)\n"
        "• /plan    — Plano de distribución de los sensores\n"
        "• /alerts  — Activar o desactivar alertas automáticas\n"
        "• /help    — Mostrar esta ayuda\n"
    )
    await update.message.reply_text(texto, parse_mode="MarkdownV2")


async def cmd_estado(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Consultando sensores, por favor espere...")
    await _enviar_estado_texto(ctx.application, update.effective_chat.id)


async def _iniciar_flujo(update: Update, tipo: str):
    """Paso 1: pregunta el sensor."""
    uid = update.effective_user.id
    _estado_usuario[uid] = {"tipo": tipo, "paso": "sensor"}
    await update.message.reply_text(
        f"Por favor seleccione el sensor para la {TIPO_NOMBRE[tipo]}:",
        reply_markup=_teclado_sensores(tipo),
    )


async def cmd_grafica(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _iniciar_flujo(update, "g")

async def cmd_reporte(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _iniciar_flujo(update, "r")

async def cmd_csv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _iniciar_flujo(update, "c")


async def cmd_alertas(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    global alertas_activas
    alertas_activas = not alertas_activas
    estado = "✅ activadas" if alertas_activas else "🔕 desactivadas"
    await update.message.reply_text(f"Alertas automáticas {estado}.")


async def cmd_ayuda(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)



async def cmd_dashboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Genera un enlace de acceso único (válido 10 minutos) al dashboard
    de Grafana y lo envía de forma privada al usuario que lo solicitó.
    El enlace solo funciona desde la red local donde corre el servidor.
    """
    token = _servidor_dashboard.generar_token()
    url   = _servidor_dashboard.url_con_token(token)
    tz    = pytz.timezone(ZONA_HORARIA)
    ts    = datetime.now(tz).strftime("%H:%M:%S")
    texto = (
        "📊 Dashboard DHT22\n\n"
        f"Enlace generado a las {ts}:\n"
        f"{url}\n\n"
        "Este enlace expira en 🔟 minutos."
    )
    await update.message.reply_text(texto)

async def cmd_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ruta = os.path.join("recursos", "plano_sensores.png")
    if not os.path.isfile(ruta):
        await update.message.reply_text(
            "No se encontró el archivo del plano.\n"
            "Verifique que exista la ruta: recursos/plano_sensores.png"
        )
        return
    with open(ruta, "rb") as f:
        await update.message.reply_photo(
            photo=f,
            caption="📐 *Plano de distribución de sensores DHT22*",
            parse_mode="Markdown",
        )


# ----------------------------------------------------------------
# Callbacks de botones inline
# ----------------------------------------------------------------

async def callback_sensor(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Paso 2: usuario eligió sensor → consultar disponibilidad → pedir unidad."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    _, resto      = query.data.split(":", 1)
    tipo, idx_str = resto.split("|", 1)
    idx           = int(idx_str)
    nombres       = _sensor_por_idx(idx)
    tipo_nombre   = TIPO_NOMBRE.get(tipo, tipo)

    await query.edit_message_text(
        f"Sensor seleccionado: *{', '.join(nombres)}*\n\n"
        "⏳ Consultando historial disponible...",
        parse_mode="Markdown",
    )

    # Consultar cuántos minutos hay disponibles (con tolerancia a gaps)
    minutos_disp = obtener_minutos_disponibles(nombres)

    # Guardar estado
    _estado_usuario[uid] = {
        "tipo":     tipo,
        "sensores": nombres,
        "min_disp": minutos_disp,
        "paso":     "unidad",
    }

    teclado = _teclado_unidades(tipo, minutos_disp)
    if teclado is None:
        await ctx.application.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ No hay suficientes datos disponibles para generar un reporte.",
        )
        _estado_usuario.pop(uid, None)
        return

    # Resumen legible de disponibilidad
    def _fmt_disp(minutos: int) -> str:
        if minutos < 60:
            return f"{minutos} min"
        elif minutos < 1440:
            return f"{minutos // 60} h {minutos % 60} min"
        elif minutos < 10080:
            d = minutos // 1440
            h = (minutos % 1440) // 60
            return f"{d}d {h}h" if h else f"{d} día{'s' if d > 1 else ''}"
        else:
            w = minutos // 10080
            d = (minutos % 10080) // 1440
            return f"{w} sem {d}d" if d else f"{w} semana{'s' if w > 1 else ''}"

    await ctx.application.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            f"📊 Historial disponible: *{_fmt_disp(minutos_disp)}*\n\n"
            f"Seleccione la unidad de tiempo para la {tipo_nombre}:"
        ),
        parse_mode="Markdown",
        reply_markup=teclado,
    )


async def callback_unidad(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Paso 3: usuario eligió unidad → mostrar botones de cantidad disponibles."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    _, resto     = query.data.split(":", 1)
    tipo, unidad = resto.split("|", 1)
    nombre_u     = UNIDADES[unidad][0]
    estado       = _estado_usuario.get(uid, {})
    minutos_disp = estado.get("min_disp", 60)

    # Actualizar estado
    _estado_usuario[uid] = {
        **estado,
        "tipo":   tipo,
        "unidad": unidad,
        "paso":   "cantidad",
    }

    teclado = _teclado_cantidades(tipo, unidad, minutos_disp)
    if teclado is None:
        await query.edit_message_text(
            f"❌ No hay datos suficientes para mostrar opciones en {nombre_u}.\n"
            "Por favor elija otra unidad.",
        )
        return

    await query.edit_message_text(
        f"Unidad seleccionada: *{nombre_u}*\n\n"
        f"Seleccione cuántos {nombre_u} desea consultar:",
        parse_mode="Markdown",
        reply_markup=teclado,
    )


async def callback_cantidad(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Paso 4: usuario eligió cantidad → generar y enviar archivo."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    _, resto          = query.data.split(":", 1)
    tipo, unidad, val_str = resto.split("|", 2)
    valor             = int(val_str)
    minutos           = valor * MINUTOS_POR_UNIDAD[unidad]
    estado            = _estado_usuario.get(uid, {})
    nombres           = estado.get("sensores", _SENSORES_LISTA)
    tipo_nombre       = TIPO_NOMBRE.get(tipo, tipo)
    label_u           = _ETIQ_SINGULAR[unidad] if valor == 1 else _ETIQ_PLURAL[unidad]

    # Limpiar estado
    _estado_usuario.pop(uid, None)

    await query.edit_message_text(
        f"⏳ Generando {tipo_nombre} — últimos {valor} {label_u} "
        f"— {', '.join(nombres)}...\nPor favor espere."
    )

    try:
        await _generar_y_enviar(
            ctx.application, query.message.chat_id,
            tipo, minutos, nombres
        )
    except Exception as e:
        log.error(f"Error generando {tipo_nombre}: {e}")
        await ctx.application.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ Ocurrió un error al generar el archivo. Por favor intente nuevamente.",
        )
        return

    # Ofrecer volver a empezar
    await ctx.application.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            f"✅ {tipo_nombre.capitalize()} enviado correctamente.\n\n"
            "¿Desea consultar otro periodo?"
        ),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                f"🔄 Nueva {tipo_nombre}",
                callback_data=f"reiniciar:{tipo}"
            )
        ]]),
    )


async def callback_reiniciar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Reinicia el flujo desde el paso de selección de sensor."""
    query = update.callback_query
    await query.answer()
    _, tipo = query.data.split(":", 1)
    uid = query.from_user.id
    _estado_usuario[uid] = {"tipo": tipo, "paso": "sensor"}
    await query.edit_message_text(
        f"Por favor seleccione el sensor para la {TIPO_NOMBRE[tipo]}:",
        reply_markup=_teclado_sensores(tipo),
    )


# ----------------------------------------------------------------
# Tarea periódica: verificación de alertas
# ----------------------------------------------------------------

async def verificacion_alertas(app: Application):
    try:
        await _verificar_alertas(app)
    except Exception as e:
        log.error(f"Error en verificación de alertas: {e}")


# ----------------------------------------------------------------
# Main
# ----------------------------------------------------------------

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("status", cmd_estado))
    app.add_handler(CommandHandler("png",    cmd_grafica))
    app.add_handler(CommandHandler("pdf",    cmd_reporte))
    app.add_handler(CommandHandler("csv",    cmd_csv))
    app.add_handler(CommandHandler("dashboard", cmd_dashboard))
    app.add_handler(CommandHandler("plan",   cmd_plan))
    app.add_handler(CommandHandler("alerts", cmd_alertas))
    app.add_handler(CommandHandler("help",   cmd_ayuda))

    # Botones inline — orden importa
    app.add_handler(CallbackQueryHandler(callback_sensor,   pattern=f"^{PRE_SENSOR}"))
    app.add_handler(CallbackQueryHandler(callback_unidad,   pattern=f"^{PRE_UNIDAD}"))
    app.add_handler(CallbackQueryHandler(callback_cantidad, pattern=f"^{PRE_CANTIDAD}"))
    app.add_handler(CallbackQueryHandler(callback_reiniciar, pattern=r"^reiniciar:"))

    # Sin MessageHandler de texto: ya no se pide número al usuario

    async def post_init(application: Application):
        await _servidor_dashboard.iniciar()
        await application.bot.set_my_commands([
            BotCommand("status",  "Lecturas actuales de todos los sensores"),
            BotCommand("png",     "Gráfica PNG — seleccione sensor y periodo"),
            BotCommand("pdf",     "Reporte PDF completo — seleccione sensor y periodo"),
            BotCommand("csv",     "Exportar datos en CSV — seleccione sensor y periodo"),
            BotCommand("dashboard", "Dashboard de Grafana (enlace de acceso temporal)"),
            BotCommand("plan",    "Plano de distribución de los sensores"),
            BotCommand("alerts",  "Activar o desactivar alertas automáticas"),
            BotCommand("help",    "Mostrar comandos disponibles"),
        ])

    async def post_shutdown(application: Application):
        await _servidor_dashboard.detener()

    app.post_init     = post_init
    app.post_shutdown = post_shutdown

    scheduler = AsyncIOScheduler(timezone=ZONA_HORARIA)
    scheduler.add_job(
        verificacion_alertas,
        trigger=CronTrigger(minute="*/5", timezone=ZONA_HORARIA),
        args=[app],
        id="chequeo_alertas",
    )
    scheduler.start()
    log.info("Bot iniciado. Alertas activas cada 5 min.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
