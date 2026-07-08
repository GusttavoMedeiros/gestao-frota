import csv
import io
import math
import re
from datetime import date, datetime, timedelta

from flask import Flask, Response, flash, redirect, render_template, request, url_for
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from models import Abastecimento, Manutencao, Motorista, Veiculo, db

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///frota.db"
app.config["SECRET_KEY"] = "troque-esta-chave-antes-de-usar-em-producao"
db.init_app(app)

with app.app_context():
    db.create_all()


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


def parse_int(value, default=None):
    numero = parse_num(value)
    return int(round(numero)) if numero is not None else default


def parse_float(value, default=None):
    numero = parse_num(value)
    return numero if numero is not None else default


@app.errorhandler(ValueError)
def erro_de_valor(e):
    flash("Não foi possível entender um dos números informados. Verifique os campos e tente novamente.", "danger")
    return redirect(request.referrer or url_for("index"))


# ---------------- Painel ----------------

def montar_alertas():
    """Manutenções previstas vencidas ou próximas de vencer (por data ou km)."""
    hoje = date.today()
    alertas = []
    previstas = (
        Manutencao.query.options(joinedload(Manutencao.veiculo))
        .filter((Manutencao.proxima_data.isnot(None)) | (Manutencao.proxima_km.isnot(None)))
        .all()
    )
    for m in previstas:
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


# ---------------- Veículos ----------------

@app.route("/veiculos")
def listar_veiculos():
    veiculos = Veiculo.query.order_by(Veiculo.placa).all()
    return render_template("veiculos.html", veiculos=veiculos)


def preencher_veiculo(veiculo):
    veiculo.placa = request.form["placa"].strip().upper()
    veiculo.marca = request.form["marca"].strip()
    veiculo.modelo = request.form["modelo"].strip()
    veiculo.ano = parse_int(request.form["ano"])
    veiculo.quilometragem = parse_int(request.form["quilometragem"])
    veiculo.status = request.form["status"]


@app.route("/veiculos/novo", methods=["GET", "POST"])
def novo_veiculo():
    if request.method == "POST":
        veiculo = Veiculo()
        preencher_veiculo(veiculo)
        db.session.add(veiculo)
        try:
            db.session.commit()
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
        preencher_veiculo(veiculo)
        try:
            db.session.commit()
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
    veiculo_id = request.form.get("veiculo_id") or None
    motorista.nome = request.form["nome"].strip()
    motorista.cnh = request.form["cnh"].strip()
    motorista.categoria_cnh = request.form["categoria_cnh"].strip().upper()
    motorista.telefone = request.form.get("telefone", "").strip()
    motorista.veiculo_id = int(veiculo_id) if veiculo_id else None


@app.route("/motoristas/novo", methods=["GET", "POST"])
def novo_motorista():
    veiculos = Veiculo.query.order_by(Veiculo.placa).all()
    if request.method == "POST":
        motorista = Motorista()
        preencher_motorista(motorista)
        db.session.add(motorista)
        db.session.commit()
        flash("Motorista cadastrado com sucesso!", "success")
        return redirect(url_for("listar_motoristas"))
    return render_template("motorista_form.html", motorista=None, veiculos=veiculos)


@app.route("/motoristas/<int:motorista_id>/editar", methods=["GET", "POST"])
def editar_motorista(motorista_id):
    motorista = Motorista.query.get_or_404(motorista_id)
    veiculos = Veiculo.query.order_by(Veiculo.placa).all()
    if request.method == "POST":
        preencher_motorista(motorista)
        db.session.commit()
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
    manutencao.veiculo_id = int(request.form["veiculo_id"])
    manutencao.tipo = request.form["tipo"].strip()
    manutencao.data = parse_date(request.form["data"])
    manutencao.quilometragem = parse_int(request.form["quilometragem"])
    manutencao.custo = parse_float(request.form.get("custo"), 0)
    manutencao.descricao = request.form.get("descricao", "").strip()
    manutencao.proxima_data = parse_date(request.form.get("proxima_data"))
    manutencao.proxima_km = parse_int(request.form.get("proxima_km"))


@app.route("/manutencoes/nova", methods=["GET", "POST"])
def nova_manutencao():
    veiculos = Veiculo.query.order_by(Veiculo.placa).all()
    if request.method == "POST":
        manutencao = Manutencao()
        preencher_manutencao(manutencao)
        db.session.add(manutencao)
        db.session.commit()
        flash("Manutenção registrada com sucesso!", "success")
        return redirect(url_for("listar_manutencoes"))
    return render_template("manutencao_form.html", manutencao=None, veiculos=veiculos,
                           today=date.today().isoformat())


@app.route("/manutencoes/<int:manutencao_id>/editar", methods=["GET", "POST"])
def editar_manutencao(manutencao_id):
    manutencao = Manutencao.query.get_or_404(manutencao_id)
    veiculos = Veiculo.query.order_by(Veiculo.placa).all()
    if request.method == "POST":
        preencher_manutencao(manutencao)
        db.session.commit()
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
    fim = parse_date(request.args.get("fim")) or hoje
    inicio = parse_date(request.args.get("inicio")) or meses_atras(hoje, 5)
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
        escritor.writerow([v.placa, f"{v.marca} {v.modelo}",
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


def preencher_abastecimento(abastecimento):
    motorista_id = request.form.get("motorista_id") or None
    abastecimento.veiculo_id = int(request.form["veiculo_id"])
    abastecimento.motorista_id = int(motorista_id) if motorista_id else None
    abastecimento.data = parse_date(request.form["data"])
    abastecimento.tipo_combustivel = request.form["tipo_combustivel"]
    abastecimento.litros = parse_float(request.form["litros"])
    abastecimento.valor_total = parse_float(request.form["valor_total"])
    abastecimento.quilometragem = parse_int(request.form["quilometragem"])


@app.route("/abastecimentos/novo", methods=["GET", "POST"])
def novo_abastecimento():
    veiculos = Veiculo.query.order_by(Veiculo.placa).all()
    motoristas = Motorista.query.order_by(Motorista.nome).all()
    if request.method == "POST":
        abastecimento = Abastecimento()
        preencher_abastecimento(abastecimento)
        db.session.add(abastecimento)
        db.session.commit()
        flash("Abastecimento registrado com sucesso!", "success")
        return redirect(url_for("listar_abastecimentos"))
    return render_template("abastecimento_form.html", abastecimento=None, veiculos=veiculos,
                           motoristas=motoristas, today=date.today().isoformat())


@app.route("/abastecimentos/<int:abastecimento_id>/editar", methods=["GET", "POST"])
def editar_abastecimento(abastecimento_id):
    abastecimento = Abastecimento.query.get_or_404(abastecimento_id)
    veiculos = Veiculo.query.order_by(Veiculo.placa).all()
    motoristas = Motorista.query.order_by(Motorista.nome).all()
    if request.method == "POST":
        preencher_abastecimento(abastecimento)
        db.session.commit()
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
    app.run(debug=True)
