import os
import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import sqlite3
from flask import Flask
from threading import Thread

load_dotenv()
TOKEN_TELEGRAM = os.getenv("TELEGRAM_TOKEN")
MI_CHAT_ID = os.getenv("MI_CHAT_ID")

# --- SERVIDOR WEB (KEEPALIVE) ---
app_web = Flask(__name__)
@app_web.route('/')
def home(): return "Bot actiu!"

def run(): app_web.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

# --- CONFIGURACIÓ DEL PONT DE GOOGLE ---
# Fem servir la mateixa URL per a tot el bot
URL_PONT_GOOGLE = "https://script.google.com/macros/s/AKfycbxzizXAuxwoTxKMmOPjrQXMfFtCqGlNb3iDlEvpONMv-QsX6-h4aumUfMNxVASmagptxQ/exec"

def inicializar_bd():
    conexion = sqlite3.connect("apuestas.db")
    cursor = conexion.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS enviadas (id_partido INTEGER PRIMARY KEY)')
    conexion.commit()
    conexion.close()

inicializar_bd()

async def comando_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! Bot de alertas listo y usando el puente de Google. 🤖⚽")

async def comando_activas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 Buscando apuestas a través de Google...")
    
    # És vital fer servir follow_redirects=True amb Google Scripts
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            respuesta = await client.get(URL_PONT_GOOGLE, timeout=20.0)
            if respuesta.status_code == 200:
                datos = respuesta.json()
                predicciones = datos.get("predictions", [])
                if predicciones:
                    msg = f"📋 *He encontrado {len(predicciones)} apuestas:* \n\n"
                    for ap in predicciones:
                        msg += f"⚽ *{ap['homeTeamName']} vs {ap['awayTeamName']}*\n🎯 {ap['vote']} | 📈 {ap['odds']['decimalValue']}\n\n"
                    await update.message.reply_text(msg, parse_mode="Markdown")
                else:
                    await update.message.reply_text("No hay apuestas ahora mismo. 🎈")
            else:
                await update.message.reply_text(f"⚠️ Error en el puente: {respuesta.status_code}")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

async def revisar_automaticamente(context: ContextTypes.DEFAULT_TYPE):
    # Aquí també fem servir el pont de Google!
    async with httpx.AsyncClient(follow_redirects=True) as client:
        try:
            res = await client.get(URL_PONT_GOOGLE, timeout=20.0)
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
                    msg = f"🚨 *¡NUEVAS APUESTAS DETECTADAS!*\n\n"
                    for ap in nuevas:
                        msg += f"⚽ *{ap['homeTeamName']} vs {ap['awayTeamName']}*\n🎯 {ap['vote']} | 📈 {ap['odds']['decimalValue']}\n\n"
                    await context.bot.send_message(chat_id=MI_CHAT_ID, text=msg, parse_mode="Markdown")
        except Exception as e:
            print(f"Error automàtic: {e}")

if __name__ == '__main__':
    keep_alive()
    app = Application.builder().token(TOKEN_TELEGRAM).build()
    app.add_handler(CommandHandler("start", comando_start))
    app.add_handler(CommandHandler("activas", comando_activas)) 
    
    # Revisa cada 5 minuts
    app.job_queue.run_repeating(revisar_automaticamente, interval=300, first=5)

    print("Iniciant bot amb pont de Google...")
    app.run_polling()