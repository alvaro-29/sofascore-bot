import os
import httpx
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import sqlite3
from flask import Flask
from threading import Thread

load_dotenv()
TOKEN_TELEGRAM = os.getenv("TELEGRAM_TOKEN")
MI_CHAT_ID = os.getenv("MI_CHAT_ID")

# --- CONFIGURACIÓ ---
URL_PONT_GOOGLE = "https://script.google.com/macros/s/AKfycbzNv_4YqY0fBEpR9yNwAebEbgbcsJ0NMwJDN3H_Y-oeT05bTaIom2yWoKyPiBitR8DP/exec"

TIPSTERS = {
    "🏆 Top 1": "678767edb8435cc2d1bba515",
    "🥈 Top 2": "6758979fed09a67b595d5ba2",
    "🥉 Top 3": "68e0f8743fc35ff674f3ad74"
}

USER_ACTUAL = "678767edb8435cc2d1bba515" # ID per defecte

# --- SERVIDOR WEB (KEEPALIVE) ---
app_web = Flask(__name__)
@app_web.route('/')
def home(): return "Bot actiu!"

def run(): app_web.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

def inicializar_bd():
    conexion = sqlite3.connect("apuestas.db")
    cursor = conexion.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS enviadas (id_partido INTEGER PRIMARY KEY)')
    conexion.commit()
    conexion.close()

inicializar_bd()

# --- COMANDOS ---
async def comando_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! Usa /menu para elegir a qué tipster seguir. 🤖⚽")

async def mostrar_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for nombre, tid in TIPSTERS.items():
        keyboard.append([InlineKeyboardButton(nombre, callback_data=tid)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🏆 **Selecciona un tipster para vigilar:**", reply_markup=reply_markup, parse_mode="Markdown")

async def gestion_botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_ACTUAL
    query = update.callback_query
    await query.answer()
    
    USER_ACTUAL = query.data
    nombre = [n for n, tid in TIPSTERS.items() if tid == USER_ACTUAL][0]
    
    await query.edit_message_text(text=f"✅ Ahora vigilando a: *{nombre}*", parse_mode="Markdown")

async def comando_activas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🔎 Buscando apuestas del usuario actual...")
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            # Enviem l'ID actual a Google
            respuesta = await client.get(f"{URL_PONT_GOOGLE}?id={USER_ACTUAL}", timeout=20.0)
            if respuesta.status_code == 200:
                datos = respuesta.json()
                predicciones = datos.get("predictions", [])
                if predicciones:
                    msg = f"📋 *Apuestas de {USER_ACTUAL}:* \n\n"
                    for ap in predicciones:
                        msg += f"⚽ *{ap['homeTeamName']} vs {ap['awayTeamName']}*\n🎯 {ap['vote']} | 📈 {ap['odds']['decimalValue']}\n\n"
                    await update.message.reply_text(msg, parse_mode="Markdown")
                else:
                    await update.message.reply_text("No hay apuestas ahora mismo. 🎈")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

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
                    msg = f"🚨 *¡NUEVA ALERTA!* ({USER_ACTUAL})\n\n"
                    for ap in nuevas:
                        msg += f"⚽ *{ap['homeTeamName']} vs {ap['awayTeamName']}*\n🎯 {ap['vote']} | 📈 {ap['odds']['decimalValue']}\n\n"
                    await context.bot.send_message(chat_id=MI_CHAT_ID, text=msg, parse_mode="Markdown")
        except Exception as e:
            print(f"Error automàtic: {e}")

if __name__ == '__main__':
    keep_alive()
    app = Application.builder().token(TOKEN_TELEGRAM).build()
    app.add_handler(CommandHandler("start", comando_start))
    app.add_handler(CommandHandler("menu", mostrar_menu))
    app.add_handler(CommandHandler("activas", comando_activas)) 
    app.add_handler(CallbackQueryHandler(gestion_botones)) # Gestor de clics
    
    app.job_queue.run_repeating(revisar_automaticamente, interval=300, first=5)
    app.run_polling()