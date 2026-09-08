"""
Lógica de reentrenamiento del modelo de ocupación del spa.

Este módulo es la parte "D - reentrenamiento" del Team Challenge de despliegue.
No expone rutas HTTP: solo la función `reentrenar()`, que consume los CSV de
`data/` y deja un artefacto nuevo en `models/`. El endpoint que la llama vive
en `retrain.py` (Blueprint de Flask), para que la app principal (`main.py`) no
tenga que conocer nada de esto más allá de registrar el Blueprint.

Decisiones importantes:

* **Nunca se lee el export crudo del negocio** (`informe_NOUP.csv`). Ese
  fichero contiene datos personales de clientes reales (nombre, teléfono,
  email) y está excluido del repositorio por RGPD. El reentrenamiento parte
  siempre del agregado fecha x tramo, que no contiene ningún dato personal.
* **El contrato de columnas es fijo** (`COLUMNAS_MODELO`). El one-hot encoding
  de `build_features()` solo genera las categorías presentes en los datos, así
  que se reindexa siempre contra la lista canónica: así el modelo reentrenado
  sigue siendo compatible con el endpoint de predicción.
* **El modelo nuevo no sustituye al viejo si es peor.** Se evalúa contra un
  holdout temporal y solo se reemplaza el artefacto si el MAE está dentro del
  umbral aceptable. El anterior se guarda en `models/backup/`.
"""
from __future__ import annotations

import datetime as dt
import glob
import os
import shutil
import tempfile
import uuid
from contextlib import contextmanager

import numpy as np

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.preprocessing import StandardScaler

from utils.feature_engineering import construir_features_df
from utils.preprocessing import build_features
from model_service import cargar_artefacto, invalidar_cache, predecir_features

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODELS_DIR = os.path.join(BASE_DIR, "models")
BACKUP_DIR = os.path.join(MODELS_DIR, "backup")
# El artefacto de fábrica es de solo lectura: el reentrenamiento publica
# siempre en MODEL_ACTIVE_PATH, y model_service da prioridad a ese fichero si
# existe. Así restaurar el original es borrar un fichero, no recuperar una
# copia de seguridad y confiar en que esté intacta.
MODEL_BASE_PATH = os.path.join(MODELS_DIR, "modelo_ocupacion.joblib")
MODEL_ACTIVE_PATH = os.path.join(MODELS_DIR, "modelo_reentrenado.joblib")
SCALER_PATH = os.path.join(MODELS_DIR, "scaler.joblib")

# Dataset base del proyecto original. Cualquier CSV adicional que se añada a
# data/ se concatena por detrás y pisa a este en caso de solapamiento.
DATASET_BASE = "ocupacion_tramos.csv"

# Contrato de columnas del modelo: el mismo orden con el que se entrenó el
# artefacto original. Se mantiene fijo a propósito (ver docstring del módulo).
COLUMNAS_MODELO = [
    "dia_semana", "mes", "trimestre", "dias_desde_inicio", "tramo_tarde",
    "es_festivo", "es_vispera_festivo", "es_fecha_comercial",
    "grupo_dia_entre_semana", "grupo_dia_fin_de_semana", "grupo_dia_viernes",
    "temporada_invierno", "temporada_otoño", "temporada_primavera",
    "temporada_verano",
]

# Única columna escalada, igual que en el proyecto original.
COLUMNA_ESCALADA = "dias_desde_inicio"

COLUMNAS_REQUERIDAS = ["fecha_cita", "tramo", "n_citas"]

# Hiperparámetros ganadores de la RandomizedSearchCV del proyecto original.
# No se vuelve a buscar en cada reentrenamiento: sería lento y no es lo que
# pide el enunciado (reentrenar con datos nuevos, no rebuscar el modelo).
HIPERPARAMETROS = {
    "n_estimators": 200,
    "min_samples_leaf": 8,
    "max_features": 1.0,
    "max_depth": 6,
    "random_state": 42,
}

