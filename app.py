import os
import base64
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq

app = Flask(__name__)

# En producción, limita el origin a tu dominio real en vez de "*"
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Las keys SOLO viven en el servidor, nunca en el navegador.
# Se leen de variables de entorno (las configuras en Render, no en el código).
client = Groq(api_key=os.environ["GROQ_API_KEY"])
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")

# Voz de ElevenLabs a usar. "Antoni" es una voz masculina en inglés que suena bien
# con tono grave; puedes cambiar este ID por cualquier voice_id de tu cuenta de ElevenLabs
# (Voice Library -> elige una voz en español -> copia su Voice ID).
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "onwK4e9ZLuTAKqWW03F9")

SYSTEM_PROMPT = """Eres Rodrigo Díaz de Vivar, el Cid Campeador.
Respondes siempre en primera persona como si fueras él en carne y hueso.
Hablas con dignidad, valentía y honor, reflejando tu época del siglo XI.
Conoces todos los detalles del Cantar de Mio Cid: tu destierro, tus batallas,
tu familia, la conquista de Valencia, los infantes de Carrión, el rey Alfonso VI.
Puedes hablar en castellano moderno pero con cierto tono épico y solemne."""

# Guardamos el historial por sesión en memoria (simple, para un solo servidor).
# Si esperas más tráfico o varias instancias, cambia esto por Redis o una base de datos.
sesiones = {}

MAX_TURNOS = 20  # evita que el historial crezca sin límite y dispare costos

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True) or {}
    mensaje = (data.get("mensaje") or "").strip()
    sesion_id = data.get("sesion_id") or "default"

    if not mensaje:
        return jsonify({"error": "Falta el campo 'mensaje'"}), 400

    if sesion_id not in sesiones:
        sesiones[sesion_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    historial = sesiones[sesion_id]
    historial.append({"role": "user", "content": mensaje})

    # Recorta el historial si crece demasiado (deja el system prompt intacto)
    if len(historial) > MAX_TURNOS * 2 + 1:
        historial = [historial[0]] + historial[-(MAX_TURNOS * 2):]
        sesiones[sesion_id] = historial

    try:
        respuesta = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=historial,
        )
        texto = respuesta.choices[0].message.content
    except Exception as e:
        return jsonify({"error": f"Error al contactar al modelo: {e}"}), 500

    historial.append({"role": "assistant", "content": texto})

    return jsonify({"respuesta": texto})


@app.route("/api/voz", methods=["POST"])
def voz():
    """Igual que /api/chat, pero además devuelve el audio de la respuesta en base64."""
    data = request.get_json(force=True) or {}
    mensaje = (data.get("mensaje") or "").strip()
    sesion_id = data.get("sesion_id") or "default"

    if not mensaje:
        return jsonify({"error": "Falta el campo 'mensaje'"}), 400

    if not ELEVENLABS_API_KEY:
        return jsonify({"error": "Falta configurar ELEVENLABS_API_KEY en el servidor"}), 500

    if sesion_id not in sesiones:
        sesiones[sesion_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    historial = sesiones[sesion_id]
    historial.append({"role": "user", "content": mensaje})

    if len(historial) > MAX_TURNOS * 2 + 1:
        historial = [historial[0]] + historial[-(MAX_TURNOS * 2):]
        sesiones[sesion_id] = historial

    try:
        respuesta = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=historial,
        )
        texto = respuesta.choices[0].message.content
    except Exception as e:
        return jsonify({"error": f"Error al contactar al modelo: {e}"}), 500

    historial.append({"role": "assistant", "content": texto})

    # Generamos el audio con ElevenLabs a partir del texto de respuesta
    try:
        tts_resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "text": texto,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.4, "similarity_boost": 0.75},
            },
            timeout=30,
        )
        tts_resp.raise_for_status()
        audio_b64 = base64.b64encode(tts_resp.content).decode("utf-8")
    except Exception as e:
        # Si falla la voz, al menos devolvemos el texto para no perder la respuesta
        return jsonify({"respuesta": texto, "audio_base64": None, "error_voz": str(e)})

    return jsonify({"respuesta": texto, "audio_base64": audio_b64})


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
