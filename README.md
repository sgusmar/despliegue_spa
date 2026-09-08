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
- [backend/README.md](backend/README.md): contrato de API que el frontend
  espera, CORS necesario, estructura sugerida. **Cualquier PR que añada el
  backend real debe respetar ese contrato** para que el acople no rompa el
  frontend.

## Cómo se acoplan

- El frontend nunca hardcodea la URL del backend: usa la variable de entorno
  `VITE_API_URL` (ver `frontend/.env.example`). Sin ella, funciona con datos
  simulados (`frontend/src/api/mock.ts`), así que se puede desarrollar y
  demostrar el front sin backend.
- En Render, cada carpeta es un servicio con su propio `rootDir`
  (`render.yaml` en la raíz), así que build y dependencias de uno no afectan
  al otro.
- El backend debe habilitar CORS para el origen del frontend (detalle en
  `backend/README.md`) — es el único ajuste imprescindible del lado backend
  para que el acople funcione en producción.

## Desarrollo local

```bash
cd frontend
npm install
npm run dev
```

Para apuntar el front a un backend real en local, copia
`frontend/.env.example` a `frontend/.env` y configura `VITE_API_URL` (p.ej.
`http://localhost:8000`).

## Despliegue en Render

Este repo usa un [Blueprint](https://render.com/docs/blueprint-spec) — al
conectar el repo en Render, `render.yaml` crea automáticamente los dos
servicios (`spa-occupancy-frontend` y `spa-occupancy-backend`). Tras el
primer deploy, configura `VITE_API_URL` en el servicio del frontend con la
URL pública que Render asigne al backend.
