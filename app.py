import csv
import io
import math
import os
import re
import secrets
import time
from datetime import date, datetime, timedelta

from flask import (Flask, Response, abort, flash, redirect, render_template,
                   request, session, url_for)
from sqlalchemy import func, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from models import Abastecimento, Manutencao, Motorista, Usuario, Veiculo, db

app = Flask(__name__)

# Banco: usa DATABASE_URL se definida; senão, um arquivo SQLite na pasta do
# projeto (caminho absoluto, para não depender de onde o app foi iniciado).
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = (
    os.environ.get("DATABASE_URL") or "sqlite:///" + os.path.join(BASE_DIR, "frota.db")
)

# Em produção, defina a variável de ambiente SECRET_KEY com um valor fixo.
# Sem ela, uma chave aleatória é gerada a cada execução (seguro para uso local).
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

# Cookies de sessão. Em produção (FLASK_DEBUG=0) o cookie só trafega em HTTPS.
EM_PRODUCAO = os.environ.get("FLASK_DEBUG", "1") == "0"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = EM_PRODUCAO
# Desloga automaticamente após este tempo SEM uso (renovado a cada ação).
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
app.config["SESSION_REFRESH_EACH_REQUEST"] = True

db.init_app(app)


def garantir_colunas():
    """Adiciona colunas novas a bancos que já existem, sem apagar dados.
    (db.create_all só cria tabelas que faltam, não colunas novas.)"""
    novas = {
        "veiculo": {"venc_licenciamento": "DATE", "venc_seguro": "DATE"},
        "motorista": {"validade_cnh": "DATE"},
        "abastecimento": {"tanque_cheio": "BOOLEAN"},
    }
    inspetor = inspect(db.engine)
    tabelas = inspetor.get_table_names()
    for tabela, colunas in novas.items():
        if tabela not in tabelas:
            continue
        existentes = {c["name"] for c in inspetor.get_columns(tabela)}
        for nome, tipo in colunas.items():
            if nome not in existentes:
                db.session.execute(text(f"ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}"))
    db.session.commit()


with app.app_context():
    db.create_all()
    garantir_colunas()


# ---------------- Proteção CSRF ----------------

def csrf_token():
    """Token por sessão, embutido em todos os formulários POST."""
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


def redireciona_local(padrao="index"):
    """Redireciona para a página anterior somente se ela for deste próprio site."""
    anterior = request.referrer or ""
    if anterior.startswith(request.host_url):
        return redirect(anterior)
    return redirect(url_for(padrao))


@app.before_request
def proteger_csrf():
    if request.method == "POST":
        token = session.get("_csrf")
        if not token or token != request.form.get("_csrf"):
            flash("Sua sessão expirou. Recarregue a página e tente novamente.", "danger")
            return redireciona_local()


@app.after_request
def cabecalhos_de_seguranca(resposta):
    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    resposta.headers.setdefault("X-Frame-Options", "DENY")
    resposta.headers.setdefault("Referrer-Policy", "same-origin")
    return resposta


# ---------------- Autenticação ----------------

# Endpoints acessíveis sem login (a própria tela de login, o primeiro acesso,
# arquivos estáticos e o service worker do PWA).
ENDPOINTS_PUBLICOS = {"login", "logout", "configurar", "service_worker", "static",
                      "backup_automatico"}


@app.before_request
def exigir_login():
    if request.endpoint in ENDPOINTS_PUBLICOS:
        return
    if "user_id" in session:
        return  # já logado — segue sem consultar o banco
    if Usuario.query.count() == 0:
        return redirect(url_for("configurar"))
    return redirect(url_for("login"))


@app.context_processor
def injeta_usuario():
    uid = session.get("user_id")
    return {"usuario_atual": db.session.get(Usuario, uid) if uid else None}


