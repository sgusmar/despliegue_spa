# Ejemplos de uso — API Spa Oasis

Base local: `http://127.0.0.1:5000` · Base desplegada: `https://<tu-backend>.onrender.com`

## 1. Landing — `GET /`

`http://127.0.0.1:5000/`

```json
{
  "proyecto": "API de Predicción de Ocupación - Spa Oasis",
  "descripcion": "API REST para predecir la ocupación del spa y reentrenar el modelo",
  "endpoints": { "...": "..." }
}
```

## 2. Estado del servicio — `GET /health`

`http://127.0.0.1:5000/health`

```json
{
  "status": "ok",
  "model_loaded": true,
  "entrenado_hasta": "2026-01-24",
  "version_modelo": "original",
  "es_original": true
}
```

## 3. Predicción de un día — `GET /predict` *(endpoint principal)*

`http://127.0.0.1:5000/predict?fecha=2026-09-15&tramo=tarde`

```json
{
  "date": "2026-09-15",
  "tramo": "tarde",
  "citasPrevistas": 3.6,
  "es_cierre": false,
  "version_modelo": "original",
  "entrenado_hasta": "2026-01-24"
}
```

Día de cierre (Navidad): `http://127.0.0.1:5000/predict?fecha=2026-12-25&tramo=manana`

```json
{ "date": "2026-12-25", "tramo": "manana", "citasPrevistas": 0.0, "es_cierre": true, "version_modelo": "original", "entrenado_hasta": "2026-01-24" }
```

## 4. Predicción de un rango — `GET /predict/range`

`http://127.0.0.1:5000/predict/range?startDate=2026-09-08&endDate=2026-09-11`

```json
{
  "current": [
    { "date": "2026-09-08", "manana": 2.6, "tarde": 3.6 },
    { "date": "2026-09-09", "manana": 2.8, "tarde": 3.6 },
    { "date": "2026-09-10", "manana": 2.7, "tarde": 3.6 },
    { "date": "2026-09-11", "manana": 2.8, "tarde": 7.4 }
  ],
  "previousYear": [
    { "date": "2025-09-08", "manana": 1.0, "tarde": 0.0 },
    { "date": "2025-09-09", "manana": 3.0, "tarde": 3.0 },
    { "date": "2025-09-10", "manana": 1.0, "tarde": 4.0 },
    { "date": "2025-09-11", "manana": 2.0, "tarde": 4.0 }
  ]
}
```

## 5. Manejo de errores

`http://127.0.0.1:5000/predict?fecha=2026-09-15&tramo=noche`

```json
// HTTP 400
{ "error": "tramo debe ser 'manana' o 'tarde'." }
```

## 6. Estado del reentrenamiento — `GET /retrain`

`http://127.0.0.1:5000/retrain`

```json
{
  "endpoint": "/retrain",
  "datasets_detectados": ["ocupacion_tramos.csv"],
  "modelo_actual": {
    "disponible": true,
    "algoritmo": "RandomForest",
    "entrenado_hasta": "2026-01-24",
    "mae": 1.744,
    "version_modelo": "original",
    "reentrenado_el": "nunca (artefacto original)"
  }
}
```

## 7. Reentrenar con datos nuevos — `POST /retrain` *(extra voluntario)*

Subida de archivo (`file`) o JSON `{"csvText": "..."}` con `frontend/public/ejemplo_retrain.csv`.

```json
{
  "status": "ok",
  "rowsIngested": 14,
  "message": "Se han incorporado 14 filas y el modelo se ha reentrenado correctamente. MAE de validación 1.68 (baseline 2.43). Modelo entrenado hasta 2026-07-07."
}
```

## 8. Restaurar el modelo original — `POST /retrain/reset`

```json
{
  "status": "ok",
  "modelRestored": true,
  "filesRemoved": 1,
  "message": "Se ha restaurado el modelo original y se han eliminado 1 fichero(s) de datos subidos."
}
```

---

En el plan gratuito de Render, la primera petición tras inactividad tarda ~50s (arranque en frío) — conviene despertar el backend con `GET /health` antes de la demo.
