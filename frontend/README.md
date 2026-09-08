# SPA Occupancy — Frontend

Frontend (React + Vite + TypeScript) para mostrar el modelo de Machine Learning
de predicción de ocupación del spa. Pensado para desplegarse en Render como
Static Site.

## Páginas

- **Inicio (`/`)**: explicación de la app y accesos a Predicción y Reentrenar.
- **Predicción (`/predict`)**:
  - *Fecha única*: fecha + tramo (mañana/tarde) → tabla con las citas previstas.
  - *Rango de fechas*: dos gráficos de barras apiladas (mañana + tarde) lado a
    lado — ocupación prevista del periodo elegido y ocupación real del mismo
    periodo del año anterior (si hay datos históricos).
- **Reentrenar (`/retrain`)**: descarga de un CSV de ejemplo, y envío de nuevos
  datos (texto pegado o archivo) validados contra ese mismo formato antes de
  enviarlos al backend.

## Formato de datos para reentrenar

CSV con cabecera exacta `fecha_cita,tramo,n_citas`:

```csv
fecha_cita,tramo,n_citas
2026-07-01,manana,4
2026-07-01,tarde,7
```

- `fecha_cita`: `YYYY-MM-DD`
- `tramo`: `manana` o `tarde` (también se acepta `mañana`)
- `n_citas`: entero >= 0 (número de citas reales de ese tramo)

Es el mismo formato que consume el backend, así que el fichero se valida en el
navegador antes de enviarlo. El archivo de ejemplo se sirve desde
`public/ejemplo_retrain.csv` y es descargable desde la página de Reentrenar.

## Contrato de API

Los endpoints (`/predict/single`, `/predict/range`, `/retrain`) están
documentados en [../backend/README.md](../backend/README.md), que es la fuente
de verdad del contrato. Los tipos que los modelan viven en `src/types.ts`.

## Desarrollo local

```bash
npm install
npm run dev
```

El frontend llama siempre a `/api/*`, y el proxy de `vite.config.ts` lo
redirige al backend en `http://127.0.0.1:5000`. Para trabajar con la app
completa, levanta el backend en otra terminal:

```bash
cd ../backend
pip install -r requirements.txt
python main.py
```

Para trabajar en el frontend **sin backend levantado**, copia `.env.example` a
`.env` y pon `VITE_USE_MOCK=true`: la app usa entonces datos simulados
(`src/api/mock.ts`).

## Build y despliegue en Render

```bash
npm run build
```

Genera el sitio estático en `dist/`. El `render.yaml` de la raíz del repo
define este servicio como Static Site con `rootDir: frontend`
(`npm ci && npm run build`, publish path `./dist`) y dos reglas de reescritura,
**en este orden**: `/api/*` hacia el backend y `/*` hacia `index.html` para el
enrutado de React Router. Gracias a la primera, el navegador ve un único
origen y no hace falta CORS ni hornear la URL del backend en el build.
