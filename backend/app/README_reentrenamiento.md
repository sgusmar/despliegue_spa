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

**[Actualizado: la validación se relajó tras uso real — ver `evaluar_holdout`
y `_reentrenar` en `train_model.py` para el detalle exacto; lo de abajo queda
como contexto histórico de las dos primeras versiones.]**

Se exige que haya filas nuevas de verdad (más que cuando se entrenó el modelo
vigente); sin eso, 400. Con eso claro, los últimos `dias` días se reservan
para validación — pero esa ventana se adapta: si las filas nuevas extienden el
horizonte, se acorta a los días realmente posteriores al `entrenado_hasta`
vigente (mínimo 7); si rellenan un hueco histórico, no hay "días nuevos" al
final que aislar, así que se usa la ventana completa sobre el tramo final ya
conocido. El candidato y su scaler se ajustan únicamente con datos anteriores
al corte.

**El umbral de aceptación es relativo al modelo vigente, no fijo.** Se acepta
si el MAE del candidato no empeora claramente el del modelo vigente en esa
misma ventana (margen `MARGEN_TOLERANCIA_MAE`, 10%). El baseline semanal (t-7)
se sigue calculando y reportando, pero ya no forma parte del criterio de
aceptación: exigir batirlo además del modelo vigente rechazaba
reentrenamientos con datos reales válidos solo porque esa ventana concreta
favorecía a ese baseline ingenuo, no porque el candidato fuera peor que lo que
ya está en producción. Sin modelo anterior con el que comparar (primer
entrenamiento) se usa el techo histórico fijo `MAE_MAXIMO_ACEPTABLE` (2,46)
como única red de seguridad.

**El CSV subido se conserva aunque el candidato no se publique.** Son datos
reales; que no batan al modelo vigente en esta validación concreta no los
invalida como observaciones — se quedan en `data/` para el próximo intento.
Solo se retiran si ni siquiera se ha podido evaluar (p. ej. sin filas nuevas).

Después de aceptar, se reajusta con todo el histórico. Se guarda `validacion`
con método holdout_temporal, fechas, tamaños y las tres métricas; no se
denomina CV. El antiguo test incorporado al entrenamiento deja
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
