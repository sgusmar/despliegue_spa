from flask import Flask, request, jsonify
from model_service import predecir_ocupacion
from retrain import retrain_bp
from root import root_bp

app = Flask(__name__)

#registrar la ruta de reentrenamiento creada por mi compañero
app.register_blueprint(retrain_bp)
# registrar la ruta de root
app.register_blueprint(root_bp)


@app.route("/predict", methods=["POST", "GET"])
def predict():
    if request.method == "POST":
        data = request.get_json()

        #comprobar que nos envían un JSON
        if not data:
            return jsonify({"error": "No se enviaron datos en la petición"}), 400

        #guardar las variables del formulario/front
        fecha = data.get("fecha")
        tramo = data.get("tramo")

        #validar que no falte ningún campo
        if not fecha or not tramo:
            return jsonify({
                "error": "Faltan datos obligatorios. Debes enviar 'fecha' (YYYY-MM-DD) y 'tramo' ('mañana' o 'tarde')."
            }), 400

        try:
            #llamada a la función de predicción de model_service
            resultado = predecir_ocupacion(fecha, tramo)

            return jsonify({
                "status": "success",
                "resultado": resultado
            })

        except ValueError as e:
            #errores de validación de fechas o tramos
            return jsonify({"error": str(e)}), 400
        except RuntimeError as e:
            #errores en caso de que el modelo no esté disponible
            return jsonify({"error": str(e)}), 500
        except Exception as e:
            return jsonify({"error": f"Error inesperado procesando la predicción: {str(e)}"}), 500

    #mensaje por si se accede a /predict usando GET
    return jsonify({
        "mensaje": "Envía una petición POST con 'fecha' y 'tramo' en formato JSON para obtener una predicción."
    })


if __name__ == "__main__":
    app.run(debug=True)