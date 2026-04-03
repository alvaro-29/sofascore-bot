import os
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

async def comando_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usuario = update.effective_user.first_name
    mensaje_bienvenida = f"¡Hola, {usuario}! Soy tu bot de alertas de Sofascore. Estoy activo y preparado. 🤖⚽"
    await update.message.reply_text(mensaje_bienvenida)

async def comando_activas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Mantenim el teu codi anterior intacte per quan vulguis consultar manualment
    await update.message.reply_text("🔎 Buscando apuestas activas en Sofascore...")
    url = "https://www.sofascore.com/api/v1/user-account/678767edb8435cc2d1bba515/predictions/next/0"
    cabeceras = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    
    try:
        respuesta = requests.get(url, headers=cabeceras)
        print(f"DEBUG: Código de respuesta: {respuesta.status_code}")
        if respuesta.status_code == 200:
            datos = respuesta.json()
            predicciones = datos.get("predictions", [])
            
            if predicciones:
                mensaje_final = f"📋 *He encontrado {len(predicciones)} apuestas activas:*\n\n"
                for apuesta in predicciones:
                    mensaje_final += (
                        f"⚽ *{apuesta['homeTeamName']} vs {apuesta['awayTeamName']}*\n"
                        f"🎯 Pronóstico: {apuesta['vote']} | 📈 Cuota: {apuesta['odds']['decimalValue']}\n"
                        f"〰️〰️〰️〰️〰️〰️〰️〰️\n"
                    )
                await update.message.reply_text(mensaje_final, parse_mode="Markdown")
            else:
                await update.message.reply_text("No hay apuestas activas en este momento. 🎈")
    except Exception as e:
        await update.message.reply_text(f"❌ Error interno: {e}")

async def revisar_apuestas_automaticamente(context: ContextTypes.DEFAULT_TYPE):
    # Com que aquesta funció s'executa sola, ho fa en silenci
    url = "https://www.sofascore.com/api/v1/user-account/678767edb8435cc2d1bba515/predictions/next/0"
    cabeceras = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    
    try:
        respuesta = requests.get(url, headers=cabeceras)
        if respuesta.status_code == 200:
            datos = respuesta.json()
            predicciones = datos.get("predictions", [])
            
            nuevas_apuestas = [] # Llista per guardar només les que no hem vist abans
            
            conexion = sqlite3.connect("apuestas.db")
            cursor = conexion.cursor()
            
            for apuesta in predicciones:
                id_unico = apuesta["eventId"] # Utilitzem l'ID del partit com a identificador
                
                cursor.execute("SELECT id_partido FROM enviadas WHERE id_partido = ?", (id_unico,))
                resultado = cursor.fetchone()
                
                # Si aquest ID no està a la nostra memòria, és una alerta NOVA
                if resultado is None:
                    nuevas_apuestas.append(apuesta)
                    
                    cursor.execute("INSERT INTO enviadas (id_partido) VALUES (?)", (id_unico,))
                    conexion.commit() # Confirmem que volem guardar els canvis
                    
            conexion.close()
            
            # Si hem trobat apostes noves, construïm el missatge i te l'enviem
            if nuevas_apuestas:
                mensaje_final = f"🚨 *¡NUEVAS APUESTAS DETECTADAS!* ({len(nuevas_apuestas)})\n\n"
                for apuesta in nuevas_apuestas:
                    mensaje_final += (
                        f"⚽ *{apuesta['homeTeamName']} vs {apuesta['awayTeamName']}*\n"
                        f"🎯 Pronóstico: {apuesta['vote']} | 📈 Cuota: {apuesta['odds']['decimalValue']}\n"
                        f"〰️〰️〰️〰️〰️〰️〰️〰️\n"
                    )
                # Iniciem la conversa utilitzant el teu MI_CHAT_ID
                await context.bot.send_message(chat_id=MI_CHAT_ID, text=mensaje_final, parse_mode="Markdown")
                
    except Exception as e:
        # En tasques de fons, els errors s'imprimeixen a la consola
        print(f"Error en revisión automática: {e}")

if __name__ == '__main__':
    # 1. Primer, encenem el servidor fals en segon pla perquè Render estigui content
    keep_alive()

    # 2. Configurem i engeguem el bot
    app = Application.builder().token(TOKEN_TELEGRAM).build()

    app.add_handler(CommandHandler("start", comando_start))
    app.add_handler(CommandHandler("activas", comando_activas)) 

    # Configurem el rellotge intern per repetir cada 5 minuts (300 segons)
    app.job_queue.run_repeating(revisar_apuestas_automaticamente, interval=300, first=5)

    print("Iniciant el bot automàtic... Prem Ctrl+C per aturar-lo.")
    app.run_polling()