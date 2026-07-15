import os
import time
from datetime import date, datetime
from functools import wraps
from uuid import uuid4

from flask import Blueprint, current_app, g, jsonify, request, send_from_directory
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from models import (Abastecimento, Configuracao, Despesa, Documento,
                    Manutencao, Motorista, Usuario, Veiculo, db)

api = Blueprint("api", __name__, url_prefix="/api")


def configurar_api(app):
    app.config.setdefault("MAX_CONTENT_LENGTH", 10 * 1024 * 1024)
    app.config.setdefault("UPLOAD_FOLDER", os.path.join(app.root_path, "uploads"))

    @app.after_request
    def cors(resposta):
        if not request.path.startswith("/api/"):
            return resposta
        permitidas = {
            origem.strip() for origem in os.environ.get(
                "ALLOWED_ORIGINS",
                "http://127.0.0.1:5173",
            ).split(",") if origem.strip()
        }
        origem = request.headers.get("Origin")
        if origem in permitidas:
            resposta.headers["Access-Control-Allow-Origin"] = origem
            resposta.headers["Vary"] = "Origin"
            resposta.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            resposta.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        return resposta


def _assinador():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="kg-frota-api")


def autenticado(funcao):
    @wraps(funcao)
    def wrapper(*args, **kwargs):
        cabecalho = request.headers.get("Authorization", "")
        token = cabecalho.removeprefix("Bearer ").strip()
        try:
            usuario_id = _assinador().loads(token, max_age=8 * 60 * 60)
        except (BadSignature, SignatureExpired):
            return jsonify(erro="Sessao expirada. Entre novamente."), 401
        g.usuario = db.session.get(Usuario, usuario_id)
        if not g.usuario:
            return jsonify(erro="Usuario nao encontrado."), 401
        return funcao(*args, **kwargs)
    return wrapper


@api.before_request
def preflight():
    if request.method == "OPTIONS":
        return "", 204


@api.post("/login")
def login():
    dados = request.get_json(silent=True) or {}
    nome = str(dados.get("usuario") or dados.get("email") or "").strip().lower()
    senha = str(dados.get("senha") or dados.get("password") or "")
    usuario = Usuario.query.filter_by(usuario=nome).first()
    if not usuario or not usuario.conferir_senha(senha):
        time.sleep(0.6)
        return jsonify(erro="Usuario ou senha incorretos."), 401
    return jsonify(token=_assinador().dumps(usuario.id), usuario={"id": str(usuario.id), "nome": usuario.nome or usuario.usuario})


@api.get("/sessao")
@autenticado
def sessao():
    return jsonify(usuario={"id": str(g.usuario.id), "nome": g.usuario.nome or g.usuario.usuario})


def _data(valor, obrigatorio=False):
    if not valor:
        if obrigatorio:
            raise ValueError("Data obrigatoria.")
        return None
    try:
        return datetime.strptime(str(valor), "%Y-%m-%d").date()
    except ValueError as erro:
        raise ValueError("Data invalida.") from erro


def _numero(valor, rotulo, minimo=None, inteiro=False, obrigatorio=True):
    if valor in (None, ""):
        if obrigatorio:
            raise ValueError(f"{rotulo} obrigatorio.")
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError) as erro:
        raise ValueError(f"{rotulo} invalido.") from erro
    if minimo is not None and numero < minimo:
        raise ValueError(f"{rotulo} deve ser maior ou igual a {minimo}.")
    return int(numero) if inteiro else numero


def _texto(dados, campo, obrigatorio=False, padrao=""):
    valor = str(dados.get(campo, padrao) or "").strip()
    if obrigatorio and not valor:
        raise ValueError(f"{campo} obrigatorio.")
    return valor


def _escolha(dados, campo, validos, padrao):
    valor = _texto(dados, campo, padrao=padrao)
    if valor not in validos:
        raise ValueError(f"{campo} invalido.")
    return valor


