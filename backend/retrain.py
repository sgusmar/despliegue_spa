"""
Ingesta del CSV de reentrenamiento (extra voluntario del enunciado).

Este módulo no define rutas: el enrutado vive entero en `main.py`. Aquí está
solo la lógica de qué hacer con el CSV que llega — validarlo, añadirlo al
histórico de `data/` y lanzar el reentrenamiento de `train_model.py` — y la
traducción del informe técnico a la respuesta que espera el frontend.

Decisiones importantes:

* **El CSV subido se suma al histórico, no lo reemplaza.** Se guarda como un
  fichero más de `data/` con un nombre que ordena después del dataset base,
  porque `cargar_datasets()` deduplica con `keep="last"`: así una subida puede
  corregir cifras del histórico sin editar el fichero original a mano.
* **Si el modelo nuevo no se publica, el CSV se retira.** `data/` solo
  contiene datos que han producido un modelo aceptado, de modo que el
  histórico que se muestra en el gráfico y el que entrena el modelo son el
  mismo.
"""
import datetime as dt
import io
import os
import threading

import pandas as pd

import train_model
from model_service import obtener_artefacto
from train_model import ErrorDeReentrenamiento, ReentrenamientoEnCurso, reentrenar

# Un reentrenamiento a la vez: si llegan dos peticiones simultáneas, la segunda
# recibe un 409 en vez de pelearse con la primera por escribir el mismo fichero.
_candado = threading.Lock()


def info_modelo(model_path=None):
    """Estado del artefacto desplegado ahora mismo (para GET /retrain)."""
    try:
        art = obtener_artefacto(model_path)
    except RuntimeError as exc:
        return {'disponible': False, 'error': str(exc)}
    mae = art.get('validacion', {}).get('mae', art.get('mae_cv'))
    return {
        'disponible': True,
        'algoritmo': art.get('nombre'),
        'entrenado_hasta': art.get('entrenado_hasta'),
        # float() explícito: mae_cv viene del entrenamiento como np.float64 y
        # jsonify no sabe serializar escalares de numpy.
        'mae': None if mae is None else round(float(mae), 3),
        'version_modelo': art.get('version', 'original'),
        'reentrenado_el': art.get('reentrenado_el', 'nunca (artefacto original)'),
    }


def parsear_y_validar(csv_texto):
    """Texto CSV -> rejilla validada con las mismas reglas que los CSV de data/."""
    try:
        df = pd.read_csv(io.StringIO(csv_texto))
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeError) as exc:
        raise ErrorDeReentrenamiento('El CSV no se ha podido leer.') from exc
    if 'tramo' in df.columns:
        # Tolerante en la entrada (el frontend manda 'manana' sin ñ), canónico
        # en el disco. Un valor desconocido se deja intacto para que sea
        # validar_dataset quien dé el error, y no dos mensajes distintos.
        df['tramo'] = df['tramo'].astype(str).str.strip().str.lower().replace({'manana': 'mañana'})
    return train_model.validar_dataset(df, 'CSV recibido')


def _persistir(df, data_dir):
    """Guarda el CSV recibido en data/, de forma atómica y ordenable."""
    sello = dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    # El nombre tiene que ordenar DESPUÉS de ocupacion_tramos.csv: listar_datasets()
    # ordena alfabéticamente y cargar_datasets() deduplica con keep="last".
    destino = os.path.join(str(data_dir), 'subida_' + sello + '.csv')
    temporal = destino + '.tmp'  # .tmp para que listar_datasets() no lo vea a medio escribir
    # validar_dataset devuelve fecha_cita como datetime y n_citas como float; si
    # se volcaran así, la validación estricta de la siguiente lectura los
    # rechazaría ('2026-07-01 00:00:00' y '12.0').
    df.assign(
        fecha_cita=df['fecha_cita'].dt.strftime('%Y-%m-%d'),
        n_citas=df['n_citas'].astype(int),
    ).to_csv(temporal, index=False, encoding='utf-8')
    os.replace(temporal, destino)
    return destino


def ingerir_y_reentrenar(csv_texto, data_dir=None, dias_validacion=None):
    """Valida el CSV, lo añade al histórico y reentrena con todo lo que haya."""
    data_dir = data_dir or train_model.DATA_DIR
    df = parsear_y_validar(csv_texto)
    filas = int(len(df))

    if not _candado.acquire(blocking=False):
        raise ReentrenamientoEnCurso('Ya hay un reentrenamiento en curso. Espera a que termine.')
    try:
        destino = _persistir(df, data_dir)
        try:
            informe = reentrenar(
                data_dir=data_dir,
                dias_validacion=dias_validacion or train_model.DIAS_VALIDACION,
            )
        except Exception:
            os.unlink(destino)
            raise
        if informe['estado'] != 'reemplazado':
            os.unlink(destino)
    finally:
        _candado.release()

    return _a_respuesta(informe, filas)


def _a_respuesta(informe, filas):
    """Informe técnico del reentrenamiento -> {status, rowsIngested, message}."""
    if informe['estado'] == 'reemplazado':
        validacion = informe['validacion']
        return {
            'status': 'ok',
            'rowsIngested': filas,
            'message': (
                'Se han incorporado {} filas y el modelo se ha reentrenado correctamente. '
                'MAE de validación {:.2f} (baseline {:.2f}). Modelo entrenado hasta {}.'.format(
                    filas, validacion['mae'], validacion['mae_baseline'],
                    informe['entrenado_hasta'],
                )
            ),
        }
    return {
        'status': 'error',
        'rowsIngested': filas,
        'message': (
            'Se han recibido {} filas, pero el modelo NO se ha reemplazado: {} '
            'Los datos enviados se han descartado.'.format(filas, informe.get('motivo', ''))
        ),
    }