# Días finales de la serie que se reservan para validar el modelo nuevo.
DIAS_VALIDACION = 60

# Umbral de aceptación: el MAE del baseline estacional (t-7) medido contra test
# en el proyecto original. Si el modelo reentrenado no bate esto, algo va mal
# con los datos nuevos y no se despliega.
MAE_MAXIMO_ACEPTABLE = 2.46

# Mínimo de días posteriores al entrenamiento vigente para poder validar un
# reentrenamiento incremental (ver evaluar_holdout).
MIN_DIAS_NUEVOS = 7


class ErrorDeReentrenamiento(Exception):
    """Fallo controlado durante el reentrenamiento (datos inválidos, etc.)."""


class ReentrenamientoEnCurso(ErrorDeReentrenamiento):
    """Otro proceso tiene reservado el entrenamiento."""


@contextmanager
def reservar_entrenamiento():
    os.makedirs(MODELS_DIR, exist_ok=True)
    ruta = os.path.join(MODELS_DIR, '.retrain.lock')
    try:
        fd = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ReentrenamientoEnCurso('Ya hay un reentrenamiento en curso.') from exc
    try:
        os.close(fd)
        yield
    finally:
        os.unlink(ruta)


def listar_datasets(data_dir=DATA_DIR):
    """CSV disponibles en data/, con el dataset base siempre el primero."""
    rutas = sorted(glob.glob(os.path.join(data_dir, "*.csv")))
    base = os.path.join(data_dir, DATASET_BASE)
    if base in rutas:
        rutas.remove(base)
        rutas.insert(0, base)
    return rutas


def validar_dataset(df, nombre="dataset"):
    """
    Comprueba el contrato de columnas y devuelve la rejilla normalizada.

    La usan tanto la lectura de los CSV de data/ como la ingesta del CSV que
    llega por /retrain, para que un fichero subido se valide exactamente con
    las mismas reglas con las que se leerá después desde disco.
    """
    if df.empty:
        raise ErrorDeReentrenamiento(nombre + ': dataset vacío.')
    faltan = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltan:
        raise ErrorDeReentrenamiento(
            "{}: faltan las columnas {}. Se esperan al menos {}.".format(
                nombre, faltan, COLUMNAS_REQUERIDAS
            )
        )
    df = df[COLUMNAS_REQUERIDAS].copy()
    if not df['fecha_cita'].astype(str).str.fullmatch(r'\d{4}-\d{2}-\d{2}').all():
        raise ErrorDeReentrenamiento('fecha_cita debe tener formato YYYY-MM-DD.')
    df["fecha_cita"] = pd.to_datetime(df["fecha_cita"], format='%Y-%m-%d', errors="coerce")
    if df["fecha_cita"].isna().any():
        raise ErrorDeReentrenamiento(nombre + ": hay fechas que no se han podido leer.")
    if df['fecha_cita'].dt.tz is not None or (df['fecha_cita'] != df['fecha_cita'].dt.normalize()).any():
        raise ErrorDeReentrenamiento('Las fechas deben ser días sin hora ni zona horaria.')
    if not df['tramo'].isin(['mañana', 'tarde']).all():
        raise ErrorDeReentrenamiento('tramo debe ser mañana o tarde.')
    df['n_citas'] = pd.to_numeric(df['n_citas'], errors='coerce')
    if not (np.isfinite(df['n_citas']) & (df['n_citas'] >= 0) & (df['n_citas'] % 1 == 0)).all():
        raise ErrorDeReentrenamiento('n_citas debe contener enteros no negativos y finitos.')
    return df


