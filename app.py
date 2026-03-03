import os
import json
import requests
from datetime import datetime
from urllib.parse import quote
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-troque-em-producao')

database_url = os.environ.get('DATABASE_URL', 'sqlite:///database.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

ABACATEPAY_API_KEY = os.environ.get('ABACATEPAY_API_KEY', '')
ABACATEPAY_BASE_URL = 'https://api.abacatepay.com/v1'
ADMIN_PASSWORD_PLAIN = os.environ.get('ADMIN_PASSWORD', 'Dahan1005@')
WHATSAPP_ORCAMENTO_NUMERO = os.environ.get('WHATSAPP_ORCAMENTO_NUMERO', '5521970913261')


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
    descricao_servico = db.Column(db.String(200))
    mensagem = db.Column(db.Text)
    # Status: pendente → aprovado → aguardando_pagamento → pago → recusado
    status = db.Column(db.String(30), default='pendente')
    valor = db.Column(db.Float, nullable=True)
    pagamento_id = db.Column(db.String(200), nullable=True)
    pagamento_url = db.Column(db.String(500), nullable=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    pago_em = db.Column(db.DateTime, nullable=True)

    @property
    def status_label(self):
        labels = {
            'pendente': ('Pendente', 'yellow'),
            'aprovado': ('Aprovado', 'blue'),
            'aguardando_pagamento': ('Aguard. Pagamento', 'orange'),
            'pago': ('Pago ✓', 'green'),
            'recusado': ('Recusado', 'red'),
        }
        return labels.get(self.status, (self.status, 'gray'))


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
        cliente_id = session.get('cliente_id')
        if not cliente_id:
            flash('Você precisa estar logado para acessar essa área.', 'aviso')
            session['redirect_after_login'] = request.url
            return redirect(url_for('login'))

        # Sessão antiga/inválida: evita erro em carrinho/área do cliente.
        if not db.session.get(Cliente, cliente_id):
            session.pop('cliente_id', None)
            session.pop('cliente_nome', None)
            flash('Sua sessão expirou. Faça login novamente.', 'aviso')
            session['redirect_after_login'] = request.url
            return redirect(url_for('login'))

        return f(*args, **kwargs)
    return decorated


def gerar_pagamento_abacatepay(orcamento):
    if not ABACATEPAY_API_KEY:
        return None, None, 'Chave AbacatePay não configurada'

    headers = {
        'Authorization': f'Bearer {ABACATEPAY_API_KEY}',
        'Content-Type': 'application/json'
    }
    payload = {
        'amount': int(orcamento.valor * 100),
        'description': f'Orçamento #{orcamento.id} - {orcamento.tipo_servico}',
        'customer': {
            'name': orcamento.nome,
            'email': orcamento.email,
        },
        'methods': ['PIX'],
    }
    try:
        resp = requests.post(f'{ABACATEPAY_BASE_URL}/billing/create', json=payload, headers=headers)
        data = resp.json() if resp.content else {}
        if resp.status_code == 200:
            pagamento_id = data.get('id')
            pagamento_url = data.get('url')
            return pagamento_id, pagamento_url, None
        return None, None, data.get('message', 'Erro ao gerar pagamento')
    except Exception as e:
        return None, None, str(e)


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


# ══════════════════════════════════════
# SISTEMA DE ORÇAMENTO (requer login)
# ══════════════════════════════════════

@app.route('/orcamentos')
@cliente_required
def orcamentos():
    return render_template('orcamentos.html')


@app.route('/solicitar-orcamento', methods=['POST'])
@cliente_required
def solicitar_orcamento():
    nome = request.form.get('nome', '').strip()
    email = request.form.get('email', '').strip()
    telefone = request.form.get('telefone', '').strip()
    tipo_servico = request.form.get('tipo_servico', '').strip()
    descricao_servico = request.form.get('descricao_servico', '').strip()
    mensagem = request.form.get('mensagem', '').strip()

    if not nome or not email or not tipo_servico:
        flash('Preencha todos os campos obrigat?rios.', 'erro')
        return redirect(url_for('orcamentos'))

    cliente_id = session.get('cliente_id')

    orc = Orcamento(
        nome=nome,
        email=email,
        telefone=telefone,
        tipo_servico=tipo_servico,
        descricao_servico=descricao_servico,
        mensagem=mensagem,
        cliente_id=cliente_id,
        status='pendente'
    )
    db.session.add(orc)
    db.session.commit()

    # Continua indo para o painel admin via banco e já monta mensagem para WhatsApp
    partes = [
        f"📩 Novo orçamento #{orc.id}",
        f"Nome: {orc.nome}",
        f"Email: {orc.email}",
        f"Telefone: {orc.telefone or '-'}",
        f"Serviço: {orc.tipo_servico}",
        f"Descrição: {orc.descricao_servico or '-'}",
        f"Detalhes: {orc.mensagem or '-'}",
    ]
    texto = quote('\n'.join(partes))

    flash(
        f'Orçamento #{orc.id} enviado com sucesso! Seus dados também foram preparados no WhatsApp.',
        'sucesso'
    )

    return redirect(f"https://wa.me/{WHATSAPP_ORCAMENTO_NUMERO}?text={texto}")

    return redirect(f"https://wa.me/{WHATSAPP_ORCAMENTO_NUMERO}?text={texto}")

    return redirect(f"https://wa.me/{WHATSAPP_ORCAMENTO_NUMERO}?text={texto}")

    return redirect(f"https://wa.me/{WHATSAPP_ORCAMENTO_NUMERO}?text={texto}")


@app.route('/carrinho')
@cliente_required
def carrinho():
    cliente_id = session.get('cliente_id')
    cliente = db.session.get(Cliente, cliente_id)
    # Mostra todos os orçamentos do cliente no carrinho
    meus_orcamentos = Orcamento.query.filter_by(cliente_id=cliente_id)\
        .order_by(Orcamento.criado_em.desc()).all()
    return render_template('carrinho.html', cliente=cliente, orcamentos=meus_orcamentos)


@app.route('/carrinho/pagar/<int:id>')
@cliente_required
def carrinho_pagar(id):
    orc = Orcamento.query.get_or_404(id)

    # Segurança: só o dono pode pagar
    if orc.cliente_id != session.get('cliente_id'):
        flash('Acesso negado.', 'erro')
        return redirect(url_for('carrinho'))

    if orc.status != 'aguardando_pagamento' or not orc.pagamento_url:
        flash('Este orçamento ainda não foi aprovado para pagamento.', 'aviso')
        return redirect(url_for('carrinho'))

    return redirect(orc.pagamento_url)


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
            # Redireciona para onde tentou acessar antes do login
            next_url = session.pop('redirect_after_login', None)
            return redirect(next_url or url_for('area_cliente'))
        flash('Email ou senha incorretos.', 'erro')

    return render_template('login.html')


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip()
        senha = request.form.get('senha', '')
        confirmar = request.form.get('confirmar_senha', '')

        if not nome or not email:
            flash('Nome e email são obrigatórios.', 'erro')
            return render_template('cadastro.html')

        if senha != confirmar:
            flash('As senhas não coincidem.', 'erro')
            return render_template('cadastro.html')

        if len(senha) < 6:
            flash('A senha deve ter pelo menos 6 caracteres.', 'erro')
            return render_template('cadastro.html')

        if Cliente.query.filter_by(email=email).first():
            flash('Email já cadastrado.', 'erro')
            return render_template('cadastro.html')

        cliente = Cliente(nome=nome, email=email)
        cliente.set_senha(senha)
        db.session.add(cliente)
        db.session.commit()
        session['cliente_id'] = cliente.id
        session['cliente_nome'] = cliente.nome

        next_url = session.pop('redirect_after_login', None)
        return redirect(next_url or url_for('area_cliente'))

    return render_template('cadastro.html')


@app.route('/area-cliente')
@cliente_required
def area_cliente():
    cliente = db.session.get(Cliente, session['cliente_id'])
    orcamentos_cliente = Orcamento.query.filter_by(cliente_id=cliente.id)\
        .order_by(Orcamento.criado_em.desc()).all()
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
        if senha == ADMIN_PASSWORD_PLAIN:
            session['admin'] = True
            return redirect(url_for('admin_painel'))
        flash('Senha incorreta.', 'erro')

    return render_template('admin_login.html')


@app.route('/admin/painel')
@admin_required
def admin_painel():
    filtro = request.args.get('status', 'todos')
    query = Orcamento.query.order_by(Orcamento.criado_em.desc())
    if filtro != 'todos':
        query = query.filter_by(status=filtro)

    orcamentos_todos = query.all()
    clientes_todos = Cliente.query.order_by(Cliente.criado_em.desc()).all()

    stats = {
        'total': Orcamento.query.count(),
        'pendente': Orcamento.query.filter_by(status='pendente').count(),
        'aprovado': Orcamento.query.filter_by(status='aprovado').count(),
        'aguardando_pagamento': Orcamento.query.filter_by(status='aguardando_pagamento').count(),
        'pago': Orcamento.query.filter_by(status='pago').count(),
        'recusado': Orcamento.query.filter_by(status='recusado').count(),
        'receita_total': db.session.query(db.func.sum(Orcamento.valor))
            .filter_by(status='pago').scalar() or 0,
    }

    return render_template('admin.html',
        orcamentos=orcamentos_todos,
        clientes=clientes_todos,
        stats=stats,
        filtro_ativo=filtro
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

    # Quando admin aprova, gera link de pagamento automaticamente
    if novo_status == 'aprovado' and orc.valor:
        pag_id, pag_url, erro = gerar_pagamento_abacatepay(orc)
        if pag_url:
            orc.pagamento_id = pag_id
            orc.pagamento_url = pag_url
            orc.status = 'aguardando_pagamento'
            flash(f'Orçamento #{id} aprovado e link de pagamento gerado!', 'sucesso')
        else:
            flash(f'Orçamento aprovado, mas erro ao gerar pagamento: {erro}', 'aviso')
    else:
        flash(f'Orçamento #{id} atualizado para: {novo_status}.', 'sucesso')

    db.session.commit()
    return redirect(url_for('admin_painel'))


@app.route('/admin/orcamento/<int:id>/marcar-pago', methods=['POST'])
@admin_required
def admin_marcar_pago(id):
    """Permite admin marcar manualmente como pago (para testes ou pagamento fora da plataforma)"""
    orc = Orcamento.query.get_or_404(id)
    orc.status = 'pago'
    orc.pago_em = datetime.utcnow()
    db.session.commit()
    flash(f'Orçamento #{id} marcado como PAGO.', 'sucesso')
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
            orc.pago_em = datetime.utcnow()
            db.session.commit()

    return jsonify({'ok': True})


def aplicar_migracoes_basicas():
    """Aplica ajustes simples de schema em bancos já existentes (sem Alembic)."""
    comandos = [
        "ALTER TABLE orcamento ADD COLUMN descricao_servico VARCHAR(200)",
        "ALTER TABLE orcamento ADD COLUMN criado_em TIMESTAMP",
        "ALTER TABLE orcamento ADD COLUMN pago_em TIMESTAMP",
        "ALTER TABLE cliente ADD COLUMN criado_em TIMESTAMP",
    ]

    for sql in comandos:
        try:
            db.session.execute(db.text(sql))
            db.session.commit()
        except Exception:
            db.session.rollback()



# ══════════════════════════════════════
# INIT
# ══════════════════════════════════════

with app.app_context():
    db.create_all()
    aplicar_migracoes_basicas()

if __name__ == '__main__':
    app.run(debug=False)
