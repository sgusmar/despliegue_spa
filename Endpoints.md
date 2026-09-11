# Referencia de endpoints — API Spa Oasis

Base local: `http://127.0.0.1:5000` · Base desplegada: `https://<tu-backend>.onrender.com`

Todas las respuestas son JSON. Todas las rutas aceptan indistintamente con o
sin barra final (`/health` y `/health/` son lo mismo).

| Método | Ruta | Qué hace |
|---|---|---|
| GET | [`/`](#get-) | Landing: descripción de la API y lista de endpoints |
| GET | [`/health`](#get-health) | Estado del servicio y del modelo cargado |
| GET | [`/predict`](#get-predict-alias-get-predictsingle) | Predicción de un día y tramo *(endpoint principal)* |
| GET | [`/predict/single`](#get-predict-alias-get-predictsingle) | Alias exacto de `/predict` |
| GET | [`/predict/range`](#get-predictrange) | Predicción de un rango de fechas |
| GET | [`/retrain`](#get-retrain) | Estado del modelo desplegado e instrucciones |
| POST | [`/retrain`](#post-retrain) | Reentrena el modelo con un CSV nuevo |
| POST | [`/retrain/reset`](#post-retrainreset) | Descarta el modelo reentrenado, vuelve al de fábrica |

---

## `GET /`

Sin parámetros.

**200**
```json
{
  "proyecto": "API de Predicción de Ocupación - Spa Oasis",
  "descripcion": "API REST para predecir la ocupación del spa y reentrenar el modelo",
  "endpoints": { "GET /health": "...", "...": "..." }
}
```

---

## `GET /health`

Sin parámetros. **Siempre 200**, incluso sin modelo cargado (es un *liveness
check*: Render no debe reiniciar el servicio solo porque falte el artefacto).

| Campo | Tipo | Descripción |
|---|---|---|
| `status` | string | Siempre `"ok"` |
| `model_loaded` | bool | Si hay un artefacto cargado |
| `entrenado_hasta` | string \| — | Fecha `YYYY-MM-DD` hasta la que está entrenado (solo si `model_loaded`) |
| `version_modelo` | string \| — | `"original"` o el hash de la versión reentrenada |
| `es_original` | bool \| — | `false` si hay un modelo reentrenado activo |

**200**
```json
{ "status": "ok", "model_loaded": true, "entrenado_hasta": "2026-01-24",
  "version_modelo": "original", "es_original": true }
```

---

## `GET /predict` (alias: `GET /predict/single`)

Predicción de un día y tramo. Endpoint principal a efectos de evaluación.

**Query params**

| Parámetro | Obligatorio | Formato |
|---|---|---|
| `fecha` (o `date`) | Sí | `YYYY-MM-DD` |
| `tramo` | Sí | `manana`, `mañana` o `tarde` |

**200**
```json
{ "date": "2026-09-15", "tramo": "tarde", "citasPrevistas": 3.6,
  "es_cierre": false, "version_modelo": "original", "entrenado_hasta": "2026-01-24" }
```

Un día de cierre (25/12, 1/1, 6/1) devuelve `citasPrevistas: 0` sin consultar
al modelo.

**Errores**

| Código | Causa |
|---|---|
| 400 | Falta `fecha`/`date` o `tramo` |
| 400 | `fecha` con formato inválido, o `tramo` fuera de `{manana, mañana, tarde}` |
| 503 | El artefacto del modelo no está disponible |

---

## `GET /predict/range`

Predicción de un rango de fechas: ocupación prevista (`current`) y ocupación
**real** del mismo periodo un año antes (`previousYear`), leída del histórico.

**Query params**

| Parámetro | Obligatorio | Formato |
|---|---|---|
| `startDate` | Sí | `YYYY-MM-DD` |
| `endDate` | Sí | `YYYY-MM-DD`, ≥ `startDate`, rango máximo 366 días |

**200**
```json
{
  "current":      [{ "date": "2026-09-08", "manana": 2.6, "tarde": 3.6 }],
  "previousYear": [{ "date": "2025-09-08", "manana": 1.0, "tarde": 0.0 }]
}
```

- `previousYear` es `null` si no hay histórico de ese periodo. Si solo hay
  parte, devuelve únicamente los días que existen (nunca rellena con ceros).
- `previousYear` se desplaza con `DateOffset(years=1)`, no 365 días, para
  caer en el mismo día de la semana.

**Errores**

| Código | Causa |
|---|---|
| 400 | Falta `startDate` o `endDate` |
| 400 | `startDate` posterior a `endDate`, o rango > 366 días |
| 503 | El artefacto del modelo no está disponible |

---

## `GET /retrain`

Estado del modelo desplegado e instrucciones de uso. Sin parámetros.

**200**
```json
{
  "endpoint": "/retrain",
  "como_usarlo": {
    "metodo": "POST",
    "cuerpo": "archivo 'file' (multipart) o JSON {'csvText': '...'}",
    "columnas": ["fecha_cita", "tramo", "n_citas"],
    "cabecera": "X-Retrain-Token si el servidor tiene RETRAIN_TOKEN configurado"
  },
  "datasets_detectados": ["ocupacion_tramos.csv"],
  "modelo_actual": {
    "disponible": true, "algoritmo": "RandomForest",
    "entrenado_hasta": "2026-01-24", "mae": 1.744,
    "version_modelo": "original", "reentrenado_el": "nunca (artefacto original)"
  },
  "aviso": "En el plan gratuito de Render el disco es efímero..."
}
```

---

## `POST /retrain`

Añade un CSV al histórico y reentrena. El modelo nuevo solo se publica si no
empeora claramente al vigente; el CSV se conserva siempre que sea válido,
aunque el modelo no se publique.

**Cuerpo** — una de las dos formas:

| Forma | Content-Type | Campo |
|---|---|---|
| Archivo | `multipart/form-data` | `file` |
| Texto | `application/json` | `csvText` (contenido completo del CSV, con cabecera) |

**Columnas exigidas del CSV:** `fecha_cita` (`YYYY-MM-DD`), `tramo` (`manana`/`mañana`/`tarde`), `n_citas` (entero ≥ 0).

**Cabecera opcional:** `X-Retrain-Token`, exigida solo si el servidor tiene `RETRAIN_TOKEN` configurado.

**200 — modelo publicado**
```json
{ "status": "ok", "rowsIngested": 6,
  "message": "Se han incorporado 6 filas y el modelo se ha reentrenado correctamente. MAE de validación 1.66 (baseline 2.64). Modelo entrenado hasta 2026-07-03." }
```

**200 — modelo descartado** (candidato peor que el vigente; los datos se conservan igualmente)
```json
{ "status": "error", "rowsIngested": 6,
  "message": "Se han recibido 6 filas, pero el modelo NO se ha reemplazado: MAE de validación ... empeora claramente al del modelo vigente ..." }
```

**Errores**

| Código | Causa |
|---|---|
| 400 | Sin CSV, CSV mal formado, columnas/valores inválidos, o sin filas nuevas respecto al último entrenamiento |
| 401 | Falta o no coincide `X-Retrain-Token` (solo si `RETRAIN_TOKEN` está configurado) |
| 409 | Ya hay un reentrenamiento en curso |
| 413 | El CSV supera 2 MB |

---

## `POST /retrain/reset`

Descarta el modelo reentrenado y los CSV subidos; vuelve al artefacto de
fábrica versionado en el repositorio. Sin cuerpo. Idempotente. Misma cabecera
`X-Retrain-Token` que `POST /retrain` si aplica.

**200**
```json
{ "status": "ok", "modelRestored": true, "filesRemoved": 1,
  "message": "Se ha restaurado el modelo original y se han eliminado 1 fichero(s) de datos subidos." }
```

Si no había nada que restaurar: `modelRestored: false`, `filesRemoved: 0`.

---

## Errores comunes a toda la API

Todos los errores devuelven `{"error": "<mensaje>"}` — nunca HTML ni un 500 críptico.

| Código | Significado |
|---|---|
| 400 | Petición mal formada (dato obligatorio ausente o con formato inválido) |
| 401 | Token de reentrenamiento ausente o incorrecto |
| 404 | Ruta inexistente |
| 405 | Método no permitido en esa ruta (p. ej. `POST /predict/single`, que solo acepta `GET`) |
| 409 | Conflicto (reentrenamiento ya en curso) |
| 413 | Cuerpo de la petición demasiado grande |
| 500 | Error inesperado del servidor |
| 503 | El modelo no está disponible |
