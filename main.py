import os
import httpx
import sqlite3
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from flask import Flask
from threading import Thread

load_dotenv()
TOKEN_TELEGRAM = os.getenv("TELEGRAM_TOKEN")
MI_CHAT_ID = os.getenv("MI_CHAT_ID")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

URL_PONT_GOOGLE = "https://script.google.com/macros/s/AKfycbzNv_4YqY0fBEpR9yNwAebEbgbcsJ0NMwJDN3H_Y-oeT05bTaIom2yWoKyPiBitR8DP/exec"

TIPSTERS = {
    "🏆 Top 1": "678767edb8435cc2d1bba515",
    "🥈 Top 2": "6758979fed09a67b595d5ba2",
    "🥉 Top 3": "68e0f8743fc35ff674f3ad74"
}

USER_ACTUAL = "678767edb8435cc2d1bba515"

# --- CONFIGURACIÓ DEL MENÚ INFERIOR (REPLY KEYBOARD) ---
def get_main_menu():
    # Aquests botons "escriuen" el text directament al xat
    keyboard = [
        [KeyboardButton("/activas")],
        [KeyboardButton("/menu"), KeyboardButton("/start")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- SERVIDOR WEB ---
app_web = Flask(__name__)
@app_web.route('/')
def home(): return "Bot amb Menú Actiu!"

def run(): app_web.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

# --- BASE DE DADES ---
def inicializar_bd():
    conexion = sqlite3.connect("apuestas.db")
    cursor = conexion.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS enviadas (id_partido INTEGER PRIMARY KEY)')
    conexion.commit()
    conexion.close()

inicializar_bd()

# --- LÒGICA DE QUOTES ---
async def obtener_cuota_bet365(home_team, away_team):
    if not ODDS_API_KEY: return "API Key no configurada ⚠️"
    url = f"https://api.the-odds-api.com/v4/sports/soccer/odds/?apiKey={ODDS_API_KEY}&regions=eu&markets=h2h&bookmakers=bet365"
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(url, timeout=10.0)
            if res.status_code == 200:
                partits = res.json()
                for p in partits:
                    if home_team.lower() in p['home_team'].lower() or away_team.lower() in p['away_team'].lower():
                        for bm in p['bookmakers']:
                            if bm['key'] == 'bet365':
                                outcomes = bm['markets'][0]['outcomes']
                                return "✅ Bet365: " + " | ".join([f"{o['name']}: {o['price']}" for o in outcomes])
                return "❌ No trobat a Bet365"
            return "❌ Error API"
        except: return "⚠️ Error de connexió"

# --- COMANDOS ---
async def comando_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Enviem el missatge amb el teclat inferior activat
    await update.message.reply_text(
        "¡Bienvenido! He activado el menú de comandos rápido aquí abajo. ⬇️",
        reply_markup=get_main_menu()
    )

async def mostrar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Botons Inline (per triar tipster)
    keyboard = [[InlineKeyboardButton(nombre, callback_data=tid)] for nombre, tid in TIPSTERS.items()]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🏆 **Elige un tipster:**", reply_markup=reply_markup, parse_mode="Markdown")

async def gestion_botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_ACTUAL
    query = update.callback_query
    await query.answer()
    USER_ACTUAL = query.data
    nombre = [n for n, tid in TIPSTERS.items() if tid == USER_ACTUAL][0]
    
    # Després de triar, recordem que pot fer servir el menú inferior
    await query.edit_message_text(text=f"✅ Vigilando a: *{nombre}*\n\nPulsa /activas para ver sus partidos.", parse_mode="Markdown")

async def comando_activas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🔎 Buscando apuestas y comparando con Bet365...")
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            respuesta = await client.get(f"{URL_PONT_GOOGLE}?id={USER_ACTUAL}", timeout=20.0)
            if respuesta.status_code == 200:
                datos = respuesta.json()
                predicciones = datos.get("predictions", [])
                if predicciones:
                    msg = "📋 **COMPARATIVA ACTUAL:**\n\n"
                    for ap in predicciones:
                        info_bet365 = await obtener_cuota_bet365(ap['homeTeamName'], ap['awayTeamName'])
                        msg += f"⚽ *{ap['homeTeamName']} vs {ap['awayTeamName']}*\n🎯 {ap['vote']} | 📈 Sofascore: {ap['odds']['decimalValue']}\n🏦 {info_bet365}\n〰️〰️\n"
                    # Tornem a enviar el ReplyKeyboardMarkup per assegurar-nos que el té
                    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_menu())
                else:
                    await update.message.reply_text("Sin apuestas ahora mismo. 🎈", reply_markup=get_main_menu())
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}", reply_markup=get_main_menu())

async def revisar_automaticamente(context: ContextTypes.DEFAULT_TYPE):
    global USER_ACTUAL
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            res = await client.get(f"{URL_PONT_GOOGLE}?id={USER_ACTUAL}", timeout=20.0)
            if res.status_code == 200:
                predicciones = res.json().get("predictions", [])
                conexion = sqlite3.connect("apuestas.db")
                cursor = conexion.cursor()
                nuevas = []
                for ap in predicciones:
                    id_p = ap["eventId"]
                    cursor.execute("SELECT id_partido FROM enviadas WHERE id_partido = ?", (id_p,))
                    if cursor.fetchone() is None:
                        nuevas.append(ap)
                        cursor.execute("INSERT INTO enviadas (id_partido) VALUES (?)", (id_p,))
                conexion.commit()
                conexion.close()

                if nuevas:
                    msg = f"🚨 *¡ALERTA NUEVA!* ({USER_ACTUAL})\n\n"
                    for ap in nuevas:
                        msg += f"⚽ *{ap['homeTeamName']} vs {ap['awayTeamName']}*\n🎯 {ap['vote']} | 📈 {ap['odds']['decimalValue']}\n"
                    msg += "\n💡 Usa el botón /activas para ver la comparativa."
                    # A les alertes automàtiques no podem posar ReplyKeyboard fàcilment, 
                    # però l'usuari ja el tindrà al seu xat de abans.
                    await context.bot.send_message(chat_id=MI_CHAT_ID, text=msg, parse_mode="Markdown")
        except Exception as e: print(f"Error automàtic: {e}")

if __name__ == '__main__':
    keep_alive()
    app = Application.builder().token(TOKEN_TELEGRAM).build()
    app.add_handler(CommandHandler("start", comando_start))
    app.add_handler(CommandHandler("menu", mostrar_menu))
    app.add_handler(CommandHandler("activas", comando_activas)) 
    app.add_handler(CallbackQueryHandler(gestion_botones))
    
    app.job_queue.run_repeating(revisar_automaticamente, interval=300, first=5)
    app.run_polling()