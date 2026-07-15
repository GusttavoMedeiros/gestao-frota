import os
import re
import shutil
import tempfile
import unittest
from io import BytesIO

arquivo = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
arquivo.close()
os.environ["DATABASE_URL"] = "sqlite:///" + arquivo.name.replace("\\", "/")
os.environ["SECRET_KEY"] = "teste-segredo-fixo"

from app import app  # noqa: E402
from models import Usuario, db  # noqa: E402


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.uploads = tempfile.mkdtemp()
        app.config.update(TESTING=True, UPLOAD_FOLDER=cls.uploads)
        with app.app_context():
            usuario = Usuario(usuario="admin", nome="Admin")
            usuario.definir_senha("segredo123")
            db.session.add(usuario)
            db.session.commit()
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        with app.app_context():
            db.drop_all()
            db.session.remove()
            db.engine.dispose()
        os.unlink(arquivo.name)
        shutil.rmtree(cls.uploads)

    def autenticar(self):
        resposta = self.client.post("/api/login", json={"usuario": "admin", "senha": "segredo123"})
        self.assertEqual(resposta.status_code, 200)
        return {"Authorization": "Bearer " + resposta.json["token"]}

    def test_login_dados_e_crud(self):
        headers = self.autenticar()
        origem = {**headers, "Origin": "http://127.0.0.1:5173"}
        dados = self.client.get("/api/dados", headers=origem)
        self.assertEqual(dados.status_code, 200)
        self.assertEqual(dados.headers["Access-Control-Allow-Origin"], "http://127.0.0.1:5173")

        criado = self.client.post("/api/veiculos", headers=headers, json={
            "placa": "ABC1D23", "marca": "VW", "modelo": "Delivery",
            "ano": 2024, "tipo": "caminhao", "status": "ativo",
        })
        self.assertEqual(criado.status_code, 201)
        self.assertEqual(criado.json["placa"], "ABC1D23")
        identificador = criado.json["id"]

        editado = self.client.put(f"/api/veiculos/{identificador}", headers=headers, json={
            "placa": "ABC1D23", "marca": "VW", "modelo": "Delivery Express",
            "ano": 2024, "tipo": "caminhao", "status": "ativo",
        })
        self.assertEqual(editado.status_code, 200)
        self.assertEqual(editado.json["modelo"], "Delivery Express")

        excluido = self.client.delete(f"/api/veiculos/{identificador}", headers=headers)
        self.assertEqual(excluido.status_code, 200)

    def test_api_exige_token(self):
        self.assertEqual(self.client.get("/api/dados").status_code, 401)

    def test_frontend_servido_pelo_flask(self):
        pagina = self.client.get("/")
        self.assertEqual(pagina.status_code, 200)
        html = pagina.get_data(as_text=True)
        self.assertIn('<div id="root"></div>', html)
        asset = re.search(r'src="(/assets/[^"]+\.js)"', html).group(1)
        respostas = [self.client.get(asset), self.client.get("/manifest.webmanifest"), self.client.get("/sw.js")]
        self.assertTrue(all(resposta.status_code == 200 for resposta in respostas))
        pagina.close()
        for resposta in respostas:
            resposta.close()
        self.assertEqual(self.client.get("/legacy").status_code, 302)

    def test_fluxo_completo(self):
        headers = self.autenticar()
        veiculo = self.client.post("/api/veiculos", headers=headers, json={
            "placa": "XYZ9A87", "marca": "Mercedes", "modelo": "Atego",
            "ano": 2023, "tipo": "caminhao", "status": "ativo",
        }).json
        motorista = self.client.post("/api/motoristas", headers=headers, json={
            "nome": "Joao Teste", "cnh_numero": "123456", "cnh_categoria": "D",
            "status": "ativo",
        }).json
        abastecimento = self.client.post("/api/abastecimentos", headers=headers, json={
            "veiculo_id": veiculo["id"], "motorista_id": motorista["id"],
            "data": "2026-07-14", "km": 1000, "litros": 100,
            "valor_total": 650, "tipo_combustivel": "diesel_s10",
        })
        self.assertEqual(abastecimento.status_code, 201)
        manutencao = self.client.post("/api/manutencoes", headers=headers, json={
            "veiculo_id": veiculo["id"], "tipo": "preventiva", "categoria": "oleo",
            "descricao": "Troca de oleo", "data": "2026-07-14", "km": 1000,
            "valor": 400, "status": "concluida",
        })
        self.assertEqual(manutencao.status_code, 201)
        despesa = self.client.post("/api/despesas", headers=headers, json={
            "veiculo_id": veiculo["id"], "categoria": "seguro", "descricao": "Seguro",
            "data": "2026-07-14", "valor": 1200, "status": "pago",
        })
        self.assertEqual(despesa.status_code, 201)

        upload = self.client.post("/api/arquivos", headers=headers,
                                  data={"arquivo": (BytesIO(b"%PDF-teste"), "teste.pdf")})
        self.assertEqual(upload.status_code, 201)
        documento = self.client.post("/api/documentos", headers=headers, json={
            "veiculo_id": veiculo["id"], "tipo": "crlv", "descricao": "CRLV",
            "validade": "2026-08-01", "arquivo_path": upload.json["path"],
        })
        self.assertEqual(documento.status_code, 201)
        arquivo_baixado = self.client.get(f"/api/arquivos/{upload.json['path']}", headers=headers)
        self.assertEqual(arquivo_baixado.status_code, 200)
        arquivo_baixado.close()

        dados = self.client.get("/api/dados", headers=headers).json
        self.assertTrue(any(item["placa"] == "XYZ9A87" for item in dados["vehicles"]))
        self.assertTrue(dados["fuelLogs"])
        self.assertTrue(dados["maintenances"])
        self.assertTrue(dados["expenses"])
        self.assertTrue(dados["documents"])
        self.assertEqual(self.client.options(
            "/api/dados", headers={"Origin": "http://127.0.0.1:5173"}
        ).headers["Access-Control-Allow-Origin"], "http://127.0.0.1:5173")

    def test_rejeita_status_invalido(self):
        resposta = self.client.post("/api/veiculos", headers=self.autenticar(), json={
            "placa": "DEF4G56", "marca": "VW", "modelo": "Delivery",
            "ano": 2024, "tipo": "caminhao", "status": "qualquer",
        })
        self.assertEqual(resposta.status_code, 400)


if __name__ == "__main__":
    unittest.main()