@app.route("/configurar", methods=["GET", "POST"])
def configurar():
    # Só funciona enquanto não houver nenhum usuário (primeiro acesso).
    if Usuario.query.count() > 0:
        return redirect(url_for("login"))
    if request.method == "POST":
        try:
            usuario = exigir_texto("usuario", "Usuário", 50).lower()
            senha = request.form.get("senha", "")
            confirmar = request.form.get("confirmar", "")
            if len(senha) < 6:
                raise ErroFormulario("A senha deve ter pelo menos 6 caracteres.")
            if senha != confirmar:
                raise ErroFormulario("As senhas não conferem.")
            novo = Usuario(usuario=usuario, nome=request.form.get("nome", "").strip())
            novo.definir_senha(senha)
            db.session.add(novo)
            db.session.commit()
        except ErroFormulario as erro:
            db.session.rollback()
            flash(str(erro), "danger")
            return render_template("configurar.html")
        session.clear()
        session.permanent = True
        session["user_id"] = novo.id
        flash("Conta criada! Bem-vindo ao sistema.", "success")
        return redirect(url_for("index"))
    return render_template("configurar.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))
    if Usuario.query.count() == 0:
        return redirect(url_for("configurar"))
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip().lower()
        senha = request.form.get("senha", "")
        conta = Usuario.query.filter_by(usuario=usuario).first()
        if conta and conta.conferir_senha(senha):
            csrf = session.get("_csrf")
            session.clear()
            session.permanent = True
            if csrf:
                session["_csrf"] = csrf
            session["user_id"] = conta.id
            return redirect(url_for("index"))
        time.sleep(0.6)  # freia tentativas automatizadas de adivinhar a senha
        flash("Usuário ou senha incorretos.", "danger")
        return render_template("login.html", usuario=usuario)
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Você saiu do sistema.", "success")
    return redirect(url_for("login"))


@app.route("/sw.js")
def service_worker():
    resposta = app.send_static_file("sw.js")
    resposta.headers["Content-Type"] = "application/javascript"
    resposta.headers["Service-Worker-Allowed"] = "/"
    resposta.headers["Cache-Control"] = "no-cache"
    return resposta


# ---------------- Filtros de formatação ----------------

@app.template_filter("brl")
def formato_brl(valor):
    if valor is None:
        return "—"
    return "R$ " + f"{valor:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


@app.template_filter("milhar")
def formato_milhar(valor):
    if valor is None:
        return "—"
    return f"{int(valor):,}".replace(",", ".")


@app.template_filter("data_br")
def formato_data_br(valor):
    return valor.strftime("%d/%m/%Y") if valor else "—"


@app.template_filter("compacto")
def formato_compacto(valor):
    """Número curto para eixos de gráfico: 1.200 -> '1,2 mil'."""
    if valor >= 1000:
        texto = f"{valor / 1000:.1f}".replace(".", ",")
        if texto.endswith(",0"):
            texto = texto[:-2]
        return texto + " mil"
    return formato_milhar(int(valor))


@app.template_filter("venc_badge")
def venc_badge(data):
    """Cor da data de vencimento: 'danger' se vencida, 'warning' se em até 30 dias."""
    if not data:
        return ""
    dias = (data - date.today()).days
    if dias < 0:
        return "danger"
    if dias <= 30:
        return "warning"
    return ""


# ---------------- Leitura e validação de formulários ----------------

class ErroFormulario(Exception):
    """Erro de validação com mensagem amigável para o usuário."""


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date() if value else None


def parse_num(value):
    """Aceita números em formato brasileiro ('600.000', '1.234,56') ou padrão ('600000', '1234.56')."""
    texto = (value or "").strip().replace(" ", "")
    if not texto:
        return None
    if "," in texto:
        # vírgula é decimal; pontos são separadores de milhar
        texto = texto.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", texto):
        # apenas pontos em grupos de 3 dígitos: separador de milhar
        texto = texto.replace(".", "")
    return float(texto)


def exigir_texto(campo, rotulo, maximo=None):
    valor = request.form.get(campo, "").strip()
    if not valor:
        raise ErroFormulario(f'O campo "{rotulo}" é obrigatório.')
    if maximo and len(valor) > maximo:
        raise ErroFormulario(f'O campo "{rotulo}" deve ter no máximo {maximo} caracteres.')
    return valor


def ler_numero(campo, rotulo, obrigatorio=True, minimo=None, maximo=None,
               inteiro=False, positivo=False, padrao=None):
    bruto = request.form.get(campo, "")
    try:
        numero = parse_num(bruto)
    except ValueError:
        raise ErroFormulario(f'Não foi possível entender o valor "{bruto}" no campo "{rotulo}".')
    if numero is None:
        if obrigatorio:
            raise ErroFormulario(f'O campo "{rotulo}" é obrigatório.')
        return padrao
    if positivo and numero <= 0:
        raise ErroFormulario(f'O campo "{rotulo}" deve ser maior que zero.')
    if minimo is not None and numero < minimo:
        raise ErroFormulario(f'O campo "{rotulo}" não pode ser menor que {formato_milhar(minimo)}.')
    if maximo is not None and numero > maximo:
        raise ErroFormulario(f'O campo "{rotulo}" não pode ser maior que {formato_milhar(maximo)}.')
    return int(round(numero)) if inteiro else numero


def ler_data(campo, rotulo, obrigatorio=True):
    bruto = request.form.get(campo, "")
    try:
        valor = parse_date(bruto)
    except ValueError:
        raise ErroFormulario(f'Data inválida no campo "{rotulo}".')
    if valor is None and obrigatorio:
        raise ErroFormulario(f'O campo "{rotulo}" é obrigatório.')
    return valor


def data_do_arg(nome):
    """Data vinda da URL (filtros); ignora valores inválidos em vez de quebrar."""
    try:
        return parse_date(request.args.get(nome))
    except ValueError:
        return None


def buscar_veiculo_do_form():
    bruto = request.form.get("veiculo_id", "")
    veiculo = db.session.get(Veiculo, int(bruto)) if bruto.isdigit() else None
    if veiculo is None:
        raise ErroFormulario("Selecione um veículo válido.")
    return veiculo


def atualizar_odometro(veiculo, km):
    """Mantém o odômetro do veículo em dia com o maior km registrado."""
    if km and km > veiculo.quilometragem:
        veiculo.quilometragem = km


# Maior salto de km aceito entre o último registro conhecido e um novo registro.
# Serve para barrar erros de digitação (um zero a mais vira 10x o valor).
LIMITE_SALTO_KM = 30000


def maior_km_registrado(veiculo_id, ignorar_manutencao=None, ignorar_abastecimento=None):
    """Maior km entre manutenções e abastecimentos do veículo, podendo ignorar
    o próprio registro que está sendo editado."""
    consulta_m = db.session.query(func.max(Manutencao.quilometragem)).filter(
        Manutencao.veiculo_id == veiculo_id)
    if ignorar_manutencao:
        consulta_m = consulta_m.filter(Manutencao.id != ignorar_manutencao)
    consulta_a = db.session.query(func.max(Abastecimento.quilometragem)).filter(
        Abastecimento.veiculo_id == veiculo_id)
    if ignorar_abastecimento:
        consulta_a = consulta_a.filter(Abastecimento.id != ignorar_abastecimento)
    valores = [v for v in (consulta_m.scalar(), consulta_a.scalar()) if v is not None]
    return max(valores) if valores else None


def validar_salto_km(veiculo, km, ignorar_manutencao=None, ignorar_abastecimento=None):
    """Barra km muito acima do último registro conhecido (provável erro de digitação).
    No primeiro registro do veículo não há base confiável, então não valida."""
    base = maior_km_registrado(veiculo.id, ignorar_manutencao, ignorar_abastecimento)
    if base is not None and km > base + LIMITE_SALTO_KM:
        raise ErroFormulario(
            f"O km informado ({formato_milhar(km)}) está {formato_milhar(km - base)} km acima "
            f"do último registro deste veículo ({formato_milhar(base)}). "
            f"Confira se não há um dígito a mais. O sistema aceita no máximo "
            f"{formato_milhar(LIMITE_SALTO_KM)} km de diferença.")


def recalcular_odometro(veiculo):
    """Recalcula o odômetro a partir dos registros — permite que ele DESÇA
    quando um km digitado errado é corrigido ou excluído."""
    db.session.flush()  # garante que a alteração pendente entre na conta
    maior = maior_km_registrado(veiculo.id)
    if maior is not None:
        veiculo.quilometragem = maior


def veiculos_ordenados():
    return Veiculo.query.order_by(Veiculo.placa).all()


# ---------------- Painel ----------------

def alerta_por_data(hoje, venc, dias_aviso=30):
    """(nivel, texto) se a data está vencida ou perto de vencer; senão None.
    Texto neutro em gênero ('venceu'/'vence') para servir a CNH, seguro, etc."""
    if not venc:
        return None
    dias = (venc - hoje).days
    if dias < 0:
        return "danger", f"venceu há {-dias} dia(s)"
    if dias <= dias_aviso:
        return "warning", "vence hoje" if dias == 0 else f"vence em {dias} dia(s)"
    return None


def montar_alertas():
    """Reúne os avisos do painel: manutenções previstas, documentos dos
    veículos (licenciamento/seguro) e CNH dos motoristas. Veículos inativos
    não geram alertas; a manutenção usa só a mais recente de cada tipo."""
    hoje = date.today()
    alertas = []

    manutencoes = (
        Manutencao.query.options(joinedload(Manutencao.veiculo))
        .order_by(Manutencao.data, Manutencao.id).all()
    )
    ultimas = {}
    for m in manutencoes:
        ultimas[(m.veiculo_id, m.tipo.strip().lower())] = m
    for m in ultimas.values():
        if m.veiculo.status == "inativo":
            continue
        resultado = alerta_por_data(hoje, m.proxima_data)
        if resultado:
            alertas.append({"titulo": m.veiculo.placa, "tipo": m.tipo,
                            "nivel": resultado[0], "texto": resultado[1]})
        if m.proxima_km:
            faltam = m.proxima_km - m.veiculo.quilometragem
            if faltam <= 0:
                alertas.append({"titulo": m.veiculo.placa, "tipo": m.tipo, "nivel": "danger",
                                "texto": "quilometragem prevista atingida"})
            elif faltam <= 1000:
                alertas.append({"titulo": m.veiculo.placa, "tipo": m.tipo, "nivel": "warning",
                                "texto": f"faltam {formato_milhar(faltam)} km"})

    for v in Veiculo.query.filter(Veiculo.status != "inativo").all():
        for venc, rotulo in ((v.venc_licenciamento, "Licenciamento"), (v.venc_seguro, "Seguro")):
            resultado = alerta_por_data(hoje, venc)
            if resultado:
                alertas.append({"titulo": v.placa, "tipo": rotulo,
                                "nivel": resultado[0], "texto": resultado[1]})

    for mot in Motorista.query.all():
        resultado = alerta_por_data(hoje, mot.validade_cnh)
        if resultado:
            alertas.append({"titulo": mot.nome, "tipo": "CNH",
                            "nivel": resultado[0], "texto": resultado[1]})

    ordem = {"danger": 0, "warning": 1}
    alertas.sort(key=lambda a: ordem[a["nivel"]])
    return alertas


@app.route("/")
def index():
    hoje = date.today()
    inicio_mes = hoje.replace(day=1)
    inicio_mes_ant = (inicio_mes - timedelta(days=1)).replace(day=1)

    def soma_custos(desde, ate=None):
        manut = Manutencao.query.filter(Manutencao.data >= desde)
        comb = Abastecimento.query.filter(Abastecimento.data >= desde)
        if ate is not None:
            manut = manut.filter(Manutencao.data < ate)
            comb = comb.filter(Abastecimento.data < ate)
        m = manut.with_entities(func.coalesce(func.sum(Manutencao.custo), 0)).scalar()
        c = comb.with_entities(func.coalesce(func.sum(Abastecimento.valor_total), 0)).scalar()
        return m + c

    custo_mes = soma_custos(inicio_mes)
    custo_mes_ant = soma_custos(inicio_mes_ant, inicio_mes)
    variacao = round((custo_mes - custo_mes_ant) / custo_mes_ant * 100) if custo_mes_ant > 0 else None

    stats = {
        "total_veiculos": Veiculo.query.count(),
        "veiculos_ativos": Veiculo.query.filter_by(status="ativo").count(),
        "veiculos_manutencao": Veiculo.query.filter_by(status="manutencao").count(),
        "total_motoristas": Motorista.query.count(),
        "custo_mes": custo_mes,
        "custo_variacao": variacao,
    }
    ultimas_manutencoes = (
        Manutencao.query.options(joinedload(Manutencao.veiculo))
        .order_by(Manutencao.data.desc(), Manutencao.id.desc()).limit(5).all()
    )
    ultimos_abastecimentos = (
        Abastecimento.query.options(joinedload(Abastecimento.veiculo))
        .order_by(Abastecimento.data.desc(), Abastecimento.id.desc()).limit(5).all()
    )
    return render_template(
        "index.html", stats=stats, alertas=montar_alertas(), hoje=hoje,
        ultimas_manutencoes=ultimas_manutencoes, ultimos_abastecimentos=ultimos_abastecimentos,
    )


@app.errorhandler(404)
def pagina_nao_encontrada(e):
    return render_template("404.html"), 404


# ---------------- Veículos ----------------

@app.route("/veiculos")
def listar_veiculos():
    return render_template("veiculos.html", veiculos=veiculos_ordenados())


def preencher_veiculo(veiculo):
    veiculo.placa = exigir_texto("placa", "Placa", 10).upper()
    veiculo.marca = exigir_texto("marca", "Marca", 50)
    veiculo.modelo = exigir_texto("modelo", "Modelo", 50)
    veiculo.ano = ler_numero("ano", "Ano", inteiro=True, minimo=1950, maximo=2100)
    veiculo.quilometragem = ler_numero("quilometragem", "Quilometragem", inteiro=True, minimo=0)
    status = request.form.get("status", "ativo")
    if status not in ("ativo", "manutencao", "inativo"):
        raise ErroFormulario("Status inválido.")
    veiculo.status = status
    veiculo.venc_licenciamento = ler_data("venc_licenciamento", "Vencimento do licenciamento", obrigatorio=False)
    veiculo.venc_seguro = ler_data("venc_seguro", "Vencimento do seguro", obrigatorio=False)


@app.route("/veiculos/novo", methods=["GET", "POST"])
def novo_veiculo():
    if request.method == "POST":
        veiculo = Veiculo()
        try:
            preencher_veiculo(veiculo)
            db.session.add(veiculo)
            db.session.commit()
        except ErroFormulario as erro:
            db.session.rollback()
            flash(str(erro), "danger")
            return render_template("veiculo_form.html", veiculo=None)
        except IntegrityError:
            db.session.rollback()
            flash("Já existe um veículo cadastrado com essa placa.", "danger")
            return render_template("veiculo_form.html", veiculo=None)
        flash("Veículo cadastrado com sucesso!", "success")
        return redirect(url_for("listar_veiculos"))
    return render_template("veiculo_form.html", veiculo=None)


@app.route("/veiculos/<int:veiculo_id>/editar", methods=["GET", "POST"])
def editar_veiculo(veiculo_id):
    veiculo = Veiculo.query.get_or_404(veiculo_id)
    if request.method == "POST":
        try:
            preencher_veiculo(veiculo)
            db.session.commit()
        except ErroFormulario as erro:
            db.session.rollback()
            flash(str(erro), "danger")
            return render_template("veiculo_form.html", veiculo=veiculo)
        except IntegrityError:
            db.session.rollback()
            flash("Já existe um veículo cadastrado com essa placa.", "danger")
            return render_template("veiculo_form.html", veiculo=veiculo)
        flash("Veículo atualizado com sucesso!", "success")
        return redirect(url_for("listar_veiculos"))
    return render_template("veiculo_form.html", veiculo=veiculo)


@app.route("/veiculos/<int:veiculo_id>/excluir", methods=["POST"])
def excluir_veiculo(veiculo_id):
    veiculo = Veiculo.query.get_or_404(veiculo_id)
    # Veículo com histórico não pode ser excluído: apagaria de vez todas as
    # manutenções e abastecimentos dele. O caminho certo é marcar como inativo.
    registros = (Manutencao.query.filter_by(veiculo_id=veiculo.id).count()
                 + Abastecimento.query.filter_by(veiculo_id=veiculo.id).count())
    if registros > 0:
        flash(f"O veículo {veiculo.placa} tem {registros} registro(s) de manutenção/abastecimento. "
              "Para preservar o histórico, edite o veículo e mude o status para \"Inativo\" "
              "em vez de excluir.", "danger")
        return redirect(url_for("listar_veiculos"))
    db.session.delete(veiculo)
    db.session.commit()
    flash("Veículo removido.", "success")
    return redirect(url_for("listar_veiculos"))


# ---------------- Motoristas ----------------

@app.route("/motoristas")
def listar_motoristas():
    motoristas = (
        Motorista.query.options(joinedload(Motorista.veiculo))
        .order_by(Motorista.nome).all()
    )
    return render_template("motoristas.html", motoristas=motoristas)


def preencher_motorista(motorista):
    motorista.nome = exigir_texto("nome", "Nome completo", 100)
    motorista.cnh = exigir_texto("cnh", "CNH", 20)
    motorista.categoria_cnh = exigir_texto("categoria_cnh", "Categoria", 5).upper()
    motorista.telefone = request.form.get("telefone", "").strip()
    motorista.validade_cnh = ler_data("validade_cnh", "Validade da CNH", obrigatorio=False)
    bruto = request.form.get("veiculo_id") or None
    if bruto:
        if not bruto.isdigit() or db.session.get(Veiculo, int(bruto)) is None:
            raise ErroFormulario("Selecione um veículo válido.")
        motorista.veiculo_id = int(bruto)
    else:
        motorista.veiculo_id = None
    # CNH única (verificação em nível de aplicação para não exigir migração do banco)
    consulta = Motorista.query.filter(Motorista.cnh == motorista.cnh)
    if motorista.id:
        consulta = consulta.filter(Motorista.id != motorista.id)
    duplicado = consulta.first()
    if duplicado:
        raise ErroFormulario(f"Já existe um motorista cadastrado com a CNH {motorista.cnh} ({duplicado.nome}).")


@app.route("/motoristas/novo", methods=["GET", "POST"])
def novo_motorista():
    veiculos = veiculos_ordenados()
    if request.method == "POST":
        motorista = Motorista()
        try:
            preencher_motorista(motorista)
            db.session.add(motorista)
            db.session.commit()
        except ErroFormulario as erro:
            db.session.rollback()
            flash(str(erro), "danger")
            return render_template("motorista_form.html", motorista=None, veiculos=veiculos)
        flash("Motorista cadastrado com sucesso!", "success")
        return redirect(url_for("listar_motoristas"))
    return render_template("motorista_form.html", motorista=None, veiculos=veiculos)


@app.route("/motoristas/<int:motorista_id>/editar", methods=["GET", "POST"])
def editar_motorista(motorista_id):
    motorista = Motorista.query.get_or_404(motorista_id)
    veiculos = veiculos_ordenados()
    if request.method == "POST":
        try:
            preencher_motorista(motorista)
            db.session.commit()
        except ErroFormulario as erro:
            db.session.rollback()
            flash(str(erro), "danger")
            return render_template("motorista_form.html", motorista=motorista, veiculos=veiculos)
        flash("Motorista atualizado com sucesso!", "success")
        return redirect(url_for("listar_motoristas"))
    return render_template("motorista_form.html", motorista=motorista, veiculos=veiculos)


@app.route("/motoristas/<int:motorista_id>/excluir", methods=["POST"])
def excluir_motorista(motorista_id):
    motorista = Motorista.query.get_or_404(motorista_id)
    db.session.delete(motorista)
    db.session.commit()
    flash("Motorista removido.", "success")
    return redirect(url_for("listar_motoristas"))


# ---------------- Manutenções ----------------

@app.route("/manutencoes")
def listar_manutencoes():
    manutencoes = (
        Manutencao.query.options(joinedload(Manutencao.veiculo))
        .order_by(Manutencao.data.desc(), Manutencao.id.desc()).all()
    )
    return render_template("manutencoes.html", manutencoes=manutencoes)


def preencher_manutencao(manutencao):
    veiculo = buscar_veiculo_do_form()
    manutencao.veiculo_id = veiculo.id
    manutencao.tipo = exigir_texto("tipo", "Tipo de manutenção", 50)
    manutencao.data = ler_data("data", "Data")
    manutencao.quilometragem = ler_numero("quilometragem", "KM na data", inteiro=True, minimo=0)
    manutencao.custo = ler_numero("custo", "Custo", obrigatorio=False, minimo=0, padrao=0)
    manutencao.descricao = request.form.get("descricao", "").strip()
    manutencao.proxima_data = ler_data("proxima_data", "Próxima manutenção (data)", obrigatorio=False)
    manutencao.proxima_km = ler_numero("proxima_km", "Próxima manutenção (km)",
                                       obrigatorio=False, inteiro=True, minimo=0)
    validar_salto_km(veiculo, manutencao.quilometragem, ignorar_manutencao=manutencao.id)
    if manutencao.id:
        recalcular_odometro(veiculo)  # edição pode corrigir km para baixo
    else:
        atualizar_odometro(veiculo, manutencao.quilometragem)


@app.route("/manutencoes/nova", methods=["GET", "POST"])
def nova_manutencao():
    veiculos = veiculos_ordenados()
    if request.method == "POST":
        manutencao = Manutencao()
        try:
            preencher_manutencao(manutencao)
            db.session.add(manutencao)
            db.session.commit()
        except ErroFormulario as erro:
            db.session.rollback()
            flash(str(erro), "danger")
            return render_template("manutencao_form.html", manutencao=None, veiculos=veiculos,
                                   today=date.today().isoformat())
        flash("Manutenção registrada com sucesso!", "success")
        return redirect(url_for("listar_manutencoes"))
    return render_template("manutencao_form.html", manutencao=None, veiculos=veiculos,
                           today=date.today().isoformat())


@app.route("/manutencoes/<int:manutencao_id>/editar", methods=["GET", "POST"])
def editar_manutencao(manutencao_id):
    manutencao = Manutencao.query.get_or_404(manutencao_id)
    veiculos = veiculos_ordenados()
    if request.method == "POST":
        try:
            preencher_manutencao(manutencao)
            db.session.commit()
        except ErroFormulario as erro:
            db.session.rollback()
            flash(str(erro), "danger")
            return render_template("manutencao_form.html", manutencao=manutencao, veiculos=veiculos,
                                   today=date.today().isoformat())
        flash("Manutenção atualizada com sucesso!", "success")
        return redirect(url_for("listar_manutencoes"))
    return render_template("manutencao_form.html", manutencao=manutencao, veiculos=veiculos,
                           today=date.today().isoformat())


@app.route("/manutencoes/<int:manutencao_id>/excluir", methods=["POST"])
def excluir_manutencao(manutencao_id):
    manutencao = Manutencao.query.get_or_404(manutencao_id)
    veiculo = manutencao.veiculo
    db.session.delete(manutencao)
    recalcular_odometro(veiculo)  # o odômetro pode descer se o km excluído era o maior
    db.session.commit()
    flash("Registro de manutenção removido.", "success")
    return redirect(url_for("listar_manutencoes"))


# ---------------- Relatórios ----------------

MESES_ABREV = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
               "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def meses_atras(referencia, quantidade):
    ano, mes = referencia.year, referencia.month - quantidade
    while mes <= 0:
        mes += 12
        ano -= 1
    return date(ano, mes, 1)


def escala_do_grafico(maximo):
    """Teto 'redondo' e 5 marcações para o eixo do gráfico."""
    if maximo <= 0:
        return 100, [0, 25, 50, 75, 100]
    bruto = maximo / 4
    magnitude = 10 ** math.floor(math.log10(bruto))
    passo = magnitude
    for multiplo in (1, 2, 2.5, 5, 10):
        passo = multiplo * magnitude
        if passo * 4 >= maximo:
            break
    return passo * 4, [passo * i for i in range(5)]


def dados_relatorio(inicio, fim):
    """Agrega custos por veículo e por mês dentro do período."""
    abastecimentos = (
        Abastecimento.query.options(joinedload(Abastecimento.veiculo))
        .filter(Abastecimento.data >= inicio, Abastecimento.data <= fim).all()
    )
    manutencoes = (
        Manutencao.query.options(joinedload(Manutencao.veiculo))
        .filter(Manutencao.data >= inicio, Manutencao.data <= fim).all()
    )

    por_veiculo = {}

    def entrada(veiculo):
        return por_veiculo.setdefault(veiculo.id, {
            "veiculo": veiculo, "litros": 0.0, "custo_combustivel": 0.0,
            "custo_manutencao": 0.0, "qtd_abastecimentos": 0, "qtd_manutencoes": 0,
            "abastecimentos": [],
        })

    for a in abastecimentos:
        linha = entrada(a.veiculo)
        linha["litros"] += a.litros
        linha["custo_combustivel"] += a.valor_total
        linha["qtd_abastecimentos"] += 1
        linha["abastecimentos"].append(a)
    for m in manutencoes:
        linha = entrada(m.veiculo)
        linha["custo_manutencao"] += m.custo
        linha["qtd_manutencoes"] += 1

    linhas = []
    for linha in por_veiculo.values():
        registros = sorted(linha.pop("abastecimentos"), key=lambda a: a.quilometragem)
        km_rodados = consumo = custo_km = None
        if len(registros) >= 2:
            km_rodados = registros[-1].quilometragem - registros[0].quilometragem
            # Consumo medido só entre tanques cheios (parciais acumulam litros).
            km_medidos = litros_medidos = 0.0
            km_cheio, litros_acum = None, 0.0
            for a in registros:
                litros_acum += a.litros
                if eh_tanque_cheio(a):
                    if km_cheio is not None and a.quilometragem > km_cheio and litros_acum > 0:
                        km_medidos += a.quilometragem - km_cheio
                        litros_medidos += litros_acum
                    km_cheio, litros_acum = a.quilometragem, 0.0
            if km_medidos > 0 and litros_medidos > 0:
                consumo = km_medidos / litros_medidos
        linha["custo_total"] = linha["custo_combustivel"] + linha["custo_manutencao"]
        if km_rodados and linha["custo_total"]:
            custo_km = linha["custo_total"] / km_rodados
        linha.update(km_rodados=km_rodados, consumo=consumo, custo_km=custo_km)
        linhas.append(linha)
    linhas.sort(key=lambda item: -item["custo_total"])

    meses = []
    atual = inicio.replace(day=1)
    while atual <= fim:
        meses.append({"ref": atual, "label": f"{MESES_ABREV[atual.month - 1]}/{atual.year % 100:02d}",
                      "combustivel": 0.0, "manutencao": 0.0})
        atual = (atual + timedelta(days=32)).replace(day=1)
    indice = {(m["ref"].year, m["ref"].month): m for m in meses}
    for a in abastecimentos:
        mes = indice.get((a.data.year, a.data.month))
        if mes:
            mes["combustivel"] += a.valor_total
    for m in manutencoes:
        mes = indice.get((m.data.year, m.data.month))
        if mes:
            mes["manutencao"] += m.custo
    for mes in meses:
        mes["total"] = mes["combustivel"] + mes["manutencao"]

    totais = {
        "custo_total": sum(l["custo_total"] for l in linhas),
        "custo_combustivel": sum(l["custo_combustivel"] for l in linhas),
        "custo_manutencao": sum(l["custo_manutencao"] for l in linhas),
        "litros": sum(l["litros"] for l in linhas),
        "km_rodados": sum(l["km_rodados"] or 0 for l in linhas),
        "qtd_manutencoes": sum(l["qtd_manutencoes"] for l in linhas),
    }
    return linhas, meses, totais


def periodo_do_filtro():
    hoje = date.today()
    fim = data_do_arg("fim") or hoje
    inicio = data_do_arg("inicio") or meses_atras(hoje, 5)
    if inicio > fim:
        inicio, fim = fim, inicio
    return inicio, fim


@app.route("/relatorios")
def relatorios():
    inicio, fim = periodo_do_filtro()
    linhas, meses, totais = dados_relatorio(inicio, fim)
    maximo = max((m["total"] for m in meses), default=0)
    teto, marcacoes = escala_do_grafico(maximo)
    hoje = date.today()
    atalhos = [
        ("Este mês", hoje.replace(day=1), hoje),
        ("Últimos 6 meses", meses_atras(hoje, 5), hoje),
        ("Este ano", hoje.replace(month=1, day=1), hoje),
    ]
    return render_template(
        "relatorios.html", inicio=inicio, fim=fim, linhas=linhas, meses=meses,
        totais=totais, teto=teto, marcacoes=marcacoes, atalhos=atalhos,
        tem_dados=bool(linhas),
    )


def celula_segura(texto):
    """Evita que planilhas interpretem o conteúdo como fórmula (CSV injection)."""
    return "'" + texto if texto and texto[0] in "=+-@" else texto


@app.route("/relatorios/exportar")
def exportar_relatorio():
    inicio, fim = periodo_do_filtro()
    linhas, meses, totais = dados_relatorio(inicio, fim)

    def num(valor, casas=2):
        return f"{valor:.{casas}f}".replace(".", ",") if valor is not None else ""

    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    escritor.writerow([f"Relatório da frota — {inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}"])
    escritor.writerow([])
    escritor.writerow(["Resumo por veículo"])
    escritor.writerow(["Placa", "Veículo", "Km rodados", "Litros", "Custo combustível (R$)",
                       "Custo manutenção (R$)", "Custo total (R$)", "Consumo (km/L)", "Custo por km (R$)"])
    for l in linhas:
        v = l["veiculo"]
        escritor.writerow([celula_segura(v.placa), celula_segura(f"{v.marca} {v.modelo}"),
                           l["km_rodados"] if l["km_rodados"] is not None else "",
                           num(l["litros"], 1), num(l["custo_combustivel"]),
                           num(l["custo_manutencao"]), num(l["custo_total"]),
                           num(l["consumo"], 1) if l["consumo"] else "",
                           num(l["custo_km"]) if l["custo_km"] else ""])
    escritor.writerow(["TOTAL", "", totais["km_rodados"], num(totais["litros"], 1),
                       num(totais["custo_combustivel"]), num(totais["custo_manutencao"]),
                       num(totais["custo_total"]), "", ""])
    escritor.writerow([])
    escritor.writerow(["Evolução mensal"])
    escritor.writerow(["Mês", "Combustível (R$)", "Manutenção (R$)", "Total (R$)"])
    for m in meses:
        escritor.writerow([m["label"], num(m["combustivel"]), num(m["manutencao"]), num(m["total"])])

    conteudo = "﻿" + buffer.getvalue()  # BOM para o Excel abrir acentos corretamente
    nome = f"relatorio_frota_{inicio.isoformat()}_a_{fim.isoformat()}.csv"
    return Response(conteudo, mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={nome}"})


# ---------------- Backup ----------------

def copia_segura_do_banco():
    """Retorna os bytes de uma cópia consistente do frota.db (segura mesmo
    com o site em uso), ou None se o banco não for SQLite."""
    import sqlite3
    import tempfile
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if not uri.startswith("sqlite:///"):
        return None
    caminho = uri.replace("sqlite:///", "", 1)
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as arquivo:
        temporario = arquivo.name
    origem = sqlite3.connect(caminho)
    destino = sqlite3.connect(temporario)
    with destino:
        origem.backup(destino)  # cópia consistente, sem risco de pegar escrita no meio
    origem.close()
    destino.close()
    with open(temporario, "rb") as arquivo:
        dados = arquivo.read()
    os.unlink(temporario)
    return dados


@app.route("/backup")
def baixar_backup():
    """Baixa uma cópia segura do banco (frota.db), mesmo com o sistema em uso.
    Protegida por login como qualquer outra página."""
    dados = copia_segura_do_banco()
    if dados is None:
        flash("O backup por download só está disponível com banco SQLite.", "danger")
        return redirect(url_for("index"))
    nome = f"frota-{date.today().isoformat()}.db"
    return Response(dados, mimetype="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename={nome}"})


def ler_chave_backup():
    """Lê a chave secreta do backup automático do arquivo chave_backup.txt
    (na mesma pasta do app). Se o arquivo não existir, a rota fica desligada."""
    caminho = os.path.join(os.path.abspath(os.path.dirname(__file__)), "chave_backup.txt")
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            chave = arquivo.read().strip()
        return chave if len(chave) >= 32 else None  # chave curta = insegura = desligado
    except OSError:
        return None


@app.route("/backup-automatico")
def backup_automatico():
    """Usada pelo robô do GitHub Actions (1x por dia). Sem login: a proteção é
    uma chave secreta longa que só existe no servidor e no cofre do GitHub."""
    import hmac
    chave_correta = ler_chave_backup()
    chave_recebida = request.args.get("chave", "")
    # compare_digest evita ataque de medição de tempo na comparação
    if not chave_correta or not hmac.compare_digest(chave_recebida, chave_correta):
        abort(404)  # não revela que a rota existe
    dados = copia_segura_do_banco()
    if dados is None:
        abort(404)
    return Response(dados, mimetype="application/octet-stream")


# ---------------- Abastecimentos ----------------

def eh_tanque_cheio(abastecimento):
    """Registros antigos (antes do campo existir) contam como tanque cheio."""
    return abastecimento.tanque_cheio is None or bool(abastecimento.tanque_cheio)


def calcular_consumos(abastecimentos):
    """Km/L medido de tanque cheio a tanque cheio. Abastecimentos parciais
    apenas acumulam litros e não geram medição própria — só assim o número
    reflete o consumo real do veículo."""
    estado = {}  # por veículo: km do último tanque cheio + litros acumulados desde então
    for a in sorted(abastecimentos, key=lambda x: (x.veiculo_id, x.quilometragem)):
        e = estado.setdefault(a.veiculo_id, {"km_cheio": None, "litros": 0.0})
        a.consumo = None
        e["litros"] += a.litros
        if eh_tanque_cheio(a):
            if (e["km_cheio"] is not None and a.quilometragem > e["km_cheio"]
                    and e["litros"] > 0):
                a.consumo = (a.quilometragem - e["km_cheio"]) / e["litros"]
            e["km_cheio"] = a.quilometragem
            e["litros"] = 0.0
    return abastecimentos


@app.route("/abastecimentos")
def listar_abastecimentos():
    abastecimentos = (
        Abastecimento.query
        .options(joinedload(Abastecimento.veiculo), joinedload(Abastecimento.motorista))
        .order_by(Abastecimento.data.desc(), Abastecimento.id.desc()).all()
    )
    calcular_consumos(abastecimentos)
    return render_template("abastecimentos.html", abastecimentos=abastecimentos)


COMBUSTIVEIS = ("gasolina", "etanol", "diesel", "gnv")


def preencher_abastecimento(abastecimento):
    veiculo = buscar_veiculo_do_form()
    abastecimento.veiculo_id = veiculo.id
    bruto = request.form.get("motorista_id") or None
    if bruto:
        if not bruto.isdigit() or db.session.get(Motorista, int(bruto)) is None:
            raise ErroFormulario("Selecione um motorista válido.")
        abastecimento.motorista_id = int(bruto)
    else:
        abastecimento.motorista_id = None
    abastecimento.data = ler_data("data", "Data")
    combustivel = request.form.get("tipo_combustivel", "")
    if combustivel not in COMBUSTIVEIS:
        raise ErroFormulario("Combustível inválido.")
    abastecimento.tipo_combustivel = combustivel
    abastecimento.litros = ler_numero("litros", "Litros", positivo=True)
    abastecimento.valor_total = ler_numero("valor_total", "Valor total", minimo=0)
    abastecimento.quilometragem = ler_numero("quilometragem", "KM na data", inteiro=True, minimo=0)
    abastecimento.tanque_cheio = request.form.get("tanque_cheio") == "1"
    validar_salto_km(veiculo, abastecimento.quilometragem, ignorar_abastecimento=abastecimento.id)
    if abastecimento.id:
        recalcular_odometro(veiculo)  # edição pode corrigir km para baixo
    else:
        atualizar_odometro(veiculo, abastecimento.quilometragem)


@app.route("/abastecimentos/novo", methods=["GET", "POST"])
def novo_abastecimento():
    veiculos = veiculos_ordenados()
    motoristas = Motorista.query.order_by(Motorista.nome).all()
    if request.method == "POST":
        abastecimento = Abastecimento()
        try:
            preencher_abastecimento(abastecimento)
            db.session.add(abastecimento)
            db.session.commit()
        except ErroFormulario as erro:
            db.session.rollback()
            flash(str(erro), "danger")
            return render_template("abastecimento_form.html", abastecimento=None, veiculos=veiculos,
                                   motoristas=motoristas, today=date.today().isoformat())
        flash("Abastecimento registrado com sucesso!", "success")
        return redirect(url_for("listar_abastecimentos"))
    return render_template("abastecimento_form.html", abastecimento=None, veiculos=veiculos,
                           motoristas=motoristas, today=date.today().isoformat())


@app.route("/abastecimentos/<int:abastecimento_id>/editar", methods=["GET", "POST"])
def editar_abastecimento(abastecimento_id):
    abastecimento = Abastecimento.query.get_or_404(abastecimento_id)
    veiculos = veiculos_ordenados()
    motoristas = Motorista.query.order_by(Motorista.nome).all()
    if request.method == "POST":
        try:
            preencher_abastecimento(abastecimento)
            db.session.commit()
        except ErroFormulario as erro:
            db.session.rollback()
            flash(str(erro), "danger")
            return render_template("abastecimento_form.html", abastecimento=abastecimento,
                                   veiculos=veiculos, motoristas=motoristas,
                                   today=date.today().isoformat())
        flash("Abastecimento atualizado com sucesso!", "success")
        return redirect(url_for("listar_abastecimentos"))
    return render_template("abastecimento_form.html", abastecimento=abastecimento, veiculos=veiculos,
                           motoristas=motoristas, today=date.today().isoformat())


@app.route("/abastecimentos/<int:abastecimento_id>/excluir", methods=["POST"])
def excluir_abastecimento(abastecimento_id):
    abastecimento = Abastecimento.query.get_or_404(abastecimento_id)
    veiculo = abastecimento.veiculo
    db.session.delete(abastecimento)
    recalcular_odometro(veiculo)  # o odômetro pode descer se o km excluído era o maior
    db.session.commit()
    flash("Abastecimento removido.", "success")
    return redirect(url_for("listar_abastecimentos"))


if __name__ == "__main__":
    # Em produção, defina FLASK_DEBUG=0 e use um servidor WSGI (ex.: waitress).
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1")
