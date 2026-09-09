# src/feature_engineering.py
"""
Funciones reutilizables para construir las variables de calendario y de
negocio a partir de una fecha (y, cuando aplica, un tramo horario).

Cada función es una transformación pura: solo depende de la fecha/tramo de
entrada y de constantes fijas (festivos, fechas comerciales, cierres) — nunca
de un histórico de reservas. Por eso `construir_features_df` sirve igual para
montar `train`/`test` sobre todo el histórico que para calcular el input de
una predicción futura. Usar siempre estas funciones en los dos sitios evita
que el cálculo de "cómo se entrenó" y el de "cómo se predice" diverjan con el
tiempo (training-serving skew).
"""
import pandas as pd
import holidays

# Fecha de referencia para dias_desde_inicio: el inicio del histórico de train.
# Es una constante fija, no se recalcula — en producción tiene que ser siempre
# la misma que se usó al entrenar el modelo.
FECHA_REFERENCIA = pd.Timestamp('2024-05-09')

# Calendario oficial de festivos de Andalucía — se expande automáticamente
# para cualquier año que se consulte, no hace falta fijar un rango de años.
FESTIVOS_ANDALUCIA = holidays.Spain(subdiv='AN')

# TODO: rellenar con las fechas oficiales publicadas en el BOJA para cada año
FESTIVOS_LOCALES_SEVILLA = set()

# Cierres recurrentes confirmados por el EDA (mismo día todos los años)
CIERRES_RECURRENTES = {(12, 25), (1, 1), (1, 6)}  # Navidad, Año Nuevo, Reyes

# Cierres puntuales confirmados por el negocio (rellenar a mano, como los
# festivos locales) — p. ej. los bloques 9-13/03/2025 y 17-19/11/2025 si el
# spa confirma que fueron cierres y no demanda cero real.
CIERRES_CONOCIDOS = set()

MESES_A_TEMPORADA = {
    12: 'invierno', 1: 'invierno', 2: 'invierno',
    3: 'primavera', 4: 'primavera', 5: 'primavera',
    6: 'verano', 7: 'verano', 8: 'verano',
    9: 'otoño', 10: 'otoño', 11: 'otoño',
}


def _grupo_dia(dia_semana):
    if dia_semana <= 3:
        return 'entre_semana'
    if dia_semana == 4:
        return 'viernes'
    return 'fin_de_semana'


def primer_domingo_mayo(anio):
    uno_mayo = pd.Timestamp(year=anio, month=5, day=1)
    return uno_mayo + pd.Timedelta(days=(6 - uno_mayo.weekday()) % 7)


def _es_festivo(fecha):
    return fecha in FESTIVOS_ANDALUCIA or fecha in FESTIVOS_LOCALES_SEVILLA


def _es_fecha_comercial(fecha):
    return (
        fecha == pd.Timestamp(year=fecha.year, month=2, day=14)  # San Valentín
        or fecha == primer_domingo_mayo(fecha.year)                # Día de la Madre
    )


def _es_cierre(fecha):
    if fecha in CIERRES_CONOCIDOS:
        return True
    return (fecha.month, fecha.day) in CIERRES_RECURRENTES


def anadir_variables_calendario(df):
    """dia_semana, nombre_dia, es_finde, mes, anio, semana_iso (transform.ipynb §8)."""
    df = df.copy()
    df['dia_semana'] = df['fecha_cita'].dt.dayofweek  # 0 = lunes
    df['nombre_dia'] = df['fecha_cita'].dt.day_name()
    df['es_finde'] = df['dia_semana'].isin([5, 6])
    df['mes'] = df['fecha_cita'].dt.month
    df['anio'] = df['fecha_cita'].dt.year
    df['semana_iso'] = df['fecha_cita'].dt.isocalendar().week.astype(int)
    return df


def anadir_tendencia(df, fecha_referencia=FECHA_REFERENCIA):
    """trimestre, dias_desde_inicio (feature_engineering.ipynb §1)."""
    df = df.copy()
    df['trimestre'] = df['fecha_cita'].dt.quarter
    df['dias_desde_inicio'] = (df['fecha_cita'] - fecha_referencia).dt.days
    return df


def anadir_variables_negocio(df):
    """grupo_dia, temporada (feature_engineering.ipynb §2)."""
    df = df.copy()
    df['grupo_dia'] = df['dia_semana'].apply(_grupo_dia)
    df['temporada'] = df['mes'].map(MESES_A_TEMPORADA)
    return df


def anadir_tramo_tarde(df):
    """tramo_tarde: versión numérica de tramo (feature_engineering.ipynb §3)."""
    df = df.copy()
    df['tramo_tarde'] = (df['tramo'] == 'tarde').astype(int)
    return df


def anadir_festivos(df):
    """es_festivo (feature_engineering.ipynb §4)."""
    df = df.copy()
    df['es_festivo'] = df['fecha_cita'].apply(_es_festivo)
    return df


def anadir_vispera_y_comercial(df):
    """es_vispera_festivo, es_fecha_comercial (feature_engineering.ipynb §5)."""
    df = df.copy()
    df['es_vispera_festivo'] = (df['fecha_cita'] + pd.Timedelta(days=1)).apply(_es_festivo)
    df['es_fecha_comercial'] = df['fecha_cita'].apply(_es_fecha_comercial)
    return df


def anadir_cierre(df):
    """es_cierre — marcador, no feature del modelo (feature_engineering.ipynb §6)."""
    df = df.copy()
    df['es_cierre'] = df['fecha_cita'].apply(_es_cierre)
    return df


def construir_features_df(df, fecha_referencia=FECHA_REFERENCIA):
    """
    Aplica de una sola vez TODAS las transformaciones anteriores (calendario +
    negocio) sobre un DataFrame con columnas 'fecha_cita' y 'tramo'.

    `src/transform.py` NO usa esta función para el histórico — ahí interesa
    mantener separados calendario (fase de Transformación) y negocio (fase de
    Feature Engineering, con variables que nacen de lo que mostró la EDA), tal
    como reflejan los dos notebooks. Esta versión combinada es para
    producción: dadas las fechas a predecir, construye de un tirón las filas
    completas que espera el modelo.
    """
    df = df.copy()
    df['fecha_cita'] = pd.to_datetime(df['fecha_cita'])
    df = anadir_variables_calendario(df)
    df = anadir_tendencia(df, fecha_referencia)
    df = anadir_variables_negocio(df)
    df = anadir_tramo_tarde(df)
    df = anadir_festivos(df)
    df = anadir_vispera_y_comercial(df)
    df = anadir_cierre(df)
    return df
