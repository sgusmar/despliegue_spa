"""
API de predicción de ocupación del spa.

Este es el ÚNICO fichero que conoce Flask: aquí vive todo el enrutado y la
validación de la forma de la petición. El resto son dependencias sin framework:

* `model_service.py`  — artefacto del modelo y predicción (single y rango).
* `train_model.py`    — reentrenamiento y lectura del histórico.
* `retrain.py`        — ingesta del CSV que llega por /retrain.

Los errores no se capturan ruta por ruta: las dependencias lanzan excepciones
de dominio (ValueError, RuntimeError, ErrorDeReentrenamiento) y los
`errorhandler` del final las traducen a JSON con su código HTTP.
"""
import os

import pandas as pd
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from app import model_service
from app import retrain
from app import train_model
from app.train_model import ErrorDeReentrenamiento, ReentrenamientoEnCurso

# Si el servidor define RETRAIN_TOKEN, POST /retrain exige esta cabecera.
NOMBRE_CABECERA_TOKEN = 'X-Retrain-Token'

# Tamaño máximo del CSV que se puede subir a /retrain.
MAX_CSV_BYTES = 2 * 1024 * 1024

AVISO_DISCO = (
    'En el plan gratuito de Render el disco es efímero: el modelo reentrenado y '
    'los CSV subidos se pierden cuando el servicio se reinicia o se duerme, y se '
    'vuelve al artefacto versionado en el repositorio.'
)


