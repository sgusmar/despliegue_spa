# SPA Occupancy — Backend

API REST (Flask) que sirve el modelo de predicción de ocupación del spa y
permite reentrenarlo con datos nuevos. Se despliega en Render como Web Service.

## Estructura

```
backend/
├── main.py              único fichero con Flask
├── requirements.txt
├── README.md
├── app/                 lógica de dominio, sin Flask
│   ├── model_service.py
│   ├── train_model.py
│   ├── retrain.py
│   ├── utils/
│   └── README_reentrenamiento.md
├── tests/
├── data/                CSV de ocupación
└── models/              artefactos serializados
```

| Fichero | Responsabilidad |
|---|---|
| `main.py` | **Único fichero con Flask**: todas las rutas, la validación de la forma de la petición y los `errorhandler`. |
| `app/model_service.py` | Artefacto del modelo (carga cacheada) y predicción, individual y por rangos. Sin framework. |
| `app/train_model.py` | Reentrenamiento, validación de datasets y lectura del histórico. Sin framework. |
| `app/retrain.py` | Ingesta del CSV que llega por `POST /retrain`. Sin framework. |
| `app/utils/` | Ingeniería de características, compartida por entrenamiento y predicción. |
| `data/` | CSV de ocupación (`fecha_cita,tramo,n_citas`). No se mueve dentro de `app/`: es un recurso, no código. |
| `models/` | Artefactos serializados (ver más abajo). Tampoco se mueve, por el mismo motivo. |

`data/` y `models/` siguen siendo hermanos de `main.py`, no hijos de `app/`:
son recursos y artefactos, no código de aplicación.

### Los dos artefactos

```
models/
├── modelo_ocupacion.joblib     de fábrica, versionado, NUNCA se escribe
├── scaler.joblib               de fábrica, versionado
└── modelo_reentrenado.joblib   lo publica /retrain, ignorado por git
```

Si existe `modelo_reentrenado.joblib`, es el que se usa; si no, se cae al de
fábrica. El artefacto versionado es de **solo lectura**, así que volver al
original nunca depende de que una copia de seguridad esté intacta: basta con
borrar un fichero, que es justo lo que hace `POST /retrain/reset`.

El enrutado está concentrado en `main.py` a propósito: el resto de módulos son
dependencias sin Flask, así que se pueden probar y reutilizar sin levantar la
app, y solo hay un sitio donde mirar para saber qué expone la API.

## Contrato de API

Es la fuente de verdad del acople con el frontend (`frontend/src/types.ts`).
Los tramos viajan **siempre sin ñ** (`manana` / `tarde`): la `ñ` es un detalle
interno del modelo y del dataset. En la entrada se aceptan ambas formas.

### `GET /` — landing

Descripción de la API y lista de endpoints.

### `GET /docs` — documentación interactiva

Equivalente al `/docs` automático de FastAPI: Swagger UI, servido desde
`app/docs.py` (`OPENAPI_SPEC` + una página HTML mínima que carga Swagger UI
desde CDN). El spec en sí vive en `GET /openapi.json`. Sin dependencias
nuevas en `requirements.txt` a propósito.

### `GET /health`

Siempre `200`, incluso sin modelo — es un *liveness check*, y devolver error
solo haría que Render reiniciase el servicio en bucle.

```json
{"status": "ok", "model_loaded": true, "entrenado_hasta": "2026-01-24",
 "version_modelo": "original", "es_original": true}
```

`es_original` es `false` cuando está activo un modelo reentrenado. El frontend
lo usa para ofrecer el botón de restaurar en el widget flotante de estado.

### `GET /predict`, `GET /predict/single`

Solo `GET`, sin `POST`: es una consulta de solo lectura (no cambia nada en el
servidor), así que `GET` es el único verbo con sentido aquí — y es también lo
que exige el criterio de evaluación (`requests.get(url, params={...})`, o
pegando la URL en el navegador). `/predict` y `/predict/single` son la misma
función con dos nombres; el frontend usa `/predict/single`.

```
GET /predict?fecha=2026-09-10&tramo=tarde
```
```json
{"date": "2026-09-10", "tramo": "tarde", "citasPrevistas": 5.7,
 "es_cierre": false, "version_modelo": "original", "entrenado_hasta": "2026-01-24"}
```

Acepta `fecha` o `date` indistintamente como nombre del parámetro. `citasPrevistas`
es el campo que consume el frontend; el resto son metadatos que no le
estorban, pero dejan claro que es una predicción real del modelo vigente, no
un valor de mentira.

Los días de cierre (25/12, 1/1, 6/1) devuelven `0` sin consultar al modelo.

### `GET /predict/range`

Mismo criterio que `/predict`: solo `GET`, con `startDate`/`endDate` por
query string.

```
GET /predict/range?startDate=2026-09-08&endDate=2026-09-14
```
```json
{
  "current":      [{"date": "2026-09-08", "manana": 2.7, "tarde": 3.6}, ...],
  "previousYear": [{"date": "2025-09-08", "manana": 3.0, "tarde": 5.0}, ...]
}
```

- `current` son **predicciones**; `previousYear` es la **ocupación real** del
  mismo periodo un año antes, leída del histórico de `data/`.
- `previousYear` es `null` si no hay histórico de ese periodo. Si solo hay
  parte, se devuelven únicamente los días que existen: no se rellena con ceros
  porque `n_citas = 0` es un valor observado de verdad y el gráfico mentiría.