def cargar_datasets(data_dir=DATA_DIR):
    """
    Concatena todos los CSV de data/ en una única rejilla fecha x tramo.

    Si dos ficheros traen la misma combinación (fecha, tramo), gana el último
    leído: así un export nuevo puede corregir cifras del histórico sin que haya
    que editar el fichero base a mano.
    """
    rutas = listar_datasets(data_dir)
    if not rutas:
        raise ErrorDeReentrenamiento(
            "No hay ningún CSV de entrenamiento en " + str(data_dir)
        )

    trozos, informe = [], []
    for ruta in rutas:
        nombre = os.path.basename(ruta)
        try:
            df = pd.read_csv(ruta)
        except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeError) as exc:
            raise ErrorDeReentrenamiento(nombre + ': CSV inválido.') from exc
        df = validar_dataset(df, nombre)
        trozos.append(df)
        informe.append({"fichero": nombre, "filas": int(len(df))})

    completo = pd.concat(trozos, ignore_index=True)
    completo = completo.drop_duplicates(subset=["fecha_cita", "tramo"], keep="last")
    completo = completo.sort_values(["fecha_cita", "tramo"]).reset_index(drop=True)
    return completo, informe


_historico = {'clave': None, 'df': None}


def _clave_datos(data_dir):
    """Huella de los CSV de data/, para saber si el histórico cacheado sigue vigente."""
    huella = []
    for ruta in listar_datasets(data_dir):
        estado = os.stat(ruta)
        huella.append((os.path.basename(ruta), estado.st_mtime_ns, estado.st_size))
    return tuple(huella)


def cargar_historico(data_dir=DATA_DIR):
    """
    Rejilla fecha x tramo real, ya validada y deduplicada, cacheada en memoria.

    Reutiliza cargar_datasets() a propósito: así el histórico que se muestra en
    el gráfico incluye automáticamente lo que se haya subido por /retrain, y no
    hay dos caminos distintos de leer los mismos datos.
    """
    clave = _clave_datos(data_dir)
    if _historico['clave'] != clave:
        df, _ = cargar_datasets(data_dir)
        _historico['clave'], _historico['df'] = clave, df
    return _historico['df']


def historico_por_rango(desde, hasta, data_dir=DATA_DIR):
    """Ocupación observada entre dos fechas, ambas incluidas (copia, no vista)."""
    df = cargar_historico(data_dir)
    return df[(df['fecha_cita'] >= desde) & (df['fecha_cita'] <= hasta)]


def preparar_xy(df):
    """
    Rejilla fecha x tramo -> (X con el contrato de columnas, y, fechas).

    Devuelve también la serie de fechas alineada con X para poder hacer el
    corte temporal del holdout después de haber filtrado los días de cierre.
    """
    con_features = construir_features_df(df)
    X, y = build_features(con_features)

    # build_features() ya ha descartado los días de cierre; hay que quedarse con
    # las mismas filas del DataFrame de fechas para que los índices cuadren.
    fechas = con_features.loc[con_features["es_cierre"] != 1, "fecha_cita"]
    fechas = fechas.reset_index(drop=True)

    # El one-hot solo crea las categorías presentes: se reindexa contra el
    # contrato canónico para no romper la compatibilidad con /predict.
    X = X.reindex(columns=COLUMNAS_MODELO, fill_value=0)
    return X, y, fechas


def ajustar(X, y):
    """Ajusta scaler + RandomForest sobre los datos que se le pasen."""
    scaler = StandardScaler().fit(X[[COLUMNA_ESCALADA]])
    X_escalado = X.copy()
    X_escalado[[COLUMNA_ESCALADA]] = scaler.transform(X[[COLUMNA_ESCALADA]])

    modelo = RandomForestRegressor(**HIPERPARAMETROS)
    modelo.fit(X_escalado, y)
    return modelo, scaler


