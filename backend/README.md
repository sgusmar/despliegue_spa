# SPA Occupancy — Backend

Backend (Python) que sirve el modelo de Machine Learning de predicción de
ocupación del spa. Pensado para desplegarse en Render como Web Service.

Esta carpeta está pendiente de recibir el código real del backend (PR de
el equipo). Este README fija el **contrato de API** que el frontend
(`../frontend`) ya da por hecho — cualquier implementación debe respetarlo
para que el acople funcione sin tocar el frontend.

## Contrato de API

Base: la URL pública del servicio (se inyecta en el frontend vía
`VITE_API_URL`, sin barra final).

- `POST {VITE_API_URL}/predict/single`
  - body: `{ "date": "YYYY-MM-DD", "tramo": "manana" | "tarde" }`
  - respuesta `200`: `{ "date": string, "tramo": string, "citasPrevistas": number }`

- `POST {VITE_API_URL}/predict/range`
  - body: `{ "startDate": "YYYY-MM-DD", "endDate": "YYYY-MM-DD" }`
  - respuesta `200`:
    ```json
    {
      "current": [{ "date": "YYYY-MM-DD", "manana": 0, "tarde": 0 }],
      "previousYear": [{ "date": "YYYY-MM-DD", "manana": 0, "tarde": 0 }] | null
    }
    ```

- `POST {VITE_API_URL}/retrain`
  - Con archivo: `multipart/form-data`, campo `file` (CSV).
  - Con texto: JSON `{ "csvText": string }`.
  - CSV con cabecera exacta `fecha,tramo,citas` (`fecha`: `YYYY-MM-DD`,
    `tramo`: `manana`/`tarde`, `citas`: entero >= 0).
  - respuesta `200`: `{ "status": "ok" | "error", "rowsIngested": number, "message": string }`

- Errores: cualquier respuesta con status != 2xx se trata como error en el
  frontend; el body de texto/JSON se muestra tal cual si es posible, así que
  conviene devolver un mensaje legible (no solo un stack trace).

## CORS (imprescindible)

El frontend se sirve como Static Site en un dominio distinto al de este
backend, y hace `fetch` con `Content-Type: application/json` (dispara
preflight `OPTIONS`) y `multipart/form-data` para `/retrain`. El backend
**debe** habilitar CORS para el origen del frontend, por ejemplo con FastAPI:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",              # dev
        "https://spa-occupancy-frontend.onrender.com",  # ajustar a la URL real de Render
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

## Estructura esperada

Cualquier estructura vale siempre que `render.yaml` (raíz del repo) pueda
construir y arrancar el servicio con `rootDir: backend`. Como referencia para
FastAPI:

```
backend/
  main.py            # instancia FastAPI, incluye los routers
  requirements.txt
  ...
```

Al abrir el PR con el backend real, actualiza en `render.yaml` (raíz):
- `buildCommand` / `startCommand` si difieren de los de ejemplo.
- El nombre del servicio si cambia.

Y en el frontend, configura `VITE_API_URL` (dashboard de Render, o
`frontend/.env` en local) apuntando a la URL pública de este servicio.
