# SPA Occupancy

Monorepo con el frontend y el backend de la app de predicción de ocupación
del spa, pensado para desplegarse en Render como dos servicios independientes
a partir de este mismo repositorio (`render.yaml` en la raíz).

```
.
├── frontend/   React + Vite + TypeScript (Static Site)
├── backend/    Python — modelo de ML (Web Service)
└── render.yaml Blueprint de Render con ambos servicios
```

- [frontend/README.md](frontend/README.md): páginas, formato de datos,
  desarrollo local del front.
- [backend/README.md](backend/README.md): contrato de API, estructura y
  funcionamiento del reentrenamiento. Es la **fuente de verdad del contrato**
  que acopla los dos servicios.

## Cómo se acoplan

- El frontend llama siempre a rutas relativas `/api/*`, nunca a la URL del
  backend. En desarrollo lo resuelve el proxy de `frontend/vite.config.ts` y
  en producción la regla de reescritura del static site (`render.yaml`).
- Como el navegador ve un único origen, **no hace falta CORS** ni recompilar
  el frontend si cambia la URL del backend.
- Cada carpeta es un servicio de Render con su propio `rootDir`, así que el
  build y las dependencias de uno no afectan al otro.

## Desarrollo local

Dos terminales:

```bash
cd backend && pip install -r requirements.txt && python main.py   # :5000
cd frontend && npm install && npm run dev                         # :5173
```

Para trabajar en el front sin backend, copia `frontend/.env.example` a
`frontend/.env` y pon `VITE_USE_MOCK=true`.

## Despliegue en Render

Este repo usa un [Blueprint](https://render.com/docs/blueprint-spec) — al
conectar el repo en Render, `render.yaml` crea los dos servicios
(`spa-occupancy-frontend` y `spa-occupancy-backend`).

⚠️ Tras el primer deploy hay que **corregir en `render.yaml` el `destination`
de la regla `/api/*`** con la URL pública real que Render haya asignado al
backend (añade un sufijo si el nombre ya estaba cogido) y volver a desplegar
el static site. Después, comprobar que las peticiones POST atraviesan la
reescritura:

```bash
curl -X POST https://<static-site>/api/predict/single \
  -H 'Content-Type: application/json' -d '{"date":"2026-09-10","tramo":"manana"}'
```
