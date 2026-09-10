# SPA Occupancy

Documentación del frontend y el backend de la app de predicción de ocupación del spa, pensado para desplegarse en Render como dos servicios independientes a partir de este mismo repositorio (`render.yaml` en la raíz).

## Organización del repositorio

```
.
├── backend/            API REST (Flask) que sirve y reentrena el modelo de predicción
│   ├── app/               Lógica de dominio del modelo, sin Flask
│   │   └── utils/             Ingeniería de características para entrenamiento y predicción
│   ├── tests/              Tests de predicción y de reentrenamiento
│   ├── data/               CSV de ocupación usado para entrenar
│   └── models/             Artefactos del modelo serializados (.joblib)
├── frontend/           React + Vite + TypeScript que consume la API
│   ├── src/                Código fuente de la app
│   │   └── api/                Cliente de la API y datos simulados (mock)
│   └── public/             Archivos estáticos servidos tal cual (CSV de ejemplo, etc.)
├── utils/              Utilidades/scripts auxiliares a nivel de todo el repositorio
├── render.yaml         Blueprint de Render que define ambos servicios
├── .gitignore
└── README.md
```

* **`backend/main.py`**: el enrutado está concentrado aquí a propósito — todas las rutas, la validación de la forma de la petición y los `errorhandler`. El resto de módulos son dependencias sin Flask, así que se pueden probar y reutilizar sin levantar la app, y solo hay un sitio donde mirar para saber qué expone la API.
* **`backend/app/model_service.py`**: carga cacheada del artefacto del modelo y lógica de predicción (individual y por rangos), sin depender de Flask.
* **`backend/app/train_model.py`**: reentrenamiento, validación de datasets y lectura del histórico.
* **`backend/app/retrain.py`**: ingesta del CSV que llega por `POST /retrain`.
* **`backend/app/utils/`**: ingeniería de características, compartida entre entrenamiento y predicción.
* **`backend/app/README_reentrenamiento.md`**: detalle completo del lane de reentrenamiento (resumido más abajo).
* **`backend/data/`**: CSV de ocupación (`fecha_cita`, `tramo`, `n_citas`). No se mueve dentro de `app/` porque es un recurso, no código.
* **`backend/models/`**: artefactos serializados, hermanos de `main.py` por el mismo motivo que `data/`:
  * `modelo_ocupacion.joblib` — de fábrica, versionado en git, **nunca se escribe**.
  * `scaler.joblib` — de fábrica, versionado.
  * `modelo_reentrenado.joblib` — lo publica `POST /retrain`, ignorado por git.
  * `backup/` — copias del `modelo_reentrenado.joblib` anterior, guardadas justo antes de que un nuevo reentrenamiento lo sobrescriba. `POST /retrain/reset` también las borra al volver al estado de fábrica.

  Si existe `modelo_reentrenado.joblib`, es el que se usa; si no, se cae al de fábrica. El artefacto versionado es de solo lectura, así que volver al original nunca depende de que una copia de seguridad esté intacta: basta con borrarlo, que es justo lo que hace `POST /retrain/reset`.
* **`backend/tests/`**: tests de la lógica de predicción y del flujo de reentrenamiento.
* **`frontend/src/types.ts`**: tipos que modelan el contrato de API en el frontend.
* **`frontend/src/api/mock.ts`**: datos simulados que usa la app cuando `VITE_USE_MOCK=true`.
* **`utils/`** (raíz del repo): utilidades o scripts auxiliares a nivel de todo el proyecto — no confundir con `backend/app/utils/`, que es específico de la ingeniería de características del modelo.

## Cómo se acoplan

* El frontend llama siempre a rutas relativas `/api/*`, nunca a la URL del backend. En desarrollo lo resuelve el proxy de `frontend/vite.config.ts` y en producción la regla de reescritura del static site (`render.yaml`).
* `frontend/src/api/client.ts` llama a `/predict/single` y `/predict/range` como `GET`, con los parámetros por query string (sin cuerpo), en línea con el contrato del backend.
* Como el navegador ve un único origen, no hace falta CORS ni recompilar el frontend si cambia la URL del backend.
* Cada carpeta es un servicio de Render con su propio `rootDir`, así que el build y las dependencias de uno no afectan al otro.
* Los tramos viajan siempre sin ñ (`manana` / `tarde`) en el contrato de API; la ñ es un detalle interno del modelo y del dataset. En la entrada se aceptan ambas formas.

## Frontend

Páginas:

* **Inicio (`/`)**: explicación de la app y accesos a Predicción y Reentrenar.
* **Predicción (`/predict`)**:
  * Fecha única: fecha + tramo (mañana/tarde) → tabla con las citas previstas.
  * Rango de fechas: dos gráficos de barras apiladas (mañana + tarde) lado a lado — ocupación prevista del periodo elegido y ocupación real del mismo periodo del año anterior (si hay datos históricos).
* **Reentrenar (`/retrain`)**: descarga de un CSV de ejemplo, y envío de nuevos datos (texto pegado o archivo) validados contra ese mismo formato antes de enviarlos al backend.