def evaluar_holdout(X, y, fechas, dias=DIAS_VALIDACION, actual=None):
    """
    MAE honesto del pipeline con los datos actuales: se entrena con todo menos
    los últimos `dias` días y se mide contra ellos. Corte temporal, nunca
    aleatorio — es una serie temporal.

    Si hay un modelo anterior, la ventana se acorta (nunca se alarga) a los
    días que de verdad son posteriores a su `entrenado_hasta`. Sin este ajuste,
    un reentrenamiento incremental (p. ej. subir una semana de datos) nunca
    pasaría la validación por defecto de 60 días: el corte (fecha_máxima menos
    60) caería antes del entrenamiento vigente aunque esos 7 días sean
    genuinamente nuevos. Con el ajuste, el hold-out son exactamente esos días
    nuevos — ni más (no existen) ni menos (así se validan todos).
    """
    fecha_max = fechas.max()

    if actual is not None:
        entrenado_hasta = pd.Timestamp(actual['entrenado_hasta'])
        dias_nuevos = (fecha_max - entrenado_hasta).days
        if dias_nuevos < MIN_DIAS_NUEVOS:
            raise ErrorDeReentrenamiento(
                'Solo hay {} día(s) posteriores al entrenamiento vigente ({}). '
                'Hacen falta al menos {} días nuevos para poder validar el modelo: '
                'los datos que subes deben tener fecha posterior a la última fecha '
                'ya entrenada, no anterior ni ya cubierta.'.format(
                    max(dias_nuevos, 0), actual['entrenado_hasta'], MIN_DIAS_NUEVOS,
                )
            )
        dias = min(dias, dias_nuevos)

    corte = fecha_max - pd.Timedelta(days=dias)
    es_train = fechas <= corte

    if es_train.sum() == 0 or (~es_train).sum() == 0:
        raise ErrorDeReentrenamiento(
            "No hay suficiente histórico para reservar {} días de validación.".format(dias)
        )

    modelo, scaler = ajustar(X[es_train], y[es_train])
    X_val = X[~es_train].copy()
    X_val[[COLUMNA_ESCALADA]] = scaler.transform(X_val[[COLUMNA_ESCALADA]])
    mae = float(mean_absolute_error(y[~es_train], modelo.predict(X_val)))

    # Baseline semanal con observaciones disponibles estrictamente antes del corte.
    # Repite la última semana para respetar el mismo horizonte que el candidato.
    semana = pd.DataFrame({'fecha': fechas, 'tramo': X['tramo_tarde'], 'y': y})
    historia = semana[es_train].set_index(['fecha', 'tramo'])['y']
    pred_base = []
    for fila in semana[~es_train].itertuples():
        ref = fila.fecha
        while ref > corte:
            ref -= pd.Timedelta(days=7)
        pred_base.append(historia.get((ref, fila.tramo), float('nan')))
    if not np.isfinite(pred_base).all():
        raise ErrorDeReentrenamiento('Faltan observaciones en la semana de referencia del baseline.')

    return {
        "metodo": "holdout_temporal",
        "mae": mae,
        "mae_baseline": float(mean_absolute_error(y[~es_train], pred_base)),
        "mae_modelo_actual": None if actual is None else float(mean_absolute_error(
            y[~es_train], predecir_features(actual, X[~es_train]))),
        "dias": dias,
        "desde": str(fechas[~es_train].min().date()),
        "hasta": str(fechas[~es_train].max().date()),
        "filas_validacion": int((~es_train).sum()),
        "filas_entrenamiento": int(es_train.sum()),
    }


def _guardar_copia_de_seguridad():
    """
    Aparta el modelo reentrenado anterior antes de sobrescribirlo.

    El artefacto de fábrica no se copia porque nunca se toca: si no ha habido
    ningún reentrenamiento previo, no hay nada que salvar.
    """
    if not os.path.exists(MODEL_ACTIVE_PATH):
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    sello = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destino = os.path.join(BACKUP_DIR, "modelo_reentrenado_" + sello + ".joblib")
    shutil.copy2(MODEL_ACTIVE_PATH, destino)
    try:
        return os.path.relpath(destino, BASE_DIR).replace(os.sep, "/")
    except ValueError:
        # En Windows relpath revienta si destino y BASE_DIR están en unidades
        # distintas (pasa en los tests, con el tmp en C: y el repo en D:).
        return destino.replace(os.sep, "/")