def _id_relacionado(modelo, valor, rotulo, obrigatorio=False):
    if valor in (None, ""):
        if obrigatorio:
            raise ValueError(f"{rotulo} obrigatorio.")
        return None
    try:
        identificador = int(valor)
    except (TypeError, ValueError) as erro:
        raise ValueError(f"{rotulo} invalido.") from erro
    if not db.session.get(modelo, identificador):
        raise ValueError(f"{rotulo} nao encontrado.")
    return identificador


def aplicar_veiculo(item, dados):
    item.placa = _texto(dados, "placa", True).upper()
    item.marca = _texto(dados, "marca", True)
    item.modelo = _texto(dados, "modelo", True)
    item.ano = _numero(dados.get("ano"), "Ano", 1950, True)
    item.tipo = _escolha(dados, "tipo", {"caminhao", "carro", "moto", "utilitario", "outro"}, "caminhao")
    item.status = _escolha(dados, "status", {"ativo", "inativo", "vendido", "manutencao"}, "ativo")
    item.renavam = _texto(dados, "renavam") or None
    item.chassi = _texto(dados, "chassi") or None
    if dados.get("km_atual") not in (None, ""):
        item.quilometragem = _numero(dados["km_atual"], "KM", 0, True)


def aplicar_motorista(item, dados):
    item.nome = _texto(dados, "nome", True)
    item.cnh = _texto(dados, "cnh_numero", True)
    item.categoria_cnh = _texto(dados, "cnh_categoria", True).upper()
    item.validade_cnh = _data(dados.get("cnh_validade"))
    item.telefone = _texto(dados, "telefone") or None
    item.status = _escolha(dados, "status", {"ativo", "inativo"}, "ativo")


def aplicar_abastecimento(item, dados):
    item.veiculo_id = _id_relacionado(Veiculo, dados.get("veiculo_id"), "Veiculo", True)
    item.motorista_id = _id_relacionado(Motorista, dados.get("motorista_id"), "Motorista")
    item.data = _data(dados.get("data"), True)
    item.quilometragem = _numero(dados.get("km"), "KM", 0, True)
    item.litros = _numero(dados.get("litros"), "Litros", 0.01)
    item.valor_total = _numero(dados.get("valor_total"), "Valor total", 0)
    item.tipo_combustivel = _escolha(
        dados, "tipo_combustivel",
        {"diesel", "diesel_s10", "gasolina", "etanol", "gnv", "arla", "outro"},
        "diesel",
    )
    item.posto = _texto(dados, "posto") or None
    item.observacao = _texto(dados, "observacao") or None
    veiculo = db.session.get(Veiculo, item.veiculo_id)
    veiculo.quilometragem = max(veiculo.quilometragem or 0, item.quilometragem)


def aplicar_manutencao(item, dados):
    item.veiculo_id = _id_relacionado(Veiculo, dados.get("veiculo_id"), "Veiculo", True)
    item.tipo = _escolha(dados, "tipo", {"preventiva", "corretiva"}, "preventiva")
    item.categoria = _escolha(
        dados, "categoria",
        {"oleo", "pneu", "freio", "motor", "suspensao", "eletrica", "revisao", "funilaria", "outros"},
        "outros",
    )
    item.descricao = _texto(dados, "descricao", True)
    item.data = _data(dados.get("data"), True)
    item.quilometragem = _numero(dados.get("km"), "KM", 0, True, False) or 0
    item.custo = _numero(dados.get("valor"), "Valor", 0, obrigatorio=False) or 0
    item.oficina = _texto(dados, "oficina") or None
    item.status = _escolha(dados, "status", {"agendada", "em_andamento", "concluida"}, "agendada")
    item.proxima_data = _data(dados.get("proxima_data"))
    item.proxima_km = _numero(dados.get("proxima_km"), "Proxima KM", 0, True, False)


