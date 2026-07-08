from datetime import date, datetime

from flask import Flask, flash, redirect, render_template, request, url_for

from models import Abastecimento, Manutencao, Motorista, Veiculo, db

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///frota.db"
app.config["SECRET_KEY"] = "troque-esta-chave-antes-de-usar-em-producao"
db.init_app(app)

with app.app_context():
    db.create_all()


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date() if value else None


@app.route("/")
def index():
    stats = {
        "total_veiculos": Veiculo.query.count(),
        "total_motoristas": Motorista.query.count(),
        "veiculos_manutencao": Veiculo.query.filter_by(status="manutencao").count(),
        "veiculos_ativos": Veiculo.query.filter_by(status="ativo").count(),
    }
    return render_template("index.html", stats=stats)


# ---------------- Veiculos ----------------

@app.route("/veiculos")
def listar_veiculos():
    veiculos = Veiculo.query.order_by(Veiculo.placa).all()
    return render_template("veiculos.html", veiculos=veiculos)


@app.route("/veiculos/novo", methods=["GET", "POST"])
def novo_veiculo():
    if request.method == "POST":
        veiculo = Veiculo(
            placa=request.form["placa"].strip().upper(),
            marca=request.form["marca"].strip(),
            modelo=request.form["modelo"].strip(),
            ano=int(request.form["ano"]),
            quilometragem=int(request.form["quilometragem"]),
            status=request.form["status"],
        )
        db.session.add(veiculo)
        db.session.commit()
        flash("Veículo cadastrado com sucesso!", "success")
        return redirect(url_for("listar_veiculos"))
    return render_template("veiculo_form.html", veiculo=None)


@app.route("/veiculos/<int:veiculo_id>/editar", methods=["GET", "POST"])
def editar_veiculo(veiculo_id):
    veiculo = Veiculo.query.get_or_404(veiculo_id)
    if request.method == "POST":
        veiculo.placa = request.form["placa"].strip().upper()
        veiculo.marca = request.form["marca"].strip()
        veiculo.modelo = request.form["modelo"].strip()
        veiculo.ano = int(request.form["ano"])
        veiculo.quilometragem = int(request.form["quilometragem"])
        veiculo.status = request.form["status"]
        db.session.commit()
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
    motoristas = Motorista.query.order_by(Motorista.nome).all()
    return render_template("motoristas.html", motoristas=motoristas)


@app.route("/motoristas/novo", methods=["GET", "POST"])
def novo_motorista():
    veiculos = Veiculo.query.order_by(Veiculo.placa).all()
    if request.method == "POST":
        veiculo_id = request.form.get("veiculo_id") or None
        motorista = Motorista(
            nome=request.form["nome"].strip(),
            cnh=request.form["cnh"].strip(),
            categoria_cnh=request.form["categoria_cnh"].strip().upper(),
            telefone=request.form.get("telefone", "").strip(),
            veiculo_id=int(veiculo_id) if veiculo_id else None,
        )
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
        veiculo_id = request.form.get("veiculo_id") or None
        motorista.nome = request.form["nome"].strip()
        motorista.cnh = request.form["cnh"].strip()
        motorista.categoria_cnh = request.form["categoria_cnh"].strip().upper()
        motorista.telefone = request.form.get("telefone", "").strip()
        motorista.veiculo_id = int(veiculo_id) if veiculo_id else None
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


# ---------------- Manutencoes ----------------

@app.route("/manutencoes")
def listar_manutencoes():
    manutencoes = Manutencao.query.order_by(Manutencao.data.desc()).all()
    return render_template("manutencoes.html", manutencoes=manutencoes)


@app.route("/manutencoes/nova", methods=["GET", "POST"])
def nova_manutencao():
    veiculos = Veiculo.query.order_by(Veiculo.placa).all()
    if request.method == "POST":
        manutencao = Manutencao(
            veiculo_id=int(request.form["veiculo_id"]),
            tipo=request.form["tipo"].strip(),
            data=parse_date(request.form["data"]),
            quilometragem=int(request.form["quilometragem"]),
            custo=float(request.form["custo"] or 0),
            descricao=request.form.get("descricao", "").strip(),
            proxima_data=parse_date(request.form.get("proxima_data")),
            proxima_km=int(request.form["proxima_km"]) if request.form.get("proxima_km") else None,
        )
        db.session.add(manutencao)
        db.session.commit()
        flash("Manutenção registrada com sucesso!", "success")
        return redirect(url_for("listar_manutencoes"))
    return render_template("manutencao_form.html", manutencao=None, veiculos=veiculos, today=date.today().isoformat())


@app.route("/manutencoes/<int:manutencao_id>/excluir", methods=["POST"])
def excluir_manutencao(manutencao_id):
    manutencao = Manutencao.query.get_or_404(manutencao_id)
    db.session.delete(manutencao)
    db.session.commit()
    flash("Registro de manutenção removido.", "success")
    return redirect(url_for("listar_manutencoes"))


# ---------------- Abastecimentos ----------------

@app.route("/abastecimentos")
def listar_abastecimentos():
    abastecimentos = Abastecimento.query.order_by(Abastecimento.data.desc()).all()
    return render_template("abastecimentos.html", abastecimentos=abastecimentos)


@app.route("/abastecimentos/novo", methods=["GET", "POST"])
def novo_abastecimento():
    veiculos = Veiculo.query.order_by(Veiculo.placa).all()
    motoristas = Motorista.query.order_by(Motorista.nome).all()
    if request.method == "POST":
        motorista_id = request.form.get("motorista_id") or None
        abastecimento = Abastecimento(
            veiculo_id=int(request.form["veiculo_id"]),
            motorista_id=int(motorista_id) if motorista_id else None,
            data=parse_date(request.form["data"]),
            tipo_combustivel=request.form["tipo_combustivel"],
            litros=float(request.form["litros"]),
            valor_total=float(request.form["valor_total"]),
            quilometragem=int(request.form["quilometragem"]),
        )
        db.session.add(abastecimento)
        db.session.commit()
        flash("Abastecimento registrado com sucesso!", "success")
        return redirect(url_for("listar_abastecimentos"))
    return render_template(
        "abastecimento_form.html", veiculos=veiculos, motoristas=motoristas, today=date.today().isoformat()
    )


@app.route("/abastecimentos/<int:abastecimento_id>/excluir", methods=["POST"])
def excluir_abastecimento(abastecimento_id):
    abastecimento = Abastecimento.query.get_or_404(abastecimento_id)
    db.session.delete(abastecimento)
    db.session.commit()
    flash("Abastecimento removido.", "success")
    return redirect(url_for("listar_abastecimentos"))


if __name__ == "__main__":
    app.run(debug=True)