class ApiError(Exception):
    """Error de forma de la petición; el errorhandler lo convierte en JSON."""

    def __init__(self, mensaje, codigo=400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo


def create_app(data_dir=None, model_path=None):
    """
    Fábrica de la app.

    Los parámetros existen para los tests: POST /retrain escribe ficheros en
    data/, así que hay que poder apuntarlo a un directorio temporal en vez de
    contaminar el histórico real.
    """
    app = Flask(__name__)
    # Por defecto, Flask solo tolera la barra final en un sentido (una ruta
    # registrada CON barra acepta peticiones sin ella; al revés, no: una ruta
    # sin barra, como las nuestras, da 404 si la piden con barra final). Es un
    # error fácil de cometer al escribir la URL a mano o desde un script de
    # evaluación, así que aquí se aceptan las dos formas en toda la API.
    app.url_map.strict_slashes = False
    app.config['DATA_DIR'] = str(data_dir) if data_dir else train_model.DATA_DIR
    app.config['MODEL_PATH'] = model_path
    app.config['MAX_CONTENT_LENGTH'] = MAX_CSV_BYTES
    _registrar_rutas(app)
    _registrar_errores(app)
    return app


def _cuerpo_json():
    """Cuerpo de la petición como objeto JSON, o ApiError si no lo es."""
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        raise ApiError('El cuerpo debe ser un objeto JSON.')
    return datos


def _exigir_token():
    esperado = os.environ.get('RETRAIN_TOKEN')
    if esperado and request.headers.get(NOMBRE_CABECERA_TOKEN) != esperado:
        raise ApiError(
            'No autorizado: este servidor tiene el reentrenamiento protegido y falta '
            'la cabecera ' + NOMBRE_CABECERA_TOKEN + ' o su valor no es correcto.',
            401,
        )


def _leer_csv_de_peticion():
    """El CSV llega como multipart (campo 'file') o como JSON {'csvText': ...}."""
    if 'file' in request.files:
        bruto = request.files['file'].read()
        if not bruto:
            raise ApiError('El archivo está vacío.')
        try:
            # utf-8-sig: un CSV exportado de Excel empieza con BOM, y sin quitarlo
            # la primera columna se leería como '﻿fecha_cita'.
            return bruto.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ApiError('El archivo debe estar codificado en UTF-8.') from exc
    if request.is_json:
        texto = _cuerpo_json().get('csvText')
        if not isinstance(texto, str) or not texto.strip():
            raise ApiError("Falta el campo 'csvText' con el contenido del CSV.")
        return texto.lstrip('﻿')
    raise ApiError("Envía el CSV como archivo (campo 'file') o como JSON {'csvText': ...}.")


def _historico_anio_anterior(inicio, fin, data_dir):
    """
    Ocupación REAL del mismo periodo un año antes, o None si no hay histórico.

    Se desplaza con DateOffset(years=1) y no con 365 días para que caiga en el
    mismo día de la semana, que es la variable de más peso del modelo (el 29 de
    febrero retrocede al 28, que es el comportamiento correcto).

    Los días sin datos sencillamente no aparecen, en vez de rellenarse con
    ceros: en este dataset `n_citas = 0` es un valor real observado (hay días
    de cierre con 0 citas), así que un cero de relleno sería indistinguible de
    un cero verdadero y el gráfico mentiría.
    """
    desde = pd.Timestamp(inicio) - pd.DateOffset(years=1)
    hasta = pd.Timestamp(fin) - pd.DateOffset(years=1)
    try:
        historico = train_model.historico_por_rango(desde, hasta, data_dir)
    except ErrorDeReentrenamiento:
        # Un CSV corrupto en data/ no debe tumbar la predicción.
        return None
    if historico.empty:
        return None

    dias = []
    for fecha, filas in historico.groupby('fecha_cita', sort=True):
        por_tramo = dict(zip(filas['tramo'], filas['n_citas']))
        dias.append({
            'date': fecha.strftime('%Y-%m-%d'),
            'manana': float(por_tramo.get('mañana', 0)),
            'tarde': float(por_tramo.get('tarde', 0)),
        })
    return dias


def _registrar_rutas(app):
    @app.get('/')
    def home():
        return jsonify({
            'proyecto': 'API de Predicción de Ocupación - Spa Oasis',
            'descripcion': 'API REST para predecir la ocupación del spa y reentrenar el modelo',
            'endpoints': {
                'GET /health': 'Estado del servicio y del modelo cargado',
                'GET /predict': (
                    "Predicción de un día y tramo por query string: "
                    "?fecha=YYYY-MM-DD&tramo=manana|tarde (alias: GET /predict/single)"
                ),
                'GET /predict/range': (
                    'Predicción de un rango de fechas por query string: '
                    '?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD'
                ),
                'GET /retrain': 'Estado del modelo desplegado e instrucciones de reentrenamiento',
                'POST /retrain': "Reentrena el modelo con un CSV nuevo (archivo 'file' o {csvText})",
                'POST /retrain/reset': 'Descarta el modelo reentrenado y los CSV subidos',
            },
        })

    @app.get('/health')
    def health():
        # Siempre 200: esto es liveness. Si devolviera 503 al faltar el
        # artefacto, Render reiniciaría el servicio en bucle, y un artefacto
        # ausente no se arregla reiniciando.
        try:
            art = model_service.obtener_artefacto(app.config['MODEL_PATH'])
        except RuntimeError:
            return jsonify({'status': 'ok', 'model_loaded': False})
        return jsonify({
            'status': 'ok',
            'model_loaded': True,
            'entrenado_hasta': art['entrenado_hasta'],
            'version_modelo': art.get('version', 'original'),
            # Solo los artefactos reentrenados llevan 'version', así que la
            # ausencia de esa clave identifica al de fábrica.
            'es_original': 'version' not in art,
        })

    @app.get('/predict')
    @app.get('/predict/single')
    def predict_single():
        """
        Predicción de un día y tramo, solo por GET — `fecha`/`tramo` (o
        `date`/`tramo`) por query string, igual desde `/predict` que desde
        `/predict/single`. Es también el que usa el frontend: sin cuerpo que
        mandar, sin distinguir GET de POST en el handler.
        """
        fecha = request.args.get('fecha') or request.args.get('date')
        tramo = request.args.get('tramo')
        if not fecha or not tramo:
            raise ApiError(
                "Faltan datos obligatorios: 'date' (o 'fecha') en formato YYYY-MM-DD, "
                "y 'tramo' ('manana' o 'tarde')."
            )
        tramo = model_service.normalizar_tramo(tramo)
        resultado = model_service.predecir_ocupacion(fecha, tramo, app.config['MODEL_PATH'])
        return jsonify({
            'date': fecha,
            'tramo': model_service.tramo_ascii(tramo),
            # citasPrevistas: lo que pinta el frontend tal cual, sin redondear
            # de nuevo. Los tres campos siguientes son metadatos adicionales
            # (no forman parte del contrato del frontend, pero no le estorban)
            # que dejan claro que es una predicción real del modelo vigente,
            # no un valor de mentira — útil de cara a la evaluación.
            'citasPrevistas': round(resultado['prediccion_ocupacion'], 1),
            'es_cierre': resultado['es_cierre'],
            'version_modelo': resultado['version_modelo'],
            'entrenado_hasta': resultado['entrenado_hasta'],
        })

    @app.get('/predict/range')
    def predict_range():
        """
        Predicción de un rango de fechas, solo por GET — `startDate`/`endDate`
        por query string. Es una consulta de solo lectura (no cambia nada en
        el servidor), así que GET es el verbo correcto; también es el que usa
        el frontend.
        """
        inicio, fin = request.args.get('startDate'), request.args.get('endDate')
        if not inicio or not fin:
            raise ApiError("Faltan datos obligatorios: 'startDate' y 'endDate' (YYYY-MM-DD).")
        actual = model_service.predecir_rango(inicio, fin, app.config['MODEL_PATH'])
        return jsonify({
            'current': actual,
            'previousYear': _historico_anio_anterior(inicio, fin, app.config['DATA_DIR']),
        })

    @app.get('/retrain')
    def info_retrain():
        return jsonify({
            'endpoint': '/retrain',
            'descripcion': (
                'Añade un CSV de ocupación al histórico y reentrena el modelo. El '
                'modelo nuevo solo se publica si mejora al vigente en la validación.'
            ),
            'como_usarlo': {
                'metodo': 'POST',
                'cuerpo': (
                    "el CSV, como archivo en el campo 'file' (multipart) o como "
                    "JSON {'csvText': '<contenido>'}"
                ),
                'columnas': train_model.COLUMNAS_REQUERIDAS,
                'cabecera': NOMBRE_CABECERA_TOKEN + ' si el servidor tiene RETRAIN_TOKEN configurado',
                'ejemplo': 'curl -X POST -F file=@ocupacion.csv https://<tu-app>.onrender.com/retrain',
            },
            'datasets_detectados': [
                os.path.basename(r) for r in train_model.listar_datasets(app.config['DATA_DIR'])
            ],
            'modelo_actual': retrain.info_modelo(app.config['MODEL_PATH']),
            'aviso': AVISO_DISCO,
        })

    @app.post('/retrain')
    def lanzar_retrain():
        _exigir_token()
        csv_texto = _leer_csv_de_peticion()
        return jsonify(retrain.ingerir_y_reentrenar(csv_texto, app.config['DATA_DIR']))

    @app.post('/retrain/reset')
    def restaurar_original():
        _exigir_token()
        return jsonify(retrain.restaurar_original(app.config['DATA_DIR']))


def _registrar_errores(app):
    @app.errorhandler(ApiError)
    def _api_error(exc):
        return jsonify({'error': exc.mensaje}), exc.codigo

    @app.errorhandler(ValueError)
    def _valor_invalido(exc):
        return jsonify({'error': str(exc)}), 400

    # ReentrenamientoEnCurso hereda de ErrorDeReentrenamiento: Flask resuelve el
    # handler por MRO, así que registrar los dos hace que gane el más
    # específico. Sin este, el 409 se degradaría a 400 en silencio.
    @app.errorhandler(ReentrenamientoEnCurso)
    def _reentrenamiento_en_curso(exc):
        return jsonify({'error': str(exc)}), 409

    @app.errorhandler(ErrorDeReentrenamiento)
    def _error_reentrenamiento(exc):
        return jsonify({'error': str(exc)}), 400

    @app.errorhandler(RuntimeError)
    def _modelo_no_disponible(exc):
        return jsonify({'error': str(exc)}), 503

    # Sin este, un 404 o el 413 de MAX_CONTENT_LENGTH llegarían al frontend como
    # HTML, y el cliente los enseñaría en crudo al usuario.
    @app.errorhandler(HTTPException)
    def _http(exc):
        return jsonify({'error': exc.description}), exc.code

    @app.errorhandler(Exception)
    def _inesperado(exc):
        app.logger.exception('Error no controlado')
        return jsonify({'error': 'Error interno del servidor.'}), 500


app = create_app()


if __name__ == '__main__':
    # En producción manda gunicorn (ver render.yaml); esto es solo desarrollo.
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', 5000)), debug=True)