def reentrenar(data_dir=DATA_DIR, dias_validacion=DIAS_VALIDACION):
    if type(dias_validacion) is not int or dias_validacion < 7:
        raise ErrorDeReentrenamiento('dias_validacion debe ser un entero de al menos 7.')
    with reservar_entrenamiento():
        return _reentrenar(data_dir, dias_validacion)


def _reentrenar(data_dir, dias_validacion):
    """
    Reentrena el modelo con todo lo que haya en data/ y, si pasa la validación,
    reemplaza el artefacto desplegado.

    Devuelve un informe serializable a JSON con lo que ha pasado — es la
    respuesta del endpoint /retrain.
    """
    df, fuentes = cargar_datasets(data_dir)
    X, y, fechas = preparar_xy(df)

    # Mismo criterio que model_service.ruta_modelo_vigente(), pero con las
    # constantes de este módulo, que son las que los tests redirigen a un
    # directorio temporal.
    vigente = MODEL_ACTIVE_PATH if os.path.exists(MODEL_ACTIVE_PATH) else MODEL_BASE_PATH
    actual = cargar_artefacto(vigente) if os.path.exists(vigente) else None
    validacion = evaluar_holdout(X, y, fechas, dias_validacion, actual)
    mae_anterior = validacion['mae_modelo_actual']
    umbral = min(MAE_MAXIMO_ACEPTABLE, validacion['mae_baseline'],
                 mae_anterior if mae_anterior is not None else float('inf'))

    informe = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "datasets": fuentes,
        "filas_totales": int(len(df)),
        "filas_entrenamiento": int(len(X)),
        "rango_fechas": {
            "desde": str(fechas.min().date()),
            "hasta": str(fechas.max().date()),
        },
        "validacion": validacion,
        "mae_maximo_aceptable": umbral,
        "mae_modelo_anterior": mae_anterior,
    }

    if validacion["mae"] > umbral:
        informe["estado"] = "descartado"
        informe["motivo"] = (
            "MAE de validación {} peor que el umbral {}. "
            "Se mantiene el modelo anterior.".format(
                validacion["mae"], umbral
            )
        )
        return informe

    # El modelo que se despliega se reajusta con TODO el histórico, incluidos
    # los días de validación: el MAE reportado viene del holdout de arriba, que
    # es una estimación honesta del error de este pipeline con estos datos.
    modelo, scaler = ajustar(X, y)

    artefacto = {
        "modelo": modelo,
        "nombre": "RandomForest",
        "columnas": COLUMNAS_MODELO,
        "scaler": scaler,
        "version": uuid.uuid4().hex,
        "validacion": validacion,
        "entrenado_hasta": str(fechas.max().date()),
        "mejores_params": {
            k: v for k, v in HIPERPARAMETROS.items() if k != "random_state"
        },
        "reentrenado_el": informe["timestamp"],
    }

    copia = _guardar_copia_de_seguridad()
    os.makedirs(MODELS_DIR, exist_ok=True)
    fd, temporal = tempfile.mkstemp(prefix='.modelo_', suffix='.joblib', dir=MODELS_DIR)
    os.close(fd)
    try:
        joblib.dump(artefacto, temporal)
        cargar_artefacto(temporal)
        os.replace(temporal, MODEL_ACTIVE_PATH)
        # El mtime del fichero ya bastaría, pero invalidar explícitamente cubre
        # también el uso por CLI (python train_model.py) dentro del mismo proceso.
        invalidar_cache()
    finally:
        if os.path.exists(temporal):
            os.unlink(temporal)

    informe["estado"] = "reemplazado"
    informe["copia_de_seguridad"] = copia
    informe["entrenado_hasta"] = artefacto["entrenado_hasta"]
    informe['version_modelo'] = artefacto['version']
    return informe


if __name__ == "__main__":
    import json

    print(json.dumps(reentrenar(), indent=2, ensure_ascii=False))