def aplicar_despesa(item, dados):
    item.veiculo_id = _id_relacionado(Veiculo, dados.get("veiculo_id"), "Veiculo")
    item.categoria = _escolha(
        dados, "categoria",
        {"ipva", "seguro", "multa", "pedagio", "licenciamento", "financiamento", "outros"},
        "outros",
    )
    item.descricao = _texto(dados, "descricao", True)
    item.data = _data(dados.get("data"), True)
    item.valor = _numero(dados.get("valor"), "Valor", 0)
    item.vencimento = _data(dados.get("vencimento"))
    item.status = _escolha(dados, "status", {"pendente", "pago"}, "pendente")


def aplicar_documento(item, dados):
    item.veiculo_id = _id_relacionado(Veiculo, dados.get("veiculo_id"), "Veiculo")
    item.motorista_id = _id_relacionado(Motorista, dados.get("motorista_id"), "Motorista")
    if item.veiculo_id and item.motorista_id:
        raise ValueError("Escolha veiculo ou motorista, nao os dois.")
    item.tipo = _escolha(
        dados, "tipo",
        {"crlv", "cnh", "seguro", "ipva", "licenciamento", "contrato", "outros"},
        "outros",
    )
    item.descricao = _texto(dados, "descricao") or None
    item.validade = _data(dados.get("validade"))
    item.arquivo_path = _texto(dados, "arquivo_path") or None


def _iso(valor):
    return valor.isoformat() if valor else None


def veiculo_json(v):
    return {"id": str(v.id), "placa": v.placa, "marca": v.marca, "modelo": v.modelo,
            "ano": v.ano, "tipo": v.tipo, "km_atual": v.quilometragem,
            "renavam": v.renavam, "chassi": v.chassi, "status": v.status}


def motorista_json(m):
    return {"id": str(m.id), "nome": m.nome, "cnh_numero": m.cnh,
            "cnh_categoria": m.categoria_cnh, "cnh_validade": _iso(m.validade_cnh),
            "telefone": m.telefone, "status": m.status}


def abastecimento_json(a):
    return {"id": str(a.id), "veiculo_id": str(a.veiculo_id),
            "motorista_id": str(a.motorista_id) if a.motorista_id else None,
            "data": _iso(a.data), "km": a.quilometragem, "litros": a.litros,
            "valor_total": a.valor_total,
            "valor_litro": a.valor_total / a.litros if a.litros else None,
            "tipo_combustivel": a.tipo_combustivel, "posto": a.posto,
            "observacao": a.observacao,
            "veiculos": {"placa": a.veiculo.placa, "modelo": a.veiculo.modelo},
            "motoristas": {"nome": a.motorista.nome} if a.motorista else None}


def manutencao_json(m):
    return {"id": str(m.id), "veiculo_id": str(m.veiculo_id), "tipo": m.tipo,
            "categoria": m.categoria, "descricao": m.descricao or "", "data": _iso(m.data),
            "km": m.quilometragem, "valor": m.custo, "oficina": m.oficina,
            "status": m.status, "proxima_data": _iso(m.proxima_data),
            "proxima_km": m.proxima_km, "veiculos": {"placa": m.veiculo.placa}}


def despesa_json(d):
    return {"id": str(d.id), "veiculo_id": str(d.veiculo_id) if d.veiculo_id else None,
            "categoria": d.categoria, "descricao": d.descricao, "data": _iso(d.data),
            "valor": d.valor, "vencimento": _iso(d.vencimento), "status": d.status,
            "veiculos": {"placa": d.veiculo.placa} if d.veiculo else None}


def documento_json(d):
    return {"id": str(d.id), "veiculo_id": str(d.veiculo_id) if d.veiculo_id else None,
            "motorista_id": str(d.motorista_id) if d.motorista_id else None,
            "tipo": d.tipo, "descricao": d.descricao, "validade": _iso(d.validade),
            "arquivo_path": d.arquivo_path,
            "veiculos": {"placa": d.veiculo.placa} if d.veiculo else None,
            "motoristas": {"nome": d.motorista.nome} if d.motorista else None}


