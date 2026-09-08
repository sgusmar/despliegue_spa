import multiprocessing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import joblib
import pandas as pd
from flask import Flask

import model_service as servicio
import retrain
import train_model as t


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
        with patch.object(servicio, 'cargar_artefacto', side_effect=lambda: servicio.joblib.load(self.model)):
            pred = servicio.predecir_ocupacion('2026-09-10', 'tarde')
            self.assertEqual(pred['version_modelo'], art['version'])
            self.assertGreaterEqual(pred['prediccion_ocupacion'], 0)
            self.assertEqual(servicio.predecir_ocupacion('2026-12-25', 'mañana')['prediccion_ocupacion'], 0)
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

    def test_http_invalido_y_token(self):
        app = Flask(__name__)
        app.register_blueprint(retrain.retrain_bp)
        cliente = app.test_client()
        with patch.dict('os.environ', {'RETRAIN_TOKEN': ''}), patch.object(retrain, 'reentrenar') as entrenar:
            for payload in [[], [1], None, {'dias_validacion': 7.5}, {'dias_validacion': True},
                            {'dias_validacion': '60'}, {'dias_validacion': 6}]:
                import json
                self.assertEqual(cliente.post('/retrain', data=json.dumps(payload), content_type='application/json').status_code, 400)
            self.assertEqual(cliente.post('/retrain', data='{', content_type='application/json').status_code, 400)
            entrenar.assert_not_called()
            entrenar.return_value = {'estado': 'reemplazado'}
            self.assertEqual(cliente.post('/retrain').status_code, 200)
        with patch.dict('os.environ', {'RETRAIN_TOKEN': 'prueba'}), patch.object(retrain, 'reentrenar') as entrenar:
            self.assertEqual(cliente.post('/retrain').status_code, 401)
            entrenar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
