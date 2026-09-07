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

CSV con cabecera exacta `fecha,tramo,citas`:

```csv
fecha,tramo,citas
2024-01-08,manana,12
2024-01-08,tarde,17
```

- `fecha`: `YYYY-MM-DD`
- `tramo`: `manana` o `tarde`
- `citas`: entero >= 0 (número de citas reales de ese tramo)

El archivo de ejemplo se sirve desde `public/ejemplo_retrain.csv` y es
descargable desde la propia página de Reentrenar.

## Contrato de API esperado (backend)

Mientras no exista backend real, la app funciona con datos simulados
(`src/api/mock.ts`). Al configurar `VITE_API_URL`, se usan estos endpoints:

- `POST {VITE_API_URL}/predict/single`
  - body: `{ "date": "YYYY-MM-DD", "tramo": "manana" | "tarde" }`
  - respuesta: `{ "date": string, "tramo": string, "citasPrevistas": number }`

- `POST {VITE_API_URL}/predict/range`
  - body: `{ "startDate": "YYYY-MM-DD", "endDate": "YYYY-MM-DD" }`
  - respuesta:
    ```json
    {
      "current": [{ "date": "YYYY-MM-DD", "manana": 0, "tarde": 0 }],
      "previousYear": [{ "date": "YYYY-MM-DD", "manana": 0, "tarde": 0 }] | null
    }
    ```

- `POST {VITE_API_URL}/retrain`
  - Con archivo: `multipart/form-data`, campo `file`.
  - Con texto: JSON `{ "csvText": string }`.
  - respuesta: `{ "status": "ok" | "error", "rowsIngested": number, "message": string }`

## Desarrollo local

```bash
npm install
npm run dev
```

Por defecto, sin `VITE_API_URL` configurada, la app usa datos simulados
(`src/api/mock.ts`) para poder navegar y probar toda la funcionalidad sin
backend.

Para apuntar a un backend real, copia `.env.example` a `.env` y configura
`VITE_API_URL` con la URL base de la API.

## Build y despliegue en Render

```bash
npm run build
```

Genera el sitio estático en `dist/`. El repo incluye `render.yaml` con la
configuración de un Static Site en Render (`npm ci && npm run build`,
publish path `./dist`, y reescritura de rutas a `index.html` para que
funcione el enrutado de React Router). Configura la variable de entorno
`VITE_API_URL` en el dashboard de Render apuntando al backend cuando esté
disponible.