RECURSOS = {
    "veiculos": (Veiculo, aplicar_veiculo, veiculo_json),
    "motoristas": (Motorista, aplicar_motorista, motorista_json),
    "abastecimentos": (Abastecimento, aplicar_abastecimento, abastecimento_json),
    "manutencoes": (Manutencao, aplicar_manutencao, manutencao_json),
    "despesas": (Despesa, aplicar_despesa, despesa_json),
    "documentos": (Documento, aplicar_documento, documento_json),
}


def _alertas(config):
    hoje = date.today()
    itens = []

    def adicionar(tipo, identificador, veiculo_id, titulo, vencimento):
        if not vencimento:
            return
        dias = (vencimento - hoje).days
        if dias <= config.dias_aviso_vencimento:
            itens.append({"tipo": tipo, "referencia_id": str(identificador),
                          "veiculo_id": str(veiculo_id) if veiculo_id else None,
                          "titulo": titulo, "vencimento": vencimento.isoformat(),
                          "dias_restantes": dias,
                          "situacao": "vencido" if dias < 0 else "vence_em_breve"})

    for motorista in Motorista.query.all():
        adicionar("cnh", motorista.id, None, f"CNH - {motorista.nome}", motorista.validade_cnh)
    for documento in Documento.query.all():
        adicionar("documento", documento.id, documento.veiculo_id,
                  documento.descricao or documento.tipo.upper(), documento.validade)
    for despesa in Despesa.query.filter_by(status="pendente").all():
        adicionar("despesa", despesa.id, despesa.veiculo_id, despesa.descricao, despesa.vencimento)
    for manutencao in Manutencao.query.filter(Manutencao.status != "concluida").all():
        adicionar("manutencao", manutencao.id, manutencao.veiculo_id,
                  manutencao.descricao or manutencao.categoria, manutencao.proxima_data)
    return sorted(itens, key=lambda item: item["dias_restantes"])


@api.get("/dados")
@autenticado
def dados():
    hoje = date.today()
    inicio = hoje.replace(day=1)
    config = Configuracao.query.first()
    if not config:
        config = Configuracao(id=1)
        db.session.add(config)
        db.session.commit()
    custo_combustivel = db.session.query(func.coalesce(func.sum(Abastecimento.valor_total), 0)).filter(Abastecimento.data >= inicio).scalar()
    custo_manutencao = db.session.query(func.coalesce(func.sum(Manutencao.custo), 0)).filter(Manutencao.data >= inicio).scalar()
    custo_despesas = db.session.query(func.coalesce(func.sum(Despesa.valor), 0)).filter(Despesa.data >= inicio).scalar()
    alertas = _alertas(config)
    relatorio = [
        {"categoria": "combustivel", "total": float(custo_combustivel)},
        {"categoria": "manutencao", "total": float(custo_manutencao)},
        {"categoria": "despesas", "total": float(custo_despesas)},
    ]
    return jsonify({
        "dashboard": {
            "veiculos_ativos": Veiculo.query.filter_by(status="ativo").count(),
            "motoristas_ativos": Motorista.query.filter_by(status="ativo").count(),
            "custo_mes": float(custo_combustivel + custo_manutencao + custo_despesas),
            "abastecimentos_mes": Abastecimento.query.filter(Abastecimento.data >= inicio).count(),
            "manutencoes_pendentes": Manutencao.query.filter(Manutencao.status != "concluida").count(),
            "alertas_abertos": len(alertas),
        },
        "alerts": alertas,
        "vehicles": [veiculo_json(v) for v in Veiculo.query.order_by(Veiculo.placa).all()],
        "drivers": [motorista_json(m) for m in Motorista.query.order_by(Motorista.nome).all()],
        "fuelLogs": [abastecimento_json(a) for a in Abastecimento.query.order_by(Abastecimento.data.desc(), Abastecimento.id.desc()).all()],
        "maintenances": [manutencao_json(m) for m in Manutencao.query.order_by(Manutencao.data.desc(), Manutencao.id.desc()).all()],
        "expenses": [despesa_json(d) for d in Despesa.query.order_by(Despesa.data.desc(), Despesa.id.desc()).all()],
        "documents": [documento_json(d) for d in Documento.query.order_by(Documento.validade).all()],
        "reportCosts": relatorio,
        "settings": {"empresa_id": "1", "dias_aviso_vencimento": config.dias_aviso_vencimento,
                     "km_aviso_manutencao": config.km_aviso_manutencao},
    })


