import unittest
import json
from main import app

class PrediccionTests(unittest.TestCase):

    def setUp(self):
        """Configurar cliente de pruebas de Flask."""
        self.cliente = app.test_client()

    def test_landing_page(self):
        """Probar que la página principal responde 200 OK."""
        respuesta = self.cliente.get('/')
        self.assertEqual(respuesta.status_code, 200)
        datos = json.loads(respuesta.data)
        self.assertIn("proyecto", datos)

    def test_predict_exitoso(self):
        """Probar una predicción válida enviando fecha y tramo."""
        payload = {
            "fecha": "2026-09-10",
            "tramo": "tarde"
        }
        respuesta = self.cliente.post(
            '/predict',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(respuesta.status_code, 200)
        datos = json.loads(respuesta.data)
        self.assertEqual(datos["status"], "success")
        self.assertIn("resultado", datos)

    def test_predict_datos_faltantes(self):
        """Probar error 400 cuando faltan datos obligatorios."""
        payload = {"fecha": "2026-09-10"}  # Falta 'tramo'
        respuesta = self.cliente.post(
            '/predict',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(respuesta.status_code, 400)

    def test_predict_formato_invalido(self):
        """Probar error 400 con formato de tramo o fecha erróneo."""
        payload = {
            "fecha": "2026-09-10",
            "tramo": "noche"  # Tramo inválido
        }
        respuesta = self.cliente.post(
            '/predict',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(respuesta.status_code, 400)

if __name__ == '__main__':
    unittest.main()