**Formato de datos para reentrenar**, CSV con cabecera exacta `fecha_cita,tramo,n_citas`:

```
fecha_cita,tramo,n_citas
2026-07-01,manana,4
2026-07-01,tarde,7
```

* `fecha_cita`: `YYYY-MM-DD`
* `tramo`: `manana` o `tarde` (también se acepta `mañana`)
* `n_citas`: entero ≥ 0 (número de citas reales de ese tramo)

Es el mismo formato que consume el backend, así que el fichero se valida en el navegador antes de enviarlo. El archivo de ejemplo se sirve desde `public/ejemplo_retrain.csv` y es descargable desde la página de Reentrenar.

## Contrato de API (backend)

`backend/main.py` expone estos endpoints. Los tramos viajan siempre sin ñ (`manana`/`tarde`); en la entrada se aceptan ambas formas. La API acepta indistintamente las rutas con o sin barra final (`strict_slashes = False`), para tolerar tanto una URL escrita a mano como la que genere un script de evaluación.

### `GET /`
Landing: descripción de la API y lista de endpoints.

### `GET /health`
Liveness check. Siempre devuelve 200, incluso sin modelo cargado — es un liveness check, y devolver error solo haría que Render reiniciase el servicio en bucle.

```json
{"status": "ok", "model_loaded": true, "entrenado_hasta": "2026-01-24",
 "version_modelo": "original", "es_original": true}
```
`es_original` es `false` cuando está activo un modelo reentrenado. El frontend lo usa para ofrecer el botón de restaurar en el widget flotante de estado.

### `GET /predict` (alias `GET /predict/single`)
```
// entrada (query string)
?date=2026-09-10&tramo=manana
// salida
{"date": "2026-09-10", "tramo": "manana", "citasPrevistas": 2.7,
 "es_cierre": false, "version_modelo": "original", "entrenado_hasta": "2026-01-24"}
```
* Parámetros por query string, no por body: `date` (también acepta `fecha`) y `tramo`.
* Los días de cierre (25/12, 1/1, 6/1) devuelven `citasPrevistas: 0` sin consultar al modelo (`es_cierre: true`).
* `version_modelo` y `entrenado_hasta` no los usa el frontend, pero dejan explícito que la cifra viene de una predicción real del modelo vigente.
* Solo `GET`, sin `POST`: es una consulta de solo lectura, así que es el único verbo con sentido, y es también lo que exige el criterio de evaluación — sirve tanto `requests.get(url, params={...})` como pegar la URL directamente en el navegador.

### `GET /predict/range`
```
// entrada (query string)
?startDate=2026-09-08&endDate=2026-09-14
// salida
{
  "current":      [{"date": "2026-09-08", "manana": 2.7, "tarde": 3.6}, ...],
  "previousYear": [{"date": "2025-09-08", "manana": 3.0, "tarde": 5.0}, ...]
}
```
* `current` son predicciones; `previousYear` es la ocupación real del mismo periodo un año antes, leída del histórico de `data/`.
* `previousYear` es `null` si no hay histórico de ese periodo. Si solo hay parte, se devuelven únicamente los días que existen: no se rellena con ceros porque `n_citas = 0` es un valor observado de verdad y el gráfico mentiría.
* El rango no puede superar 366 días.

### `GET /retrain`
Estado del modelo desplegado, datasets detectados e instrucciones de uso.

### `POST /retrain`
Acepta el CSV de dos formas: como archivo en el campo `file` (`multipart/form-data`) o como JSON `{"csvText": "<contenido>"}`.

```json
// 200 — el modelo se ha reemplazado
{"status": "ok",    "rowsIngested": 14, "message": "Se han incorporado 14 filas y el modelo..."}
// 200 — el candidato no ha superado la validación; el modelo anterior sigue vigente
{"status": "error", "rowsIngested": 14, "message": "Se han recibido 14 filas, pero el modelo NO..."}
```
Un candidato descartado responde 200 y no un error de HTTP a propósito: el CSV se ha procesado correctamente, y así el frontend puede mostrar cuántas filas ha leído y por qué no se ha publicado el modelo.

### `POST /retrain/reset`
Vuelve al estado de fábrica: borra `modelo_reentrenado.joblib`, los CSV subidos (`data/subida_*.csv`) y las copias de seguridad. Es idempotente.

```json
{"status": "ok", "modelRestored": true, "filesRemoved": 1, "message": "..."}
```
Exige `X-Retrain-Token` en las mismas condiciones que `POST /retrain`.

### Errores
Todos los errores salen en JSON como `{"error": "..."}`:

| Código | Cuándo |
|---|---|
| 400 | Datos mal formados: fecha, tramo, rango invertido, CSV inválido, sin días nuevos. |
| 401 | Falta `X-Retrain-Token` y el servidor tiene `RETRAIN_TOKEN` configurado. |
| 405 | Método no permitido — `/predict` y `/predict/range` son solo `GET`. |
| 409 | Ya hay un reentrenamiento en curso. |
| 413 | El CSV supera 2 MB. |
| 503 | El artefacto del modelo no está disponible. |

