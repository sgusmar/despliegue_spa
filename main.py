from flask import Flask, request, jsonify
import joblib
import pandas as pd
import os

app = Flask(__name__)

#rutas a los archivos dentro de la carpeta models
MODEL_PATH = os.path.join("models", "modelo_ocupacion.joblib")
SCALER_PATH = os.path.join("models", "scaler.joblib")

#carga de modelo y escalador al arrancar la aplicación
try:
    model = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    print("Modelo y Scaler cargados correctamente.")
except Exception as e:
    model = None
    scaler = None
    print(f"Error cargando archivos: {e}")


@app.route("/", methods=["GET"])
def home():
    """
    Landing page informativa requerida por el enunciado.
    """
    return jsonify({
        "proyecto": "API de Predicción de Ocupación - Spa Oasis",
        "descripcion": "Servicio API REST para predecir el nivel o tramo de ocupación en las instalaciones del spa.",
        "endpoints": {
            "/": "GET - Esta página de bienvenida e instrucciones",
            "/predict": "POST - Envía un JSON con las variables del spa para obtener la predicción de ocupación"
        }
    })


@app.route("/predict", methods=["POST", "GET"])
def predict():
    """
    Endpoint de predicción de ocupación.
    """
    if model is None or scaler is None:
        return jsonify({
            "error": "El modelo o el escalador no están disponibles en el servidor."
        }), 500

    if request.method == "POST":
        data = request.get_json()

        if not data:
            return jsonify({"error": "No se proporcionaron datos en formato JSON"}), 400

        try:
            #se convierte el JSON recibido a DataFrame
            #si se envía un solo registro como dict {} -> [data]
            #si se envía una lista de dicts [{}] -> data
            if isinstance(data, dict):
                input_df = pd.DataFrame([data])
            elif isinstance(data, list):
                input_df = pd.DataFrame(data)
            else:
                return jsonify({"error": "Formato JSON no válido"}), 400

            #se aplica la transformación del scaler
            scaled_features = scaler.transform(input_df)

            #se realiza la predicción
            predictions = model.predict(scaled_features)

            #se convierte a lista nativa de python para serializar en JSON
            results = predictions.tolist()

            return jsonify({
                "status": "success",
                "prediccion_ocupacion": results[0] if len(results) == 1 else results
            })

        except Exception as e:
            return jsonify({
                "error": f"Error al procesar la predicción: {str(e)}"
            }), 400

    #respuesta informativa si se accede por GET al endpoint /predict
    return jsonify({
        "mensaje": "Para realizar una predicción, envía una petición POST con los datos en formato JSON a este endpoint."
    })


if __name__ == "__main__":
    app.run(debug=True)