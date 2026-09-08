"""Contrato compartido de artefactos y predicción; no depende de Flask."""
from pathlib import Path
import re

import joblib
import pandas as pd

from utils.feature_engineering import construir_features_df
from utils.preprocessing import build_features

MODEL_PATH = Path(__file__).resolve().parent / 'models' / 'modelo_ocupacion.joblib'


def cargar_artefacto(model_path=MODEL_PATH):
    """Carga una versión completa; admite el formato original separado."""
    path = Path(model_path)
    art = joblib.load(path)
    if not isinstance(art, dict) or not {'modelo', 'columnas', 'entrenado_hasta'} <= art.keys():
        raise ValueError('Formato de artefacto incompatible.')
    if 'scaler' not in art:
        art['scaler'] = joblib.load(path.with_name('scaler.joblib'))
    return art


def predecir_features(art, X):
    entrada = X.reindex(columns=art['columnas'], fill_value=0).copy()
    entrada[['dias_desde_inicio']] = art['scaler'].transform(entrada[['dias_desde_inicio']])
    return art['modelo'].predict(entrada)


def predecir_ocupacion(fecha, tramo):
    """Entrada ISO YYYY-MM-DD y mañana/tarde; carga la versión activa por petición."""
    if not isinstance(fecha, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', fecha):
        raise ValueError('fecha debe tener formato YYYY-MM-DD.')
    try:
        fecha = pd.Timestamp(fecha)
    except ValueError as exc:
        raise ValueError('fecha no es válida.') from exc
    if tramo not in ('mañana', 'tarde'):
        raise ValueError('tramo debe ser mañana o tarde.')
    try:
        art = cargar_artefacto()
    except Exception as exc:
        raise RuntimeError('El modelo no está disponible.') from exc
    df = construir_features_df(pd.DataFrame({'fecha_cita': [fecha], 'tramo': [tramo]}))
    cierre = bool(df.iloc[0]['es_cierre'])
    valor = 0.0 if cierre else float(predecir_features(art, build_features(df)[0])[0])
    return {'prediccion_ocupacion': valor, 'version_modelo': art.get('version', 'original'),
            'entrenado_hasta': art['entrenado_hasta'], 'es_cierre': cierre}
