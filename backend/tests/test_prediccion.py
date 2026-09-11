import json
import unittest
from urllib.parse import urlencode

from main import app


class PrediccionTests(unittest.TestCase):

    def setUp(self):
        """Configurar cliente de pruebas de Flask."""
        self.cliente = app.test_client()

    def _get(self, ruta, **params):
        """GET con parámetros por query string, codificados correctamente."""
        query = urlencode(params)
        return self.cliente.get(f'{ruta}?{query}' if query else ruta)

    def test_landing_page(self):
        """Probar que la página principal responde 200 OK."""
        respuesta = self.cliente.get('/')
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("proyecto", respuesta.get_json())

    def test_docs_page(self):
        """La documentación interactiva (Swagger UI) se sirve como HTML."""
        respuesta = self.cliente.get('/docs')
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('text/html', respuesta.content_type)
        self.assertIn(b'swagger-ui', respuesta.data.lower())

    def test_openapi_spec(self):
        """El spec OpenAPI es JSON válido y documenta las rutas reales de la API."""
        respuesta = self.cliente.get('/openapi.json')
        self.assertEqual(respuesta.status_code, 200)
        spec = respuesta.get_json()
        self.assertEqual(spec['openapi'], '3.0.3')
        for ruta in ('/health', '/predict', '/predict/single', '/predict/range',
                     '/retrain', '/retrain/reset'):
            self.assertIn(ruta, spec['paths'])

    def test_health(self):
        """El health check nunca falla, aunque el modelo no esté disponible."""
        respuesta = self.cliente.get('/health')
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.get_json()['model_loaded'])

    def test_predict_criterio_de_evaluacion(self):
        """
        El endpoint principal de la evaluación: requests.get con fecha y
        tramo por query string, predicción real del modelo. /predict y
        /predict/single son alias del mismo handler.
        """
        for ruta in ('/predict', '/predict/single'):
            with self.subTest(ruta=ruta):
                respuesta = self._get(ruta, fecha='2026-09-10', tramo='tarde')
                self.assertEqual(respuesta.status_code, 200)
                datos = respuesta.get_json()
                self.assertEqual(datos['date'], '2026-09-10')
                self.assertEqual(datos['tramo'], 'tarde')
                self.assertGreaterEqual(datos['citasPrevistas'], 0)
                self.assertIn('version_modelo', datos)
                self.assertIn('entrenado_hasta', datos)

    def test_predict_acepta_date_como_alias_de_fecha(self):
        """El parámetro de query admite 'date' además de 'fecha'."""
        respuesta = self._get('/predict', date='2026-09-10', tramo='tarde')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.get_json()['date'], '2026-09-10')

    def test_predict_single_solo_get_post_da_405_en_json(self):
        """No hay POST en /predict/single: rechazado con 405 en JSON, no HTML."""
        respuesta = self.cliente.post(
            '/predict/single', data=json.dumps({"date": "2026-09-10", "tramo": "tarde"}),
            content_type='application/json')
        self.assertEqual(respuesta.status_code, 405)
        self.assertIn("error", respuesta.get_json())

    def test_predict_single_contrato(self):
        """La respuesta trae, como mínimo, los campos que consume el frontend."""
        respuesta = self._get('/predict/single', date='2026-09-10', tramo='manana')
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.get_json()
        self.assertGreaterEqual(set(datos), {"date", "tramo", "citasPrevistas"})
        self.assertEqual(datos["date"], "2026-09-10")
        # El tramo vuelve siempre sin ñ: es una clave literal de los gráficos.
        self.assertEqual(datos["tramo"], "manana")
        self.assertGreaterEqual(datos["citasPrevistas"], 0)

    def test_predict_single_acepta_la_enie(self):
        """'manana' y 'mañana' son el mismo tramo y dan el mismo resultado."""
        sin_enie = self._get('/predict/single', date='2026-09-10', tramo='manana')
        con_enie = self._get('/predict/single', date='2026-09-10', tramo='mañana')
        self.assertEqual(sin_enie.get_json(), con_enie.get_json())

    def test_predict_single_dia_de_cierre(self):
        """Navidad es cierre: 0 citas sin consultar al modelo."""
        respuesta = self._get('/predict/single', date='2026-12-25', tramo='tarde')
        self.assertEqual(respuesta.get_json()["citasPrevistas"], 0)

    def test_predict_datos_faltantes(self):
        """Probar error 400 cuando faltan datos obligatorios."""
        self.assertEqual(self._get('/predict/single', date='2026-09-10').status_code, 400)
        self.assertEqual(self.cliente.get('/predict/single').status_code, 400)

    def test_predict_formato_invalido(self):
        """Probar error 400 con formato de tramo o fecha erróneo."""
        self.assertEqual(
            self._get('/predict/single', date='2026-09-10', tramo='noche').status_code, 400)
        self.assertEqual(
            self._get('/predict/single', date='10/09/2026', tramo='tarde').status_code, 400)

    def test_predict_range_criterio_de_evaluacion(self):
        """GET /predict/range: mismo criterio de evaluación que /predict, aplicado al rango."""
        respuesta = self._get('/predict/range', startDate='2026-09-08', endDate='2026-09-14')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.get_json()["current"]), 7)

    def test_predict_range_solo_get_post_da_405_en_json(self):
        """No hay POST en /predict/range: rechazado con 405 en JSON, no HTML."""
        respuesta = self.cliente.post(
            '/predict/range', data=json.dumps({"startDate": "2026-09-08", "endDate": "2026-09-14"}),
            content_type='application/json')
        self.assertEqual(respuesta.status_code, 405)
        self.assertIn("error", respuesta.get_json())

    def test_predict_range_datos_faltantes(self):
        self.assertEqual(self.cliente.get('/predict/range').status_code, 400)
        self.assertEqual(self._get('/predict/range', startDate='2026-09-08').status_code, 400)

    def test_predict_range_contrato(self):
        """El rango devuelve un punto por día con los dos tramos."""
        respuesta = self._get('/predict/range', startDate='2026-09-08', endDate='2026-09-14')
        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.get_json()
        self.assertEqual(len(datos["current"]), 7)
        self.assertEqual(set(datos["current"][0]), {"date", "manana", "tarde"})
        self.assertEqual(datos["current"][0]["date"], "2026-09-08")

    def test_predict_range_reinserta_los_cierres(self):
        """
        Regresión del realineado del lote: build_features() filtra los días de
        cierre, así que las predicciones hay que devolverlas a su posición. Si
        se hiciera por índice, saldrían desplazadas sin dar ningún error.
        """
        datos = self._get('/predict/range', startDate='2025-12-23', endDate='2025-12-27').get_json()
        por_fecha = {d["date"]: d for d in datos["current"]}
        self.assertEqual(por_fecha["2025-12-25"], {"date": "2025-12-25", "manana": 0.0, "tarde": 0.0})
        self.assertGreater(por_fecha["2025-12-24"]["tarde"], 0)
        self.assertGreater(por_fecha["2025-12-26"]["tarde"], 0)

    def test_predict_range_todo_cierre(self):
        """Un rango enteramente cerrado no llega al modelo y no revienta."""
        datos = self._get('/predict/range', startDate='2026-01-01', endDate='2026-01-01').get_json()
        self.assertEqual(datos["current"], [{"date": "2026-01-01", "manana": 0.0, "tarde": 0.0}])

    def test_predict_range_invalido(self):
        """Fechas del revés o rango desmesurado: 400."""
        self.assertEqual(
            self._get('/predict/range', startDate='2026-09-14', endDate='2026-09-08').status_code, 400)
        self.assertEqual(
            self._get('/predict/range', startDate='2024-01-01', endDate='2030-12-31').status_code, 400)

    def test_previous_year_dentro_y_fuera_del_historico(self):
        """El año anterior son datos REALES del histórico, o null si no los hay."""
        dentro = self._get('/predict/range', startDate='2025-12-26', endDate='2025-12-27').get_json()
        self.assertEqual(dentro["previousYear"], [
            {"date": "2024-12-26", "manana": 4.0, "tarde": 6.0},
            {"date": "2024-12-27", "manana": 4.0, "tarde": 7.0},
        ])
        # El histórico empieza en 2024-05-09: un año antes de 2024-01 no hay nada.
        fuera = self._get('/predict/range', startDate='2024-01-08', endDate='2024-01-10').get_json()
        self.assertIsNone(fuera["previousYear"])

    def test_ruta_inexistente_responde_json(self):
        """Los 404 salen en JSON, no en el HTML de Werkzeug."""
        respuesta = self.cliente.get('/no-existe')
        self.assertEqual(respuesta.status_code, 404)
        self.assertIn("error", respuesta.get_json())


if __name__ == '__main__':
    unittest.main()
