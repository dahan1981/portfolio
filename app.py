import os
import requests
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-troque-em-producao')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

ABACATEPAY_API_KEY = os.environ.get('ABACATEPAY_API_KEY', '')
ABACATEPAY_BASE_URL = 'https://api.abacatepay.com/v1'

# ── SENHA ADMIN ──
ADMIN_PASSWORD = bcrypt.generate_password_hash('Dahan1005@').decode('utf-8')

# ══════════════════════════════════════
# MODELOS
# ══════════════════════════════════════

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(200), nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    orcamentos = db.relationship('Orcamento', backref='cliente', lazy=True)

    def set_senha(self, senha):
        self.senha_hash = bcrypt.generate_password_hash(senha).decode('utf-8')

    def check_senha(self, senha):
        return bcrypt.check_password_hash(self.senha_hash, senha)


class Orcamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    telefone = db.Column(db.String(20))
    tipo_servico = db.Column(db.String(100), nullable=False)
    mensagem = db.Column(db.Text)
    status = db.Column(db.String(30), default='pendente')  # pendente, aprovado, pago, cancelado
    valor = db.Column(db.Float, nullable=True)
    pagamento_id = db.Column(db.String(200), nullable=True)
    pagamento_url = db.Column(db.String(500), nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


# ══════════════════════════════════════
# HELPERS
# ══════════════════════════════════════

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


def cliente_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('cliente_id'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def gerar_pagamento_abacatepay(orcamento):
    """Gera link de pagamento via AbacatePay"""
    if not ABACATEPAY_API_KEY:
        return None, 'Chave AbacatePay não configurada'

    headers = {
        'Authorization': f'Bearer {ABACATEPAY_API_KEY}',
        'Content-Type': 'application/json'
    }
    payload = {
        'amount': int(orcamento.valor * 100),  # em centavos
        'description': f'Orçamento #{orcamento.id} - {orcamento.tipo_servico}',
        'customer': {
            'name': orcamento.nome,
            'email': orcamento.email,
        },
        'methods': ['PIX'],
    }
    try:
        resp = requests.post(f'{ABACATEPAY_BASE_URL}/billing/create', json=payload, headers=headers)
        data = resp.json()
        if resp.status_code == 200:
            return data.get('url'), None
        return None, data.get('message', 'Erro ao gerar pagamento')
    except Exception as e:
        return None, str(e)


# ══════════════════════════════════════
# ROTAS PÚBLICAS
# ══════════════════════════════════════

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sobre')
def sobre():
    return render_template('sobre.html')

@app.route('/projetos')
def projetos():
    return render_template('projetos.html')

@app.route('/galeria')
def galeria():
    return render_template('galeria.html')

@app.route('/orcamentos')
def orcamentos():
    return render_template('orcamentos.html')


# ── FORMULÁRIO DE ORÇAMENTO ──
@app.route('/solicitar-orcamento', methods=['POST'])
def solicitar_orcamento():
    nome = request.form.get('nome', '').strip()
    email = request.form.get('email', '').strip()
    telefone = request.form.get('telefone', '').strip()
    tipo_servico = request.form.get('tipo_servico', '').strip()
    mensagem = request.form.get('mensagem', '').strip()

    if not nome or not email or not tipo_servico:
        flash('Preencha todos os campos obrigatórios.', 'erro')
        return redirect(url_for('orcamentos'))

    cliente_id = session.get('cliente_id')

    orc = Orcamento(
        nome=nome,
        email=email,
        telefone=telefone,
        tipo_servico=tipo_servico,
        mensagem=mensagem,
        cliente_id=cliente_id,
        status='pendente'
    )
    db.session.add(orc)
    db.session.commit()

    flash('Orçamento enviado! Entrarei em contato em breve.', 'sucesso')
    return redirect(url_for('orcamentos'))


# ══════════════════════════════════════
# ÁREA DO CLIENTE
# ══════════════════════════════════════

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('cliente_id'):
        return redirect(url_for('area_cliente'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        senha = request.form.get('senha', '')
        cliente = Cliente.query.filter_by(email=email).first()

        if cliente and cliente.check_senha(senha):
            session['cliente_id'] = cliente.id
            session['cliente_nome'] = cliente.nome
            return redirect(url_for('area_cliente'))
        flash('Email ou senha incorretos.', 'erro')

    return render_template('login.html')


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip()
        senha = request.form.get('senha', '')

        if Cliente.query.filter_by(email=email).first():
            flash('Email já cadastrado.', 'erro')
            return render_template('login.html', modo='cadastro')

        cliente = Cliente(nome=nome, email=email)
        cliente.set_senha(senha)
        db.session.add(cliente)
        db.session.commit()
        session['cliente_id'] = cliente.id
        session['cliente_nome'] = cliente.nome
        return redirect(url_for('area_cliente'))

    return render_template('login.html', modo='cadastro')


@app.route('/area-cliente')
@cliente_required
def area_cliente():
    cliente = Cliente.query.get(session['cliente_id'])
    orcamentos_cliente = Orcamento.query.filter_by(cliente_id=cliente.id).order_by(Orcamento.criado_em.desc()).all()
    return render_template('cliente.html', cliente=cliente, orcamentos=orcamentos_cliente)


@app.route('/logout')
def logout():
    session.pop('cliente_id', None)
    session.pop('cliente_nome', None)
    return redirect(url_for('index'))


# ══════════════════════════════════════
# PAINEL ADMIN
# ══════════════════════════════════════

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin'):
        return redirect(url_for('admin_painel'))

    if request.method == 'POST':
        senha = request.form.get('senha', '')
        if bcrypt.check_password_hash(ADMIN_PASSWORD, senha):
            session['admin'] = True
            return redirect(url_for('admin_painel'))
        flash('Senha incorreta.', 'erro')

    return render_template('admin_login.html')


@app.route('/admin/painel')
@admin_required
def admin_painel():
    orcamentos_todos = Orcamento.query.order_by(Orcamento.criado_em.desc()).all()
    clientes_todos = Cliente.query.order_by(Cliente.criado_em.desc()).all()
    total_pendente = Orcamento.query.filter_by(status='pendente').count()
    total_pago = Orcamento.query.filter_by(status='pago').count()
    return render_template('admin.html',
        orcamentos=orcamentos_todos,
        clientes=clientes_todos,
        total_pendente=total_pendente,
        total_pago=total_pago
    )


@app.route('/admin/orcamento/<int:id>/status', methods=['POST'])
@admin_required
def admin_atualizar_status(id):
    orc = Orcamento.query.get_or_404(id)
    novo_status = request.form.get('status')
    novo_valor = request.form.get('valor')

    if novo_valor:
        try:
            orc.valor = float(novo_valor.replace(',', '.'))
        except:
            pass

    if novo_status:
        orc.status = novo_status

    # Se aprovado com valor, gera link de pagamento
    if novo_status == 'aprovado' and orc.valor:
        url_pag, erro = gerar_pagamento_abacatepay(orc)
        if url_pag:
            orc.pagamento_url = url_pag
            orc.status = 'aguardando_pagamento'

    db.session.commit()
    flash(f'Orçamento #{id} atualizado.', 'sucesso')
    return redirect(url_for('admin_painel'))


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))


# ── WEBHOOK ABACATEPAY ──
@app.route('/webhook/abacatepay', methods=['POST'])
def webhook_abacatepay():
    data = request.json
    if not data:
        return jsonify({'ok': False}), 400

    pagamento_id = data.get('id')
    status = data.get('status')

    if pagamento_id and status == 'PAID':
        orc = Orcamento.query.filter_by(pagamento_id=pagamento_id).first()
        if orc:
            orc.status = 'pago'
            db.session.commit()

    return jsonify({'ok': True})


# ══════════════════════════════════════
# INIT
# ══════════════════════════════════════

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=False)
