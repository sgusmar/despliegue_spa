import io
import multiprocessing
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import pandas as pd

import main
from app import model_service as servicio
from app import retrain
from app import train_model as t

CSV_NUEVO = 'fecha_cita,tramo,n_citas\n2026-07-01,manana,3\n2026-07-01,tarde,5\n'
INFORME_OK = {'estado': 'reemplazado', 'entrenado_hasta': '2026-07-01',
              'validacion': {'mae': 1.2, 'mae_baseline': 2.4}}


def intentar_reserva(directorio, cola):
    t.MODELS_DIR = directorio
    try:
        with t.reservar_entrenamiento():
            cola.put('permitido')
    except t.ReentrenamientoEnCurso:
        cola.put('bloqueado')


class ReentrenamientoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # De fábrica (nunca se escribe) y el que publica el reentrenamiento.
        self.base = self.root / 'modelo_ocupacion.joblib'
        self.activo = self.root / 'modelo_reentrenado.joblib'
        # Explícitamente MODEL_BASE_PATH (el de fábrica), no el "vigente": si
        # quedara un modelo_reentrenado.joblib real de una sesión anterior (p.
        # ej. un `python main.py` que alguien se dejó corriendo), el "vigente"
        # sería ese, no el original, y contaminaría todos los tests de esta
        # clase en silencio — es justo lo que pasó al escribir este test.
        self.original = servicio.cargar_artefacto(servicio.MODEL_BASE_PATH)
        joblib.dump(self.original, self.base)
        self.paths = patch.multiple(t, MODELS_DIR=str(self.root),
                                    MODEL_BASE_PATH=str(self.base),
                                    MODEL_ACTIVE_PATH=str(self.activo),
                                    BACKUP_DIR=str(self.root / 'backup'),
                                    SCALER_PATH=str(self.root / 'scaler.joblib'))
        self.paths.start()
        self.addCleanup(self.paths.stop)

    def test_publicacion_recarga_y_rechazo_sin_datos_nuevos(self):
        de_fabrica = self.base.read_bytes()
        informe = t.reentrenar()
        self.assertEqual(informe['estado'], 'reemplazado')
        art = servicio.cargar_artefacto(self.activo)
        self.assertIn('scaler', art)
        self.assertEqual(art['version'], informe['version_modelo'])
        pred = servicio.predecir_ocupacion('2026-09-10', 'tarde', model_path=self.activo)
        self.assertEqual(pred['version_modelo'], art['version'])
        self.assertGreaterEqual(pred['prediccion_ocupacion'], 0)
        self.assertEqual(servicio.predecir_ocupacion(
            '2026-12-25', 'mañana', model_path=self.activo)['prediccion_ocupacion'], 0)
        # El artefacto de fábrica no se toca nunca, ni siquiera al publicar.
        self.assertEqual(self.base.read_bytes(), de_fabrica)
        contenido = self.activo.read_bytes()
        with self.assertRaises(t.ErrorDeReentrenamiento):
            t.reentrenar()
        self.assertEqual(self.activo.read_bytes(), contenido)
        self.assertEqual(self.base.read_bytes(), de_fabrica)

    def test_candidato_peor_no_publica_nada(self):
        de_fabrica = self.base.read_bytes()
        with patch.object(t, 'evaluar_holdout', return_value={
            'mae': 2., 'mae_baseline': 3., 'mae_modelo_actual': 1.}):
            self.assertEqual(t.reentrenar()['estado'], 'descartado')
        self.assertFalse(self.activo.exists())
        self.assertEqual(self.base.read_bytes(), de_fabrica)

    def test_fallo_publicacion_conserva_artefacto(self):
        de_fabrica = self.base.read_bytes()
        with patch.object(t.os, 'replace', side_effect=OSError('fallo simulado')):
            with self.assertRaises(OSError):
                t.reentrenar()
        self.assertEqual(self.base.read_bytes(), de_fabrica)
        self.assertFalse(self.activo.exists())
        self.assertFalse(list(self.root.glob('.modelo_*')))
        self.assertFalse((self.root / '.retrain.lock').exists())

    def test_el_reentrenado_manda_sobre_el_de_fabrica(self):
        with patch.multiple(servicio, MODEL_BASE_PATH=self.base, MODEL_ACTIVE_PATH=self.activo):
            self.assertEqual(servicio.ruta_modelo_vigente(), self.base)
            joblib.dump(self.original, self.activo)
            self.assertEqual(servicio.ruta_modelo_vigente(), self.activo)
            self.activo.unlink()
            self.assertEqual(servicio.ruta_modelo_vigente(), self.base)

    def test_restaurar_original_descarta_lo_reentrenado(self):
        cliente = main.create_app(data_dir=self.root).test_client()
        # Estado tras un reentrenamiento: modelo publicado y CSV subido.
        joblib.dump(dict(self.original, version='abc'), self.activo)
        (self.root / 'subida_20260101_000000_000000.csv').write_text(CSV_NUEVO, encoding='utf-8')

        cuerpo = cliente.post('/retrain/reset').get_json()
        self.assertEqual(cuerpo['status'], 'ok')
        self.assertTrue(cuerpo['modelRestored'])
        self.assertEqual(cuerpo['filesRemoved'], 1)
        self.assertFalse(self.activo.exists())
        self.assertFalse(list(self.root.glob('subida_*.csv')))
        self.assertTrue(self.base.exists())

        # Repetirlo no rompe nada y lo dice.
        repetido = cliente.post('/retrain/reset').get_json()
        self.assertFalse(repetido['modelRestored'])
        self.assertEqual(repetido['filesRemoved'], 0)

    def test_exclusion_entre_procesos(self):
        ctx = multiprocessing.get_context('spawn')
        cola = ctx.Queue()
        with t.reservar_entrenamiento():
            proceso = ctx.Process(target=intentar_reserva, args=(str(self.root), cola))
            proceso.start()
            try:
                self.assertEqual(cola.get(timeout=20), 'bloqueado')
            finally:
                proceso.join(timeout=20)
                if proceso.is_alive():
                    proceso.terminate()
                    proceso.join()
                cola.close()

    def test_datos_invalidos(self):
        for cambio in [{'tramo': 'noche'}, {'n_citas': -1}, {'n_citas': 1.5},
                       {'n_citas': None}, {'n_citas': float('inf')}, {'fecha_cita': 'incorrecta'}]:
            with self.subTest(cambio=cambio):
                fila = {'fecha_cita': '2026-07-01', 'tramo': 'mañana', 'n_citas': 2}
                fila.update(cambio)
                pd.DataFrame([fila]).to_csv(self.root / 'datos.csv', index=False)
                with self.assertRaises(t.ErrorDeReentrenamiento):
                    t.cargar_datasets(self.root)

    def test_ventana_de_validacion_se_adapta_a_los_dias_nuevos(self):
        """
        Regresión: con la ventana fija de 60 días, un reentrenamiento
        incremental de solo unos pocos días nuevos (p. ej. subir una semana)
        se rechazaba SIEMPRE con "no hay suficientes días nuevos", aunque esos
        días fueran genuinamente posteriores al entrenamiento vigente. La
        ventana debe acortarse a los días realmente nuevos, nunca alargarse.
        """
        df, _ = t.cargar_datasets()
        X, y, fechas = t.preparar_xy(df)
        fecha_max = fechas.max()

        # 10 días nuevos: por debajo del mínimo de 7 no debería pasar, por
        # encima sí, y el hold-out debe medir exactamente esos 10 días, no 60.
        # evaluar_holdout también usa 'actual' para el MAE del modelo vigente
        # (predecir_features), así que hace falta un artefacto completo, no
        # solo la fecha: se parte de self.original y se le pisa esa clave.
        actual = dict(self.original, entrenado_hasta=str((fecha_max - pd.Timedelta(days=10)).date()))
        validacion = t.evaluar_holdout(X, y, fechas, dias=t.DIAS_VALIDACION, actual=actual)
        self.assertEqual(validacion['dias'], 10)
        self.assertEqual(validacion['hasta'], str(fecha_max.date()))

        # Una ventana grande disponible (mucho más que los 60 pedidos) no debe
        # verse recortada: sigue siendo la ya validada por el resto de tests.
        actual_lejano = dict(self.original, entrenado_hasta='2024-06-01')
        validacion_normal = t.evaluar_holdout(X, y, fechas, dias=t.DIAS_VALIDACION, actual=actual_lejano)
        self.assertEqual(validacion_normal['dias'], t.DIAS_VALIDACION)

    def test_sin_filas_nuevas_se_rechaza(self):
        """Resubir exactamente los mismos datos no debe reentrenar ni republicar nada."""
        df, _ = t.cargar_datasets()
        X, y, fechas = t.preparar_xy(df)
        actual = dict(self.original, entrenado_hasta=str(fechas.max().date()),
                      filas_disponibles=len(fechas))
        with self.assertRaises(t.ErrorDeReentrenamiento) as ctx:
            t.evaluar_holdout(X, y, fechas, dias=t.DIAS_VALIDACION, actual=actual)
        self.assertIn('no han cambiado', str(ctx.exception))

    def test_relleno_de_hueco_historico_se_acepta_con_la_ventana_completa(self):
        """
        Regresión: subir datos con fecha ANTERIOR a la máxima ya registrada
        (rellenar un hueco histórico) se rechazaba siempre con "no hay
        suficientes días nuevos", aunque esas filas fueran genuinamente nuevas
        (nunca habían estado en el dataset) — porque el horizonte no avanzaba.
        Si hay más filas que la última vez, debe aceptarse igualmente,
        validando con la ventana completa sobre el tramo final ya conocido.
        """
        df, _ = t.cargar_datasets()
        X, y, fechas = t.preparar_xy(df)
        fecha_max = fechas.max()
        # El modelo anterior se entrenó con MENOS filas pero llegando a LA
        # MISMA fecha máxima: exactamente "se ha rellenado un hueco", no "se
        # ha extendido el horizonte".
        actual = dict(self.original, entrenado_hasta=str(fecha_max.date()),
                      filas_disponibles=len(fechas) - 14)
        validacion = t.evaluar_holdout(X, y, fechas, dias=t.DIAS_VALIDACION, actual=actual)
        # dias_nuevos = 0 -> no se acorta la ventana (no hay a qué acortarla),
        # pero tampoco se rechaza: se usa la ventana completa solicitada.
        self.assertEqual(validacion['dias'], t.DIAS_VALIDACION)
        self.assertEqual(validacion['hasta'], str(fecha_max.date()))

    def test_cache_del_artefacto_se_reutiliza_y_se_invalida(self):
        primero = servicio.obtener_artefacto(self.base)
        self.assertIs(servicio.obtener_artefacto(self.base), primero)
        # utime en vez de reescribir: así no depende de la resolución del reloj.
        marca = os.stat(self.base).st_mtime_ns + 2_000_000_000
        os.utime(self.base, ns=(marca, marca))
        self.assertIsNot(servicio.obtener_artefacto(self.base), primero)

    def test_http_invalido_y_token(self):
        cliente = main.create_app(data_dir=self.root, model_path=self.base).test_client()
        with patch.dict('os.environ', {'RETRAIN_TOKEN': ''}), patch.object(retrain, 'reentrenar') as entrenar:
            self.assertEqual(cliente.post('/retrain').status_code, 400)            # sin cuerpo
            self.assertEqual(cliente.post('/retrain', json={}).status_code, 400)   # sin csvText
            self.assertEqual(cliente.post('/retrain', json=[1]).status_code, 400)
            self.assertEqual(cliente.post('/retrain', data='{', content_type='application/json').status_code, 400)
            self.assertEqual(cliente.post('/retrain', json={'csvText': 'basura'}).status_code, 400)
            entrenar.assert_not_called()
            entrenar.return_value = INFORME_OK
            respuesta = cliente.post('/retrain', json={'csvText': CSV_NUEVO})
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.get_json()['status'], 'ok')
            self.assertEqual(respuesta.get_json()['rowsIngested'], 2)
        with patch.dict('os.environ', {'RETRAIN_TOKEN': 'prueba'}), patch.object(retrain, 'reentrenar') as entrenar:
            self.assertEqual(cliente.post('/retrain', json={'csvText': CSV_NUEVO}).status_code, 401)
            entrenar.assert_not_called()

    def test_csv_subido_queda_legible_para_el_siguiente_reentrenamiento(self):
        """
        validar_dataset devuelve fecha_cita como datetime y n_citas como float.
        Si se volcaran tal cual, la validación estricta de la lectura siguiente
        los rechazaría y el retrain se rompería en la petición posterior.
        """
        cliente = main.create_app(data_dir=self.root, model_path=self.base).test_client()
        with patch.object(retrain, 'reentrenar', return_value=INFORME_OK):
            self.assertEqual(cliente.post('/retrain', json={'csvText': CSV_NUEVO}).status_code, 200)
        subidos = list(self.root.glob('subida_*.csv'))
        self.assertEqual(len(subidos), 1)
        self.assertEqual(subidos[0].read_text(encoding='utf-8').splitlines()[:2],
                         ['fecha_cita,tramo,n_citas', '2026-07-01,mañana,3'])
        self.assertEqual(len(t.cargar_datasets(self.root)[0]), 2)

    def test_retrain_retira_el_csv_si_el_modelo_se_descarta(self):
        cliente = main.create_app(data_dir=self.root, model_path=self.base).test_client()
        with patch.object(retrain, 'reentrenar', return_value={
                'estado': 'descartado', 'motivo': 'MAE peor que el umbral.'}):
            respuesta = cliente.post('/retrain', json={'csvText': CSV_NUEVO})
        # 200 y no 409: si no, el cliente lanzaría y el usuario no vería el motivo.
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json()['status'], 'error')
        self.assertEqual(respuesta.get_json()['rowsIngested'], 2)
        self.assertFalse(list(self.root.glob('subida_*.csv')))

    def test_retrain_acepta_el_csv_como_archivo(self):
        cliente = main.create_app(data_dir=self.root, model_path=self.base).test_client()
        with patch.object(retrain, 'reentrenar', return_value=INFORME_OK):
            # Con BOM, que es como lo exporta Excel.
            datos = {'file': (io.BytesIO(CSV_NUEVO.encode('utf-8-sig')), 'ocupacion.csv')}
            respuesta = cliente.post('/retrain', data=datos, content_type='multipart/form-data')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json()['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
