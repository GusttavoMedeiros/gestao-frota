from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(50), unique=True, nullable=False)
    nome = db.Column(db.String(100))
    senha_hash = db.Column(db.String(255), nullable=False)

    def definir_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def conferir_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)

    def __repr__(self):
        return f"<Usuario {self.usuario}>"


class Veiculo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    placa = db.Column(db.String(10), unique=True, nullable=False)
    marca = db.Column(db.String(50), nullable=False)
    modelo = db.Column(db.String(50), nullable=False)
    ano = db.Column(db.Integer, nullable=False)
    quilometragem = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="ativo")

    motoristas = db.relationship("Motorista", backref="veiculo", lazy=True)
    manutencoes = db.relationship("Manutencao", backref="veiculo", lazy=True, cascade="all, delete-orphan")
    abastecimentos = db.relationship("Abastecimento", backref="veiculo", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Veiculo {self.placa}>"


class Motorista(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cnh = db.Column(db.String(20), nullable=False)
    categoria_cnh = db.Column(db.String(5), nullable=False)
    telefone = db.Column(db.String(20))
    veiculo_id = db.Column(db.Integer, db.ForeignKey("veiculo.id"), nullable=True)

    abastecimentos = db.relationship("Abastecimento", backref="motorista", lazy=True)

    def __repr__(self):
        return f"<Motorista {self.nome}>"


class Manutencao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    veiculo_id = db.Column(db.Integer, db.ForeignKey("veiculo.id"), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    data = db.Column(db.Date, nullable=False)
    quilometragem = db.Column(db.Integer, nullable=False)
    custo = db.Column(db.Float, nullable=False, default=0)
    descricao = db.Column(db.Text)
    proxima_data = db.Column(db.Date, nullable=True)
    proxima_km = db.Column(db.Integer, nullable=True)

    def __repr__(self):
        return f"<Manutencao {self.tipo} - veiculo {self.veiculo_id}>"


class Abastecimento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    veiculo_id = db.Column(db.Integer, db.ForeignKey("veiculo.id"), nullable=False)
    motorista_id = db.Column(db.Integer, db.ForeignKey("motorista.id"), nullable=True)
    data = db.Column(db.Date, nullable=False)
    tipo_combustivel = db.Column(db.String(20), nullable=False)
    litros = db.Column(db.Float, nullable=False)
    valor_total = db.Column(db.Float, nullable=False)
    quilometragem = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f"<Abastecimento veiculo {self.veiculo_id} em {self.data}>"
