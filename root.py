"""
Endpoint raíz ("/") de la API (parte obligatoria del enunciado).

Landing page con la info de la API y los endpoints disponibles.
Se define como Blueprint, para no tener que modificar main.py mucho:

    from root import root_bp
    app.register_blueprint(root_bp)

Para probarlo por separado, sin depender de main.py:

    python root.py           # -> http://127.0.0.1:5002/
"""
from flask import Blueprint, jsonify

root_bp = Blueprint("root", __name__)


@root_bp.route("/", methods=["GET"])
def home():
    return jsonify({
        "proyecto": "API de Predicción de Ocupación - Spa Oasis",
        "descripcion": "API REST para predecir la ocupación del spa y reentrenar el modelo",
        "endpoints": {
            "/": "GET - Mensaje de bienvenida e instrucciones",
            "/predict": "POST - Recibe fecha (YYYY-MM-DD) y tramo (mañana/tarde) para devolver la predicción de ocupación",
            "/retrain": "POST - Ejecuta el reentrenamiento del modelo con nuevos datos"
        }
    })


if __name__ == "__main__":
    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(root_bp)
    app.run(port=5002, debug=True)