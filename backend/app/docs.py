"""
Documentación interactiva de la API (equivalente al /docs automático de
FastAPI, que Flask no trae de fábrica).

`OPENAPI_SPEC` es la especificación OpenAPI 3.0 a mano, y `DOCS_HTML` es una
página mínima que carga Swagger UI desde CDN y la apunta a `/openapi.json`.
Deliberadamente sin ninguna librería nueva en requirements.txt (nada de
flasgger/flask-smorest): es HTML estático + un dict de Python, y la
reproducibilidad del build es uno de los criterios de evaluación.
"""

_TRAMO_ENUM = ["manana", "mañana", "tarde"]

_ERROR_SCHEMA = {
    "type": "object",
    "properties": {"error": {"type": "string"}},
    "required": ["error"],
}


def _error_response(descripcion):
    return {
        "description": descripcion,
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
    }


OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "API de Predicción de Ocupación — Spa Oasis",
        "description": (
            "Predicción de ocupación del spa (por día/tramo o por rango de fechas) "
            "y reentrenamiento del modelo con datos nuevos."
        ),
        "version": "1.0.0",
    },
    "paths": {
        "/health": {
            "get": {
                "summary": "Estado del servicio y del modelo cargado",
                "responses": {
                    "200": {
                        "description": "Siempre 200, incluso sin modelo (liveness check).",
                        "content": {"application/json": {"schema": {
                            "type": "object",
                            "properties": {
                                "status": {"type": "string", "example": "ok"},
                                "model_loaded": {"type": "boolean"},
                                "entrenado_hasta": {"type": "string", "format": "date", "example": "2026-01-24"},
                                "version_modelo": {"type": "string", "example": "original"},
                                "es_original": {"type": "boolean"},
                            },
                        }}},
                    }
                },
            }
        },
        "/predict": {
            "get": {
                "summary": "Predicción de un día y tramo (endpoint principal)",
                "description": "Alias exacto de `GET /predict/single`.",
                "parameters": [
                    {"name": "fecha", "in": "query", "required": False, "schema": {"type": "string", "format": "date"},
                     "description": "YYYY-MM-DD. Alias: `date`."},
                    {"name": "date", "in": "query", "required": False, "schema": {"type": "string", "format": "date"},
                     "description": "Alias de `fecha`."},
                    {"name": "tramo", "in": "query", "required": True, "schema": {"type": "string", "enum": _TRAMO_ENUM}},
                ],
                "responses": {
                    "200": {
                        "description": "Predicción real del modelo vigente.",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PredictionResult"}}},
                    },
                    "400": _error_response("Falta `fecha`/`tramo`, o alguno tiene formato inválido."),
                    "503": _error_response("El artefacto del modelo no está disponible."),
                },
            }
        },
        "/predict/single": {
            "get": {
                "summary": "Predicción de un día y tramo",
                "description": "Misma función que `GET /predict`, es la que usa el frontend.",
                "parameters": [
                    {"name": "date", "in": "query", "required": True, "schema": {"type": "string", "format": "date"}},
                    {"name": "tramo", "in": "query", "required": True, "schema": {"type": "string", "enum": _TRAMO_ENUM}},
                ],
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PredictionResult"}}},
                    },
                    "400": _error_response("Falta `date`/`tramo`, o alguno tiene formato inválido."),
                    "503": _error_response("El artefacto del modelo no está disponible."),
                },
            }
        },
        "/predict/range": {
            "get": {
                "summary": "Predicción de un rango de fechas",
                "description": (
                    "`current` son predicciones; `previousYear` es la ocupación REAL del "
                    "mismo periodo un año antes (null si no hay histórico)."
                ),
                "parameters": [
                    {"name": "startDate", "in": "query", "required": True, "schema": {"type": "string", "format": "date"}},
                    {"name": "endDate", "in": "query", "required": True, "schema": {"type": "string", "format": "date"},
                     "description": "≥ startDate; rango máximo 366 días."},
                ],
                "responses": {
                    "200": {"description": "OK", "content": {"application/json": {"schema": {
                        "type": "object",
                        "properties": {
                            "current": {"type": "array", "items": {"$ref": "#/components/schemas/DayOccupancy"}},
                            "previousYear": {
                                "type": "array",
                                "items": {"$ref": "#/components/schemas/DayOccupancy"},
                                "nullable": True,
                                "description": "null si no hay histórico de ese periodo.",
                            },
                        },
                    }}}},
                    "400": _error_response("Falta `startDate`/`endDate`, rango invertido o mayor de 366 días."),
                    "503": _error_response("El artefacto del modelo no está disponible."),
                },
            }
        },
        "/retrain": {
            "get": {
                "summary": "Estado del modelo desplegado e instrucciones de reentrenamiento",
                "responses": {
                    "200": {"description": "OK", "content": {"application/json": {"schema": {"type": "object"}}}},
                },
            },
            "post": {
                "summary": "Reentrena el modelo con un CSV nuevo",
                "description": (
                    "Añade el CSV al histórico y reentrena. El modelo solo se publica si no "
                    "empeora claramente al vigente; el CSV se conserva aunque no se publique."
                ),
                "parameters": [
                    {"name": "X-Retrain-Token", "in": "header", "required": False, "schema": {"type": "string"},
                     "description": "Exigida solo si el servidor tiene RETRAIN_TOKEN configurado."},
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "properties": {"file": {"type": "string", "format": "binary"}},
                            }
                        },
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {"csvText": {
                                    "type": "string",
                                    "example": "fecha_cita,tramo,n_citas\n2026-07-01,manana,4\n2026-07-01,tarde,7\n",
                                }},
                                "required": ["csvText"],
                            }
                        },
                    },
                },
                "responses": {
                    "200": {
                        "description": "El CSV se ha procesado (publicado o descartado por calidad).",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/RetrainResult"}}},
                    },
                    "400": _error_response("CSV ausente/mal formado, columnas inválidas, o sin filas nuevas."),
                    "401": _error_response("Falta o no coincide X-Retrain-Token."),
                    "409": _error_response("Ya hay un reentrenamiento en curso."),
                    "413": _error_response("El CSV supera 2 MB."),
                },
            },
        },
        "/retrain/reset": {
            "post": {
                "summary": "Descarta el modelo reentrenado y los CSV subidos",
                "description": "Vuelve al artefacto de fábrica versionado en el repositorio. Idempotente.",
                "parameters": [
                    {"name": "X-Retrain-Token", "in": "header", "required": False, "schema": {"type": "string"}},
                ],
                "responses": {
                    "200": {"description": "OK", "content": {"application/json": {"schema": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string", "example": "ok"},
                            "modelRestored": {"type": "boolean"},
                            "filesRemoved": {"type": "integer"},
                            "message": {"type": "string"},
                        },
                    }}}},
                    "401": _error_response("Falta o no coincide X-Retrain-Token."),
                },
            }
        },
    },
    "components": {
        "schemas": {
            "Error": _ERROR_SCHEMA,
            "PredictionResult": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "format": "date"},
                    "tramo": {"type": "string", "enum": ["manana", "tarde"]},
                    "citasPrevistas": {"type": "number", "example": 3.6},
                    "es_cierre": {"type": "boolean"},
                    "version_modelo": {"type": "string"},
                    "entrenado_hasta": {"type": "string", "format": "date"},
                },
            },
            "DayOccupancy": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "format": "date"},
                    "manana": {"type": "number"},
                    "tarde": {"type": "number"},
                },
            },
            "RetrainResult": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["ok", "error"]},
                    "rowsIngested": {"type": "integer"},
                    "message": {"type": "string"},
                },
            },
        }
    },
}


DOCS_HTML = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>API Spa Oasis — Documentación</title>
  <link rel="icon" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/favicon-32x32.png">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui.css">
  <style>body { margin: 0; }</style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
  <script>
    window.onload = function () {
      // No se fija "/openapi.json" a secas: esta página se sirve tanto en
      // /docs (backend directo) como en /api/docs (a través del proxy del
      // frontend). Una ruta absoluta ignoraría el prefijo /api y el
      // navegador pediría el spec en la raíz del frontend, donde no existe
      // (cae en el index.html de la SPA). Se calcula relativa a esta misma
      // página, sea cual sea el prefijo por el que se haya entrado.
      var specUrl = window.location.pathname.replace(/\\/docs\\/?$/, "/openapi.json");
      window.ui = SwaggerUIBundle({
        url: specUrl,
        dom_id: "#swagger-ui",
        presets: [SwaggerUIBundle.presets.apis],
      });
    };
  </script>
</body>
</html>
"""
