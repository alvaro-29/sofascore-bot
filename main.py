import os
import httpx
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import sqlite3

# Importem Flask i Thread per crear el servidor web fals
from flask import Flask
from threading import Thread

# Carreguem les variables d'entorn
load_dotenv()
TOKEN_TELEGRAM = os.getenv("TELEGRAM_TOKEN")
MI_CHAT_ID = os.getenv("MI_CHAT_ID") # Recuperem el teu ID de la caixa forta!

# --- INICI DEL SERVIDOR WEB PER RENDER ---
app_web = Flask(__name__)

# Aquesta funció respondrà a les visites externes per evitar que Render s'apagui
@app_web.route('/')
def home():
    return "El bot de Sofascore està actiu i funcionant 24/7!"

# Funció per arrencar el servidor web en un port específic
def run():
    app_web.run(host='0.0.0.0', port=8080)

# Funció que crea un fil (thread) separat perquè el web no bloquegi el bot
def keep_alive():
    t = Thread(target=run)
    t.start()
# --- FI DEL SERVIDOR WEB ---

def inicializar_bd():
    # Això crea un fitxer anomenat 'apuestas.db' a la teva carpeta
    conexion = sqlite3.connect("apuestas.db")
    cursor = conexion.cursor()
    
    # Creem una taula per guardar els IDs si no existeix
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS enviadas (
            id_partido INTEGER PRIMARY KEY
        )
    ''')
    conexion.commit()
    conexion.close()

# Cridem la funció només arrencar el codi
inicializar_bd()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Origin": "https://www.sofascore.com",
    "Referer": "https://www.sofascore.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site"
}

async def comando_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usuario = update.effective_user.first_name
    mensaje_bienvenida = f"¡Hola, {usuario}! Soy tu bot de alertas de Sofascore. Estoy activo y preparado. 🤖⚽"
    await update.message.reply_text(mensaje_bienvenida)

async def comando_activas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 Buscando apuestas en Sofascore con nuevo disfraz...")
    url = "https://www.sofascore.com/api/v1/user-account/678767edb8435cc2d1bba515/predictions/next/0"
    
    async with httpx.AsyncClient(http2=True) as client:
        try:
            # Fem la petició amb el nou format
            respuesta = await client.get(url, headers=HEADERS, timeout=15.0)
            
            if respuesta.status_code == 200:
                datos = respuesta.json()
                predicciones = datos.get("predictions", [])
                
                if predicciones:
                    msg = f"📋 *He encontrado {len(predicciones)} apuestas:*\n\n"
                    for ap in predicciones:
                        msg += f"⚽ *{ap['homeTeamName']} vs {ap['awayTeamName']}*\n🎯 {ap['vote']} | 📈 {ap['odds']['decimalValue']}\n\n"
                    await update.message.reply_text(msg, parse_mode="Markdown")
                else:
                    await update.message.reply_text("No hay apuestas ahora mismo. 🎈")
            else:
                await update.message.reply_text(f"⚠️ Error {respuesta.status_code}. Sofascore sigue bloqueando el acceso.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error de conexión: {e}")

async def revisar_automaticamente(context: ContextTypes.DEFAULT_TYPE):
    url = "https://www.sofascore.com/api/v1/user-account/678767edb8435cc2d1bba515/predictions/next/0"
    async with httpx.AsyncClient(http2=True) as client:
        try:
            res = await client.get(url, headers=HEADERS, timeout=15.0)
            if res.status_code == 200:
                predicciones = res.json().get("predictions", [])
                conexion = sqlite3.connect("apuestas.db")
                cursor = conexion.cursor()
                cursor.execute('CREATE TABLE IF NOT EXISTS enviadas (id_partido INTEGER PRIMARY KEY)')
                
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
                    msg = f"🚨 *¡NUEVAS APUESTAS!*\n\n"
                    for ap in nuevas:
                        msg += f"⚽ *{ap['homeTeamName']} vs {ap['awayTeamName']}*\n🎯 {ap['vote']} | 📈 {ap['odds']['decimalValue']}\n\n"
                    await context.bot.send_message(chat_id=MI_CHAT_ID, text=msg, parse_mode="Markdown")
        except Exception as e:
            print(f"Error automàtic: {e}")
            
if __name__ == '__main__':
    # 1. Primer, encenem el servidor fals en segon pla perquè Render estigui content
    keep_alive()

    # 2. Configurem i engeguem el bot
    app = Application.builder().token(TOKEN_TELEGRAM).build()

    app.add_handler(CommandHandler("start", comando_start))
    app.add_handler(CommandHandler("activas", comando_activas)) 

    # Configurem el rellotge intern per repetir cada 5 minuts (300 segons)
    app.job_queue.run_repeating(revisar_automaticamente, interval=300, first=5)

    print("Iniciant el bot automàtic... Prem Ctrl+C per aturar-lo.")
    app.run_polling()