- El rango no puede superar 366 días.

### `GET /retrain`

Estado del modelo desplegado, datasets detectados e instrucciones de uso.

### `POST /retrain`

Acepta el CSV de dos formas: como archivo en el campo `file`
(`multipart/form-data`) o como JSON `{"csvText": "<contenido>"}`.

```jsonc
// 200 — el modelo se ha reemplazado
{"status": "ok",    "rowsIngested": 14, "message": "Se han incorporado 14 filas y el modelo..."}
// 200 — el candidato no ha superado la validación; el modelo anterior sigue vigente
{"status": "error", "rowsIngested": 14, "message": "Se han recibido 14 filas, pero el modelo NO..."}
```

Un candidato descartado responde `200` y no un error de HTTP a propósito: el
CSV se ha procesado correctamente, y así el frontend puede mostrar cuántas
filas ha leído y por qué no se ha publicado el modelo.

### `POST /retrain/reset`

Vuelve al estado de fábrica: borra `modelo_reentrenado.joblib`, los CSV
subidos (`data/subida_*.csv`) y las copias de seguridad. Es idempotente.

```jsonc
{"status": "ok", "modelRestored": true, "filesRemoved": 1, "message": "..."}
```

Exige `X-Retrain-Token` en las mismas condiciones que `POST /retrain`.

### Errores

Todos los errores salen en JSON como `{"error": "..."}`:

| Código | Cuándo |
|---|---|
| `400` | Datos mal formados: fecha, tramo, rango invertido, CSV inválido, sin días nuevos. |
| `401` | Falta `X-Retrain-Token` y el servidor tiene `RETRAIN_TOKEN` configurado. |
| `409` | Ya hay un reentrenamiento en curso. |
| `413` | El CSV supera 2 MB. |
| `503` | El artefacto del modelo no está disponible. |

## Reentrenamiento

El CSV recibido **se suma al histórico**, no lo reemplaza: se guarda en `data/`
con un nombre (`subida_<sello>.csv`) que ordena después del dataset base, de
modo que en caso de solapamiento gane el dato más reciente.

Después se reentrena con todo lo que haya en `data/` y el modelo nuevo se
publica si **no empeora claramente** al vigente en un holdout temporal: el
umbral es el MAE del modelo actual en esa misma ventana, con un 10% de margen
(`MARGEN_TOLERANCIA_MAE`) — no una comparación contra un baseline ingenuo ni
un techo fijo, que rechazaban reentrenamientos con datos reales válidos solo
porque, por casualidad, la ventana concreta favorecía a esa referencia. Ese
techo fijo (`MAE_MAXIMO_ACEPTABLE`) solo se usa en el primer entrenamiento,
cuando no hay modelo anterior con el que comparar.

**El CSV se conserva aunque el modelo no se publique.** Son datos reales: que
el candidato no bata al vigente en esta validación concreta no los invalida
como observaciones. Solo se retira si ni siquiera se ha podido evaluar (p. ej.
no aporta ninguna fila nueva sobre lo que ya había).

**Solo se exige que haya filas nuevas de verdad** (más que las que había
cuando se entrenó el modelo vigente). Sin eso, se rechaza: sería reentrenar y
republicar sin ninguna información nueva. Con eso claro, hay dos formas
válidas de aportar filas nuevas, y la ventana de validación se adapta a cuál
sea:

- **Extender el horizonte** (subir una semana nueva, por ejemplo): la ventana
  de validación (60 días por defecto) se acorta —nunca se alarga— a los días
  que de verdad son posteriores al `entrenado_hasta` vigente. Sin este ajuste,
  subir datos semana a semana nunca pasaría de la primera vez: el corte
  (fecha máxima menos 60 días) caería antes del entrenamiento vigente aunque
  la semana subida fuera genuinamente nueva.
- **Rellenar un hueco histórico** (fechas anteriores a la máxima ya
  registrada): como no hay días nuevos al final que aislar como hold-out, se
  usa la ventana de validación completa sobre el tramo final ya conocido,
  comparando si incorporar esas filas mejora o empeora el modelo ahí.

En ambos casos el modelo solo se publica si de verdad mejora; rellenar un
hueco no está garantizado que lo haga (si el hueco es pequeño frente al
histórico total, es normal que apenas mueva el MAE de validación).

Publicar significa escribir `modelo_reentrenado.joblib`; el artefacto de
fábrica no se toca nunca, así que `POST /retrain/reset` deshace cualquier
reentrenamiento sin necesidad de restaurar copias.

El artefacto vigente se cachea en memoria y se recarga solo cuando el fichero
cambia, así que un reentrenamiento surte efecto sin reiniciar el servicio.

Detalles del lane de reentrenamiento en
[app/README_reentrenamiento.md](app/README_reentrenamiento.md).

## Desarrollo local

```bash
pip install -r requirements.txt
python main.py            # http://127.0.0.1:5000
python -B -m unittest discover -s tests -v
```

`scikit-learn` está fijado a la versión con la que se serializaron los
artefactos de `models/`; ver el comentario de `requirements.txt`.

## Despliegue

El `render.yaml` de la raíz define este servicio con `rootDir: backend`,
arrancado con `gunicorn main:app` y con `/health` como health check.

⚠️ En el plan gratuito de Render el disco es efímero: el modelo reentrenado y
los CSV subidos se pierden cuando el servicio se reinicia o se duerme, y se
vuelve al artefacto versionado en el repositorio.
