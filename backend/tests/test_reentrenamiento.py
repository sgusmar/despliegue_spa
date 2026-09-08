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
import model_service as servicio
import retrain
import train_model as t

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
        self.model = self.root / 'modelo_ocupacion.joblib'
        self.original = servicio.cargar_artefacto()
        joblib.dump(self.original, self.model)
        self.paths = patch.multiple(t, MODELS_DIR=str(self.root), MODEL_PATH=str(self.model),
                                    BACKUP_DIR=str(self.root / 'backup'),
                                    SCALER_PATH=str(self.root / 'scaler.joblib'))
        self.paths.start()
        self.addCleanup(self.paths.stop)

    def test_publicacion_recarga_y_rechazo_sin_datos_nuevos(self):
        informe = t.reentrenar()
        self.assertEqual(informe['estado'], 'reemplazado')
        art = servicio.cargar_artefacto(self.model)
        self.assertIn('scaler', art)
        self.assertEqual(art['version'], informe['version_modelo'])
        pred = servicio.predecir_ocupacion('2026-09-10', 'tarde', model_path=self.model)
        self.assertEqual(pred['version_modelo'], art['version'])
        self.assertGreaterEqual(pred['prediccion_ocupacion'], 0)
        self.assertEqual(servicio.predecir_ocupacion(
            '2026-12-25', 'mañana', model_path=self.model)['prediccion_ocupacion'], 0)
        contenido = self.model.read_bytes()
        with self.assertRaises(t.ErrorDeReentrenamiento):
            t.reentrenar()
        self.assertEqual(self.model.read_bytes(), contenido)

    def test_candidato_peor_conserva_artefacto(self):
        contenido = self.model.read_bytes()
        with patch.object(t, 'evaluar_holdout', return_value={
            'mae': 2., 'mae_baseline': 3., 'mae_modelo_actual': 1.}):
            self.assertEqual(t.reentrenar()['estado'], 'descartado')
        self.assertEqual(self.model.read_bytes(), contenido)

    def test_fallo_publicacion_conserva_artefacto(self):
        contenido = self.model.read_bytes()
        with patch.object(t.os, 'replace', side_effect=OSError('fallo simulado')):
            with self.assertRaises(OSError):
                t.reentrenar()
        self.assertEqual(self.model.read_bytes(), contenido)
        self.assertFalse(list(self.root.glob('.modelo_*')))
        self.assertFalse((self.root / '.retrain.lock').exists())

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

    def test_cache_del_artefacto_se_reutiliza_y_se_invalida(self):
        primero = servicio.obtener_artefacto(self.model)
        self.assertIs(servicio.obtener_artefacto(self.model), primero)
        # utime en vez de reescribir: así no depende de la resolución del reloj.
        marca = os.stat(self.model).st_mtime_ns + 2_000_000_000
        os.utime(self.model, ns=(marca, marca))
        self.assertIsNot(servicio.obtener_artefacto(self.model), primero)

    def test_http_invalido_y_token(self):
        cliente = main.create_app(data_dir=self.root, model_path=self.model).test_client()
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
        cliente = main.create_app(data_dir=self.root, model_path=self.model).test_client()
        with patch.object(retrain, 'reentrenar', return_value=INFORME_OK):
            self.assertEqual(cliente.post('/retrain', json={'csvText': CSV_NUEVO}).status_code, 200)
        subidos = list(self.root.glob('subida_*.csv'))
        self.assertEqual(len(subidos), 1)
        self.assertEqual(subidos[0].read_text(encoding='utf-8').splitlines()[:2],
                         ['fecha_cita,tramo,n_citas', '2026-07-01,mañana,3'])
        self.assertEqual(len(t.cargar_datasets(self.root)[0]), 2)

    def test_retrain_retira_el_csv_si_el_modelo_se_descarta(self):
        cliente = main.create_app(data_dir=self.root, model_path=self.model).test_client()
        with patch.object(retrain, 'reentrenar', return_value={
                'estado': 'descartado', 'motivo': 'MAE peor que el umbral.'}):
            respuesta = cliente.post('/retrain', json={'csvText': CSV_NUEVO})
        # 200 y no 409: si no, el cliente lanzaría y el usuario no vería el motivo.
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json()['status'], 'error')
        self.assertEqual(respuesta.get_json()['rowsIngested'], 2)
        self.assertFalse(list(self.root.glob('subida_*.csv')))

    def test_retrain_acepta_el_csv_como_archivo(self):
        cliente = main.create_app(data_dir=self.root, model_path=self.model).test_client()
        with patch.object(retrain, 'reentrenar', return_value=INFORME_OK):
            # Con BOM, que es como lo exporta Excel.
            datos = {'file': (io.BytesIO(CSV_NUEVO.encode('utf-8-sig')), 'ocupacion.csv')}
            respuesta = cliente.post('/retrain', data=datos, content_type='multipart/form-data')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json()['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