### Reentrenamiento

El CSV recibido se suma al histórico, no lo reemplaza: se guarda en `data/` con un nombre (`subida_<sello>.csv`) que ordena después del dataset base, de modo que en caso de solapamiento gane el dato más reciente.

Después se reentrena con todo lo que haya en `data/` y el modelo nuevo se publica si no empeora claramente al vigente en un holdout temporal: el umbral es el MAE del modelo actual en esa misma ventana, con un 10% de margen (`MARGEN_TOLERANCIA_MAE`) — no una comparación contra un baseline ingenuo ni un techo fijo, que rechazaban reentrenamientos con datos reales válidos solo porque, por casualidad, la ventana concreta favorecía a esa referencia. Ese techo fijo (`MAE_MAXIMO_ACEPTABLE`) solo se usa en el primer entrenamiento, cuando no hay modelo anterior con el que comparar.

El CSV se conserva aunque el modelo no se publique. Son datos reales: que el candidato no bata al vigente en esta validación concreta no los invalida como observaciones. Solo se retira si ni siquiera se ha podido evaluar (p. ej. no aporta ninguna fila nueva sobre lo que ya había).

Solo se exige que haya filas nuevas de verdad (más que las que había cuando se entrenó el modelo vigente). Sin eso, se rechaza: sería reentrenar y republicar sin ninguna información nueva. Con eso claro, hay dos formas válidas de aportar filas nuevas, y la ventana de validación se adapta a cuál sea:

1. **Extender el horizonte** (subir una semana nueva, por ejemplo): la ventana de validación (60 días por defecto) se acorta —nunca se alarga— a los días que de verdad son posteriores al `entrenado_hasta` vigente. Sin este ajuste, subir datos semana a semana nunca pasaría de la primera vez: el corte (fecha máxima menos 60 días) caería antes del entrenamiento vigente aunque la semana subida fuera genuinamente nueva.
2. **Rellenar un hueco histórico** (fechas anteriores a la máxima ya registrada): como no hay días nuevos al final que aislar como hold-out, se usa la ventana de validación completa sobre el tramo final ya conocido, comparando si incorporar esas filas mejora o empeora el modelo ahí.

En ambos casos el modelo solo se publica si de verdad mejora; rellenar un hueco no está garantizado que lo haga (si el hueco es pequeño frente al histórico total, es normal que apenas mueva el MAE de validación).

Publicar significa escribir `modelo_reentrenado.joblib`; el artefacto de fábrica no se toca nunca, así que `POST /retrain/reset` deshace cualquier reentrenamiento sin necesidad de restaurar copias.

El artefacto vigente se cachea en memoria y se recarga solo cuando el fichero cambia, así que un reentrenamiento surte efecto sin reiniciar el servicio.

Detalles del lane de reentrenamiento en `backend/app/README_reentrenamiento.md`.

## Desarrollo local

Dos terminales:

```bash
cd backend && pip install -r requirements.txt && python main.py   # :5000
cd frontend && npm install && npm run dev                         # :5173
```

Para trabajar en el front sin backend, copia `frontend/.env.example` a `frontend/.env` y pon `VITE_USE_MOCK=true` (la app usa entonces datos simulados de `src/api/mock.ts`).

Para correr los tests del backend:
```bash
cd backend && python -B -m unittest discover -s tests -v
```

Build del frontend (genera el sitio estático en `frontend/dist/`):
```bash
cd frontend && npm run build
```

⚠️ `scikit-learn` está fijado a la versión con la que se serializaron los artefactos de `models/` (ver comentario en `backend/requirements.txt`).

## Despliegue en Render

Este repo usa un [Blueprint](https://render.com/docs/blueprint-spec) — al conectar el repo en Render, `render.yaml` crea los dos servicios:

* **`spa-occupancy-backend`**: Web Service con `rootDir: backend`, arrancado con `gunicorn main:app` y con `/health` como health check.
* **`spa-occupancy-frontend`**: Static Site con `rootDir: frontend` (`npm ci && npm run build`, publish path `./dist`), con dos reglas de reescritura en este orden: `/api/*` hacia el backend, y `/*` hacia `index.html` para el enrutado de React Router. Gracias a la primera regla, el navegador ve un único origen y no hace falta CORS ni hornear la URL del backend en el build.

⚠️ Tras el primer deploy hay que corregir en `render.yaml` el `destination` de la regla `/api/*` con la URL pública real que Render haya asignado al backend (añade un sufijo si el nombre ya estaba cogido) y volver a desplegar el static site. Después, comprobar que las peticiones atraviesan la reescritura (aquí con `/retrain`, que es estable; sirve cualquier endpoint):

```bash
curl -X POST https://<static-site>/api/retrain \
  -H 'Content-Type: application/json' -d '{"csvText":"fecha_cita,tramo,n_citas\n2026-07-01,manana,3"}'
```

⚠️ En el plan gratuito de Render el disco es efímero: el modelo reentrenado y los CSV subidos se pierden cuando el servicio se reinicia o se duerme, y se vuelve al artefacto versionado en el repositorio.