import csv
import io
import math
import os
import re
import secrets
import time
from datetime import date, datetime, timedelta

from flask import (Flask, Response, flash, redirect, render_template, request,
                   session, url_for)
from sqlalchemy import func
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

db.init_app(app)

with app.app_context():
    db.create_all()


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
ENDPOINTS_PUBLICOS = {"login", "logout", "configurar", "service_worker", "static"}


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


def veiculos_ordenados():
    return Veiculo.query.order_by(Veiculo.placa).all()


# ---------------- Painel ----------------

def montar_alertas():
    """Alertas gerados apenas pela manutenção MAIS RECENTE de cada tipo por veículo.

    Assim, ao registrar uma nova manutenção do mesmo tipo, o alerta antigo
    se resolve sozinho. Veículos inativos não geram alertas.
    """
    hoje = date.today()
    manutencoes = (
        Manutencao.query.options(joinedload(Manutencao.veiculo))
        .order_by(Manutencao.data, Manutencao.id).all()
    )
    ultimas = {}
    for m in manutencoes:
        ultimas[(m.veiculo_id, m.tipo.strip().lower())] = m

    alertas = []
    for m in ultimas.values():
        if m.veiculo.status == "inativo":
            continue
        if m.proxima_data:
            dias = (m.proxima_data - hoje).days
            if dias < 0:
                alertas.append({"veiculo": m.veiculo, "tipo": m.tipo, "nivel": "danger",
                                "texto": f"vencida há {-dias} dia(s)"})
            elif dias <= 30:
                alertas.append({"veiculo": m.veiculo, "tipo": m.tipo, "nivel": "warning",
                                "texto": f"vence em {dias} dia(s)"})
        if m.proxima_km:
            faltam = m.proxima_km - m.veiculo.quilometragem
            if faltam <= 0:
                alertas.append({"veiculo": m.veiculo, "tipo": m.tipo, "nivel": "danger",
                                "texto": "quilometragem prevista atingida"})
            elif faltam <= 1000:
                alertas.append({"veiculo": m.veiculo, "tipo": m.tipo, "nivel": "warning",
                                "texto": f"faltam {formato_milhar(faltam)} km"})
    ordem = {"danger": 0, "warning": 1}
    alertas.sort(key=lambda a: ordem[a["nivel"]])
    return alertas


@app.route("/")
def index():
    hoje = date.today()
    inicio_mes = hoje.replace(day=1)
    custo_manutencao = (
        db.session.query(func.coalesce(func.sum(Manutencao.custo), 0))
        .filter(Manutencao.data >= inicio_mes).scalar()
    )
    custo_combustivel = (
        db.session.query(func.coalesce(func.sum(Abastecimento.valor_total), 0))
        .filter(Abastecimento.data >= inicio_mes).scalar()
    )
    stats = {
        "total_veiculos": Veiculo.query.count(),
        "veiculos_ativos": Veiculo.query.filter_by(status="ativo").count(),
        "veiculos_manutencao": Veiculo.query.filter_by(status="manutencao").count(),
        "total_motoristas": Motorista.query.count(),
        "custo_mes": custo_manutencao + custo_combustivel,
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
    db.session.delete(manutencao)
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
            combustivel_usado = sum(a.litros for a in registros[1:])
            if km_rodados > 0 and combustivel_usado > 0:
                consumo = km_rodados / combustivel_usado
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


# ---------------- Abastecimentos ----------------

def calcular_consumos(abastecimentos):
    """Km/L de cada abastecimento com base no anterior do mesmo veículo."""
    anterior_por_veiculo = {}
    for a in sorted(abastecimentos, key=lambda x: (x.veiculo_id, x.quilometragem)):
        anterior = anterior_por_veiculo.get(a.veiculo_id)
        if anterior and a.quilometragem > anterior.quilometragem and a.litros > 0:
            a.consumo = (a.quilometragem - anterior.quilometragem) / a.litros
        else:
            a.consumo = None
        anterior_por_veiculo[a.veiculo_id] = a
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
    db.session.delete(abastecimento)
    db.session.commit()
    flash("Abastecimento removido.", "success")
    return redirect(url_for("listar_abastecimentos"))


if __name__ == "__main__":
    # Em produção, defina FLASK_DEBUG=0 e use um servidor WSGI (ex.: waitress).
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1")
