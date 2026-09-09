# Reentrenamiento e integración

La lógica vive en `train_model.py`, el Blueprint en `retrain.py` y el contrato
compartido de predicción en `model_service.py`.

## Cambios mínimos pendientes en main.py

```python
from retrain import retrain_bp
from model_service import predecir_ocupacion
app.register_blueprint(retrain_bp)  # después de crear app
```

En `/predict`, obtener fecha y tramo de los parámetros GET o del objeto JSON
POST. Llamar a `predecir_ocupacion(fecha, tramo)` y devolver su diccionario con
`jsonify`. Capturar ValueError como 400 y RuntimeError como 503. Validar primero
que el JSON es un objeto. Retirar la carga global y la transformación/predicción
anterior. Documentar las rutas en `/`.

Ejemplo: `/predict?fecha=2026-09-10&tramo=tarde`. La respuesta contiene
`prediccion_ocupacion`, `version_modelo`, `entrenado_hasta` y `es_cierre`.
Los cierres confirmados devuelven cero. La rama de predicción no se modifica aquí.

## Artefactos y activación

El cargador admite el formato original (diccionario y scaler separado).
Los nuevos artefactos incluyen modelo, scaler, columnas, versión y evaluación
en un único archivo. Se escribe un temporal y se publica con os.replace;
el anterior se respalda en models/backup. No se sobrescribe scaler.joblib:
los consumidores nuevos deben utilizar el scaler incluido en el artefacto.
Cada predicción carga la versión vigente y escala solo dias_desde_inicio.
Así no necesita reinicio. Medir latencia antes de introducir caché.

El bloqueo de fichero protege HTTP y llamadas directas entre procesos que
comparten el directorio de modelos. No coordina máquinas independientes.
Una terminación abrupta puede dejar models/.retrain.lock: eliminarlo manualmente
solo tras confirmar que no hay entrenamiento activo.

## Calidad

Los últimos 60 días se reservan para validación; deben ser posteriores al último
entrenamiento vigente. Sin suficientes días nuevos se devuelve 400 y se conserva
el modelo. El candidato y su scaler se ajustan únicamente con datos anteriores.
En las mismas filas se comparan candidato, modelo vigente y baseline que repite
la última semana disponible al corte, sin consumir observaciones de validación.
Si faltan datos de esa semana, se solicita corregir el dataset.

El candidato debe igualar o mejorar ambos MAE y cumplir el techo adicional
histórico de 2,46. Se compara sin redondear. Sin modelo anterior se aplican
baseline y techo. Después de aceptar, se reajusta con todo el histórico.
Se guarda `validacion` con método holdout_temporal, fechas, tamaños y las tres
métricas; no se denomina CV. El antiguo test incorporado al entrenamiento deja
de ser una evaluación independiente del nuevo modelo.

## Datos y API

Los CSV requieren filas y columnas fecha_cita,tramo,n_citas: fechas YYYY-MM-DD,
tramos mañana/tarde y conteos enteros finitos no negativos, sin nulos.
Se lee primero ocupacion_tramos.csv y después los demás en orden alfabético;
para fechas/tramos duplicados gana la última fila leída. Revisar las correcciones
y usar nombres ordenables. Nunca incorporar exportes con datos personales.

GET /retrain informa del estado. POST acepta cuerpo vacío o un objeto JSON con
dias_validacion entero >= 7. Rechaza JSON mal formado, listas, booleanos,
decimales y strings para ese parámetro. Configurar RETRAIN_TOKEN en el servicio
público y enviar X-Retrain-Token; sin variable la protección es opcional.

Respuestas: 200 reemplazado; 400 entrada inválida/datos insuficientes; 401 token;
409 candidato rechazado o entrenamiento ocupado; 500 fallo inesperado.

## Pruebas y demo

```bash
python -B -m unittest discover -s tests -v
python retrain.py
```

Las pruebas usan artefactos temporales y cubren publicación/recarga, rechazo por
calidad, datos nuevos insuficientes, fallo de publicación, bloqueo entre procesos,
validación, cierres y token. No sustituyen los modelos del proyecto.

Demostrar GET de predicción, incorporar otro CSV agregado, llamar a POST /retrain
y verificar la nueva versión en /predict. Repetir sin datos nuevos devuelve 400.
Guardar una copia del estado inicial para repetir la demo. Verificar la
persistencia del almacenamiento del alojamiento antes de presentar.

Dependencias: Flask, pandas, numpy, scikit-learn, joblib, holidays y, si se usa
para servir la aplicación, gunicorn. Fijar Python y las versiones en el
requirements común del equipo, comprobando compatibilidad con los artefactos.
