import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq

app = Flask(__name__)

# En producción, limita el origin a tu dominio real en vez de "*"
CORS(app, resources={r"/api/*": {"origins": "*"}})

# La key SOLO vive en el servidor, nunca en el navegador.
# Se lee de una variable de entorno (la configuras en Render/Railway/etc, no en el código).
client = Groq(api_key=os.environ["GROQ_API_KEY"])

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


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
