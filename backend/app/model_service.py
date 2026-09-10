"""Contrato compartido de artefactos y predicción; no depende de Flask."""
from pathlib import Path
import re
import threading

import joblib
import numpy as np
import pandas as pd

from .utils.feature_engineering import construir_features_df
from .utils.preprocessing import build_features

# .parent.parent: este fichero vive en app/, y models/ es hermano de app/, no
# hijo suyo (backend/models/, no backend/app/models/).
MODELS_DIR = Path(__file__).resolve().parent.parent / 'models'

# Artefacto de fábrica: viaja versionado en el repositorio y NUNCA se
# sobrescribe. Por eso volver al original es siempre posible, y no depende de
# que exista una copia de seguridad.
MODEL_BASE_PATH = MODELS_DIR / 'modelo_ocupacion.joblib'

# Donde publica el reentrenamiento. Si existe, manda sobre el de fábrica; para
# restaurar el original basta con borrarlo.
MODEL_ACTIVE_PATH = MODELS_DIR / 'modelo_reentrenado.joblib'

# Tope de /predict/range: un año natural cabe entero (para comparar con el año
# anterior) y evita que una petición accidental pida miles de días.
MAX_DIAS_RANGO = 366

# Orden canónico de los tramos dentro de un día.
TRAMOS = ('mañana', 'tarde')

# El frontend manda 'manana' sin ñ (es una clave literal de sus gráficos), así
# que la ñ se queda como detalle interno del modelo y del dataset.
_TRAMOS_ACEPTADOS = {'manana': 'mañana', 'mañana': 'mañana', 'tarde': 'tarde'}

_cache = {'clave': None, 'artefacto': None}
_cache_lock = threading.Lock()


def normalizar_tramo(valor):
    """Cualquier forma admitida -> el tramo canónico con el que se entrenó."""
    tramo = _TRAMOS_ACEPTADOS.get(str(valor).strip().lower())
    if tramo is None:
        raise ValueError("tramo debe ser 'manana' o 'tarde'.")
    return tramo


def tramo_ascii(tramo):
    """Inverso de normalizar_tramo: por el cable nunca viaja la ñ."""
    return 'manana' if tramo == 'mañana' else 'tarde'


def ruta_modelo_vigente():
    """El reentrenado si lo hay; si no, el de fábrica."""
    return MODEL_ACTIVE_PATH if MODEL_ACTIVE_PATH.exists() else MODEL_BASE_PATH


def cargar_artefacto(model_path=None):
    """Carga una versión completa; admite el formato original separado."""
    path = Path(model_path) if model_path else ruta_modelo_vigente()
    art = joblib.load(path)
    if not isinstance(art, dict) or not {'modelo', 'columnas', 'entrenado_hasta'} <= art.keys():
        raise ValueError('Formato de artefacto incompatible.')
    if 'scaler' not in art:
        art['scaler'] = joblib.load(path.with_name('scaler.joblib'))
    return art


def obtener_artefacto(model_path=None):
    """
    Versión vigente del artefacto, cacheada en memoria.

    Se recarga sola cuando el .joblib cambia, así un reentrenamiento surte
    efecto sin reiniciar el servicio. Se compara `st_mtime_ns` y no `st_mtime`
    porque el float tiene resolución de ~1 s en algunos sistemas de ficheros y
    una publicación puede caer dentro del mismo segundo que la última carga.
    """
    ruta = Path(model_path) if model_path else ruta_modelo_vigente()
    try:
        estado = ruta.stat()
    except OSError as exc:
        raise RuntimeError('El modelo no está disponible.') from exc
    clave = (str(ruta), estado.st_mtime_ns, estado.st_size)

    with _cache_lock:
        if _cache['clave'] == clave:
            return _cache['artefacto']

    # Fuera del candado: en frío la carga tarda ~1 s y no merece la pena
    # bloquear a los demás lectores. Si dos peticiones compiten, se carga dos
    # veces y gana la última; es idempotente.
    try:
        artefacto = cargar_artefacto(ruta)
    except Exception as exc:
        raise RuntimeError('El modelo no está disponible.') from exc

    with _cache_lock:
        _cache['clave'], _cache['artefacto'] = clave, artefacto
    return artefacto


def invalidar_cache():
    """Fuerza la recarga en la siguiente predicción (la llama el reentrenamiento)."""
    with _cache_lock:
        _cache['clave'] = _cache['artefacto'] = None


def predecir_features(art, X):
    entrada = X.reindex(columns=art['columnas'], fill_value=0).copy()
    entrada[['dias_desde_inicio']] = art['scaler'].transform(entrada[['dias_desde_inicio']])
    return art['modelo'].predict(entrada)


def _validar_fecha(valor, campo='fecha'):
    if not isinstance(valor, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', valor):
        raise ValueError(campo + ' debe tener formato YYYY-MM-DD.')
    try:
        return pd.Timestamp(valor)
    except ValueError as exc:
        raise ValueError(campo + ' no es válida.') from exc


def predecir_ocupacion(fecha, tramo, model_path=None):
    """Entrada ISO YYYY-MM-DD y mañana/tarde; usa la versión activa del artefacto."""
    fecha = _validar_fecha(fecha)
    tramo = normalizar_tramo(tramo)
    art = obtener_artefacto(model_path)
    df = construir_features_df(pd.DataFrame({'fecha_cita': [fecha], 'tramo': [tramo]}))
    cierre = bool(df.iloc[0]['es_cierre'])
    valor = 0.0 if cierre else float(predecir_features(art, build_features(df)[0])[0])
    return {'prediccion_ocupacion': valor, 'version_modelo': art.get('version', 'original'),
            'entrenado_hasta': art['entrenado_hasta'], 'es_cierre': cierre}


def predecir_rango(fecha_inicio, fecha_fin, model_path=None):
    """
    Los dos tramos de cada día del rango, con una sola llamada al modelo.

    Devuelve una lista [{date, manana, tarde}] lista para el gráfico apilado.
    """
    inicio = _validar_fecha(fecha_inicio, 'startDate')
    fin = _validar_fecha(fecha_fin, 'endDate')
    if inicio > fin:
        raise ValueError('startDate debe ser anterior o igual a endDate.')
    dias = pd.date_range(inicio, fin, freq='D')
    if len(dias) > MAX_DIAS_RANGO:
        raise ValueError('El rango no puede superar {} días.'.format(MAX_DIAS_RANGO))

    # Rejilla intercalada [d0-mañana, d0-tarde, d1-mañana, ...]. Ese orden es el
    # invariante del que dependen tanto la máscara como el zip del return.
    rejilla = pd.DataFrame({'fecha_cita': dias.repeat(2), 'tramo': list(TRAMOS) * len(dias)})
    con_features = construir_features_df(rejilla)

    # La máscara sale de aquí y no de X: build_features() filtra los cierres y
    # reindexa, así que su índice ya no es alineable con la rejilla.
    abierto = (con_features['es_cierre'] != 1).to_numpy()
    valores = np.zeros(len(con_features), dtype=float)
    if abierto.any():
        # Sin esta guarda, un rango enteramente de cierre deja X vacío y el
        # StandardScaler revienta con "Found array with 0 sample(s)".
        X, _ = build_features(con_features)
        valores[abierto] = predecir_features(obtener_artefacto(model_path), X)
    valores = valores.clip(0.0).round(1)

    return [{'date': dia.strftime('%Y-%m-%d'), 'manana': float(manana), 'tarde': float(tarde)}
            for dia, manana, tarde in zip(dias, valores[0::2], valores[1::2])]
