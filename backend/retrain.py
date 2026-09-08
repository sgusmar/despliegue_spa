"""
Endpoint de reentrenamiento del modelo (extra voluntario del enunciado).

Se define como un **Blueprint** de Flask en vez de escribirlo dentro de
`main.py` a propósito: así el lane de reentrenamiento no toca el fichero que
están editando a la vez los demás roles, y la integración se reduce a dos
líneas en `main.py`:

    from retrain import retrain_bp
    app.register_blueprint(retrain_bp)

Para probarlo por separado, sin depender de `main.py`:

    python retrain.py           # -> http://127.0.0.1:5001/retrain
"""
import os
import threading

from flask import Blueprint, jsonify, request

import train_model
from train_model import ErrorDeReentrenamiento, ReentrenamientoEnCurso, reentrenar
from werkzeug.exceptions import BadRequest

retrain_bp = Blueprint("reentrenamiento", __name__)

# Un reentrenamiento a la vez: si llegan dos peticiones simultáneas, la segunda
# recibe un 409 en vez de pelearse con la primera por escribir el mismo fichero.
_candado = threading.Lock()

# Token opcional. Si la variable de entorno está definida (en Render, no en el
# código — como pide el enunciado), /retrain exige la cabecera X-Retrain-Token.
# Si no está definida, el endpoint queda abierto, que es lo cómodo para la demo
# en clase.
NOMBRE_CABECERA_TOKEN = "X-Retrain-Token"


def _token_valido():
    esperado = os.environ.get("RETRAIN_TOKEN")
    if not esperado:
        return True
    return request.headers.get(NOMBRE_CABECERA_TOKEN) == esperado


@retrain_bp.route("/retrain", methods=["GET"])
def info_retrain():
    """Documentación del endpoint y estado del modelo desplegado ahora mismo."""
    import joblib

    modelo_actual = {"disponible": False}
    if os.path.exists(train_model.MODEL_PATH):
        try:
            art = joblib.load(train_model.MODEL_PATH)
            modelo_actual = {
                "disponible": True,
                "algoritmo": art.get("nombre"),
                "entrenado_hasta": art.get("entrenado_hasta"),
                "mae": art.get('validacion', {}).get('mae', art.get('mae_cv')),
                "version_modelo": art.get('version', 'original'),
                "reentrenado_el": art.get("reentrenado_el", "nunca (artefacto original)"),
            }
        except Exception as e:
            modelo_actual = {"disponible": False, "error": str(e)}

    return jsonify({
        "endpoint": "/retrain",
        "descripcion": (
            "Reentrena el modelo de ocupación con todos los CSV presentes en "
            "data/. Para lanzarlo, haz una petición POST a esta misma URL."
        ),
        "como_usarlo": {
            "metodo": "POST",
            "cuerpo": "no hace falta ninguno",
            "opcional": {
                "dias_validacion": (
                    "entero, días finales reservados para validar "
                    "(por defecto " + str(train_model.DIAS_VALIDACION) + ")"
                )
            },
            "cabecera": (
                NOMBRE_CABECERA_TOKEN + " si el servidor tiene RETRAIN_TOKEN configurado"
            ),
            "ejemplo": "curl -X POST https://<tu-app>.onrender.com/retrain",
        },
        "datasets_detectados": [
            os.path.basename(r) for r in train_model.listar_datasets()
        ],
        "modelo_actual": modelo_actual,
        "aviso": (
            "En el plan gratuito de Render el disco es efímero: el modelo "
            "reentrenado se pierde cuando el servicio se reinicia o se duerme, "
            "y se vuelve al artefacto versionado en el repositorio."
        ),
    })


@retrain_bp.route("/retrain", methods=["POST"])
def lanzar_retrain():
    """Reentrena el modelo y devuelve el informe de lo ocurrido."""
    if not _token_valido():
        return jsonify({
            "error": "No autorizado.",
            "detalle": (
                "Este servidor tiene el reentrenamiento protegido: falta la "
                "cabecera " + NOMBRE_CABECERA_TOKEN + " o su valor no es correcto."
            ),
        }), 401

    if request.get_data() and not request.is_json:
        return jsonify({'error': 'El cuerpo debe ser JSON.'}), 400
    try:
        datos = request.get_json() if request.get_data() else {}
    except BadRequest:
        return jsonify({'error': 'JSON mal formado.'}), 400
    if not isinstance(datos, dict):
        return jsonify({'error': 'El cuerpo JSON debe ser un objeto.'}), 400
    dias = datos.get("dias_validacion", train_model.DIAS_VALIDACION)
    if type(dias) is not int:
        return jsonify({
            "error": "El campo 'dias_validacion' debe ser un número entero.",
            "recibido": datos.get("dias_validacion"),
        }), 400
    if dias < 7:
        return jsonify({
            "error": "'dias_validacion' debe ser al menos 7 para que la validación tenga sentido.",
            "recibido": dias,
        }), 400

    if not _candado.acquire(blocking=False):
        return jsonify({
            "error": "Ya hay un reentrenamiento en curso. Espera a que termine.",
        }), 409

    try:
        informe = reentrenar(dias_validacion=dias)
    except ReentrenamientoEnCurso as e:
        return jsonify({'error': str(e)}), 409
    except ErrorDeReentrenamiento as e:
        return jsonify({"error": "No se ha podido reentrenar.", "detalle": str(e)}), 400
    except Exception as e:
        return jsonify({
            "error": "Error inesperado durante el reentrenamiento.",
            "detalle": "{}: {}".format(type(e).__name__, e),
        }), 500
    finally:
        _candado.release()

    codigo = 200 if informe["estado"] == "reemplazado" else 409
    return jsonify(informe), codigo


if __name__ == "__main__":
    # Servidor de desarrollo solo para probar este lane por separado, sin
    # depender de main.py. En producción manda main.py + gunicorn.
    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(retrain_bp)
    app.run(port=5001, debug=True)
