import os
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import sqlite3

# Cargamos las variables de entorno
load_dotenv()
TOKEN_TELEGRAM = os.getenv("TELEGRAM_TOKEN")
MI_CHAT_ID = os.getenv("MI_CHAT_ID") # ¡Recuperamos tu ID de la caja fuerte!

def inicializar_bd():
    # Esto crea un archivo llamado 'apuestas.db' en tu carpeta
    conexion = sqlite3.connect("apuestas.db")
    cursor = conexion.cursor()
    
    # Creamos una tabla para guardar los IDs si no existe ya
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS enviadas (
            id_partido INTEGER PRIMARY KEY
        )
    ''')
    conexion.commit()
    conexion.close()

# Llamamos a la función nada más arrancar el código
inicializar_bd()

async def comando_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usuario = update.effective_user.first_name
    mensaje_bienvenida = f"¡Hola, {usuario}! Soy tu bot de alertas de Sofascore. Estoy activo y preparado. 🤖⚽"
    await update.message.reply_text(mensaje_bienvenida)

async def comando_activas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (Mantenemos tu código anterior intacto para cuando quieras consultar manualmente)
    await update.message.reply_text("🔎 Buscando apuestas activas en Sofascore...")
    url = "https://www.sofascore.com/api/v1/user-account/678767edb8435cc2d1bba515/predictions/next/0"
    cabeceras = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    
    try:
        respuesta = requests.get(url, headers=cabeceras)
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

# NUEVO: Función automática que se ejecutará en segundo plano
async def revisar_apuestas_automaticamente(context: ContextTypes.DEFAULT_TYPE):
    # Como esta función se ejecuta sola, no usamos print() ni reply_text() para avisar que está buscando, 
    # simplemente lo hace en silencio.
    
    url = "https://www.sofascore.com/api/v1/user-account/678767edb8435cc2d1bba515/predictions/next/0"
    cabeceras = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    
    try:
        respuesta = requests.get(url, headers=cabeceras)
        if respuesta.status_code == 200:
            datos = respuesta.json()
            predicciones = datos.get("predictions", [])
            
            nuevas_apuestas = [] # Lista para guardar solo las que no hemos visto antes
            
            conexion = sqlite3.connect("apuestas.db")
            cursor = conexion.cursor()
            
            for apuesta in predicciones:
                id_unico = apuesta["eventId"] # Usamos el ID del partido como identificador
                
                cursor.execute("SELECT id_partido FROM enviadas WHERE id_partido = ?", (id_unico,))
                resultado = cursor.fetchone()
                
                # Si este ID no está en nuestra memoria, es una alerta NUEVA
                if resultado is None:
                    nuevas_apuestas.append(apuesta)
                    
                    cursor.execute("INSERT INTO enviadas (id_partido) VALUES (?)", (id_unico,))
                    conexion.commit() # Confirmem que volem guardar els canvis
                    
            conexion.close()
            
            # Si hemos encontrado apuestas nuevas, construimos el mensaje y te lo enviamos directamente
            if nuevas_apuestas:
                mensaje_final = f"🚨 *¡NUEVAS APUESTAS DETECTADAS!* ({len(nuevas_apuestas)})\n\n"
                for apuesta in nuevas_apuestas:
                    mensaje_final += (
                        f"⚽ *{apuesta['homeTeamName']} vs {apuesta['awayTeamName']}*\n"
                        f"🎯 Pronóstico: {apuesta['vote']} | 📈 Cuota: {apuesta['odds']['decimalValue']}\n"
                        f"〰️〰️〰️〰️〰️〰️〰️〰️\n"
                    )
                # Fíjate que aquí usamos context.bot.send_message porque no estamos respondiendo a nadie, 
                # estamos iniciando la conversación usando tu MI_CHAT_ID
                await context.bot.send_message(chat_id=MI_CHAT_ID, text=mensaje_final, parse_mode="Markdown")
                
    except Exception as e:
        # En tareas de fondo, los errores se suelen imprimir en la consola (o en un log)
        print(f"Error en revisión automática: {e}")

if __name__ == '__main__':
    app = Application.builder().token(TOKEN_TELEGRAM).build()

    app.add_handler(CommandHandler("start", comando_start))
    app.add_handler(CommandHandler("activas", comando_activas)) 

    # NUEVO: Configuramos el reloj interno (JobQueue)
    # first=5 significa que hará la primera comprobación 5 segundos después de encender el bot
    # interval=300 significa que luego lo repetirá cada 5 minutos (300 segundos)
    app.job_queue.run_repeating(revisar_apuestas_automaticamente, interval=300, first=5)

    print("Iniciando el bot automático... Pulsa Ctrl+C para detenerlo.")
    app.run_polling()