@api.post("/<recurso>")
@autenticado
def criar(recurso):
    if recurso not in RECURSOS:
        return jsonify(erro="Recurso nao encontrado."), 404
    modelo, aplicar, serializar = RECURSOS[recurso]
    item = modelo()
    try:
        aplicar(item, request.get_json(silent=True) or {})
        db.session.add(item)
        db.session.commit()
        return jsonify(serializar(item)), 201
    except ValueError as erro:
        db.session.rollback()
        return jsonify(erro=str(erro)), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify(erro="Registro duplicado ou relacionado a dados invalidos."), 409


@api.put("/<recurso>/<int:identificador>")
@autenticado
def editar(recurso, identificador):
    if recurso not in RECURSOS:
        return jsonify(erro="Recurso nao encontrado."), 404
    modelo, aplicar, serializar = RECURSOS[recurso]
    item = db.session.get(modelo, identificador)
    if not item:
        return jsonify(erro="Registro nao encontrado."), 404
    try:
        aplicar(item, request.get_json(silent=True) or {})
        db.session.commit()
        return jsonify(serializar(item))
    except ValueError as erro:
        db.session.rollback()
        return jsonify(erro=str(erro)), 400
    except IntegrityError:
        db.session.rollback()
        return jsonify(erro="Registro duplicado ou relacionado a dados invalidos."), 409


@api.delete("/<recurso>/<int:identificador>")
@autenticado
def excluir(recurso, identificador):
    if recurso not in RECURSOS:
        return jsonify(erro="Recurso nao encontrado."), 404
    modelo = RECURSOS[recurso][0]
    item = db.session.get(modelo, identificador)
    if not item:
        return jsonify(erro="Registro nao encontrado."), 404
    db.session.delete(item)
    db.session.commit()
    return jsonify(id=str(identificador))


@api.put("/configuracoes")
@autenticado
def configuracoes():
    dados = request.get_json(silent=True) or {}
    config = Configuracao.query.first() or Configuracao(id=1)
    try:
        config.dias_aviso_vencimento = _numero(dados.get("dias_aviso_vencimento"), "Dias de aviso", 1, True)
        config.km_aviso_manutencao = _numero(dados.get("km_aviso_manutencao"), "KM de aviso", 1, True)
    except ValueError as erro:
        return jsonify(erro=str(erro)), 400
    db.session.add(config)
    db.session.commit()
    return jsonify(empresa_id="1", dias_aviso_vencimento=config.dias_aviso_vencimento,
                   km_aviso_manutencao=config.km_aviso_manutencao)


def _pasta_uploads():
    pasta = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(pasta, exist_ok=True)
    return pasta


@api.post("/arquivos")
@autenticado
def enviar_arquivo():
    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        return jsonify(erro="Selecione um arquivo."), 400
    nome = secure_filename(arquivo.filename)
    extensao = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    if extensao not in {"pdf", "png", "jpg", "jpeg", "webp"}:
        return jsonify(erro="Envie PDF ou imagem."), 400
    caminho = f"{uuid4().hex}-{nome}"
    arquivo.save(os.path.join(_pasta_uploads(), caminho))
    return jsonify(path=caminho), 201


@api.get("/arquivos/<path:caminho>")
@autenticado
def baixar_arquivo(caminho):
    return send_from_directory(_pasta_uploads(), caminho, as_attachment=False)


@api.delete("/arquivos/<path:caminho>")
@autenticado
def apagar_arquivo(caminho):
    arquivo = os.path.join(_pasta_uploads(), os.path.basename(caminho))
    if os.path.exists(arquivo):
        os.remove(arquivo)
    return "", 204
