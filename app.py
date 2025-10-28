# app.py

from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import os
from functools import wraps
from datetime import datetime
import json

import firebase_admin
from firebase_admin import credentials, firestore, auth


# =========================================================
# 1. CONFIGURAÇÃO GERAL
# =========================================================
app = Flask(__name__)

# Configurações de segurança
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sua_chave_secreta_padrao_muito_longa')


# =========================================================
# 1.1 CONFIGURAÇÃO FIREBASE ADMIN SDK
# =========================================================
db = None # Variável global para o cliente Firestore

try:
    # 1. Tenta carregar da variável de ambiente (USO EM PRODUÇÃO)
    FIREBASE_SERVICE_ACCOUNT_JSON = os.environ.get('FIREBASE_CONFIG_JSON')
    
    if FIREBASE_SERVICE_ACCOUNT_JSON:
        # Carrega o JSON da string (variável de ambiente)
        cred_json = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
        cred = credentials.Certificate(cred_json)
        print("INFO: Credenciais carregadas da variável de ambiente 'FIREBASE_CONFIG_JSON'.")
    else:
        # 2. Tenta carregar de um arquivo local (USO EM DESENVOLVIMENTO)
        cred = credentials.Certificate('serviceAccountKey.json')
        print("INFO: Credenciais carregadas do arquivo local 'serviceAccountKey.json'.")
        
except FileNotFoundError:
    print("AVISO: Arquivo 'serviceAccountKey.json' não encontrado localmente.")
    cred = None
except Exception as e:
    # Este erro pode ocorrer se o JSON da variável de ambiente for mal-formado
    print(f"ERRO ao carregar credenciais: {e}")
    cred = None

# Inicializa o Firebase apenas se as credenciais foram carregadas com sucesso
if not firebase_admin._apps and cred:
    firebase_admin.initialize_app(cred, {
        'projectId': "pc-teacher-6c75f",
    })
    db = firestore.client()
    print("INFO: Firebase Admin SDK inicializado com sucesso.")
elif not firebase_admin._apps:
    print("ERRO CRÍTICO: Firebase Admin SDK não foi inicializado. Verifique as credenciais.")


# =========================================================
# 2. CONFIGURAÇÕES ESTÁTICAS DE CURSO E PROJETO (NOVO MAPA)
# =========================================================

MODULO_CONFIG = [
    {
        'title': 'Introdução ao Pensamento Computacional',
        'field': 'introducao_concluido',
        'slug': 'introducao',
        'template': 'conteudo-introducao.html', 
        'order': 1,
        'description': 'Entenda o que é o Pensamento Computacional, seus pilares e por que ele é crucial para o futuro.',
        'lessons': 1, 'exercises': 5, 'dependency_field': None
    },
    {
        'title': 'Decomposição',
        'field': 'decomposicao_concluido',
        'slug': 'decomposicao',
        'template': 'conteudo-decomposicao.html', 
        'order': 2,
        'description': 'Aprenda a quebrar problemas complexos em partes menores e gerenciáveis.',
        'lessons': 1, 'exercises': 5, 'dependency_field': 'introducao_concluido'
    },
    {
        'title': 'Reconhecimento de Padrões',
        'field': 'reconhecimento_padroes_concluido',
        'slug': 'rec-padrao',
        'template': 'conteudo-rec-padrao.html', 
        'order': 3,
        'description': 'Identifique similaridades e tendências para simplificar a resolução de problemas.',
        'lessons': 1, 'exercises': 5, 'dependency_field': 'decomposicao_concluido'
    },
    {
        'title': 'Abstração',
        'field': 'abstracao_concluido',
        'slug': 'abstracao',
        'template': 'conteudo-abstracao.html', 
        'order': 4,
        'description': 'Foque apenas nas informações importantes, ignorando detalhes irrelevantes.',
        'lessons': 1, 'exercises': 5, 'dependency_field': 'reconhecimento_padroes_concluido'
    },
    {
        'title': 'Algoritmos',
        'field': 'algoritmo_concluido',
        'slug': 'algoritmo',
        'template': 'conteudo-algoritmos.html', # CORRIGIDO: O nome do arquivo estava 'conteudo-algoritmo.html'
        'order': 5,
        'description': 'Desenvolva sequências lógicas e organizadas para resolver problemas de forma eficaz.',
        'lessons': 1, 'exercises': 5, 'dependency_field': 'abstracao_concluido'
    },
    {
        'title': 'Projeto Final',
        'field': 'projeto_final_concluido',
        'slug': 'projeto-final',
        'template': 'conteudo-projeto-final.html', 
        'order': 6,
        'description': 'Aplique todos os pilares do PC para solucionar um desafio prático de sala de aula.',
        'lessons': 1, 'exercises': 0, 'dependency_field': 'algoritmo_concluido'
    },
]

MODULO_BY_SLUG = {m['slug']: m for m in MODULO_CONFIG}

# NOVO MAPA: Mapeia SLUG do módulo para as CHAVES de campo de projeto esperadas no template.
# Isso garante que a lógica de salvamento e carregamento use as mesmas chaves.
PROJETO_FIELD_MAP = {
    'introducao': ['project_name', 'project_objective', 'project_target'],
    'decomposicao': ['project_justification'],
    'rec-padrao': ['project_pattern_optimization'],
    'abstracao': ['project_abstraction'],
    'algoritmo': ['project_algorithm'],
}


# =========================================================
# 3. HELPERS E DECORATORS (Com adições para Projeto)
# =========================================================

def get_firestore_doc(collection_name, doc_id):
    """Auxiliar para buscar um documento no Firestore e retornar como dict."""
    if not db: return None # Proteção caso o DB não inicialize
    doc_ref = db.collection(collection_name).document(str(doc_id))
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        data['id'] = doc.id # Adiciona o ID do documento ao dict
        return data
    return None

def usuario_logado():
    """Retorna o objeto (dict) Usuario logado ou None, buscando no Firestore."""
    if 'usuario_id' in session and db:
        user_id = session['usuario_id']
        # 1. Busca o usuário
        user_data = get_firestore_doc('usuarios', user_id)
        
        if user_data:
            # 2. Busca o progresso associado
            progresso_data = get_firestore_doc('progresso', user_id)
            user_data['progresso'] = progresso_data if progresso_data else {}
            return user_data
    return None

def requires_auth(func):
    """Decorator para verificar se o usuário está logado antes de acessar a rota."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not usuario_logado():
            flash('Você precisa estar logado para acessar esta página.', 'warning')
            return redirect(url_for('login'))
        return func(*args, **kwargs)
    return wrapper

def calculate_progress(progresso_db):
    # ... (Função calculate_progress permanece a mesma, pois já estava atualizada) ...
    """Calcula todas as métricas de progresso do curso.
        progresso_db agora é um dicionário (dict) do Firestore."""
    
    total_modules = len(MODULO_CONFIG)
    completed_modules = 0
    total_lessons = sum(m['lessons'] for m in MODULO_CONFIG)
    total_exercises = sum(m['exercises'] for m in MODULO_CONFIG)
    completed_lessons = 0
    completed_exercises = 0
    
    dynamic_modules = []
    
    for module_config in MODULO_CONFIG:
        db_field = module_config['field']
        
        # MUDANÇA: Acessa o status de conclusão como uma chave de dicionário
        is_completed = progresso_db.get(db_field, False) 
        
        # Lógica de Desbloqueio (BASEADA NA DEPENDÊNCIA explícita)
        dependency_field = module_config.get('dependency_field')
        
        if dependency_field is None:
            is_unlocked_for_current_module = True
        else:
            # MUDANÇA: Acessa o status da dependência como chave de dicionário
            dependency_is_completed = progresso_db.get(dependency_field, False)
            is_unlocked_for_current_module = dependency_is_completed 

        # Contadores
        if is_completed:
            completed_modules += 1
            completed_lessons += module_config['lessons']
            completed_exercises += module_config['exercises']

        dynamic_modules.append({
            'title': module_config['title'],
            'description': module_config['description'],
            'slug': module_config['slug'],
            'order': module_config['order'],
            'is_unlocked': is_unlocked_for_current_module,
            'is_completed': is_completed,
            'lessons': module_config['lessons'],
            'exercises': module_config['exercises'],
        })
    
    overall_progress_percent = int((completed_modules / total_modules) * 100) if total_modules > 0 else 0
    
    return {
        'overall_percent': overall_progress_percent,
        'completed_modules': completed_modules,
        'total_modules': total_modules,
        'completed_lessons': completed_lessons,
        'total_lessons': total_lessons,
        'completed_exercises': completed_exercises,
        'total_exercises': total_exercises,
        'modules': dynamic_modules 
    }

# NOVO HELPER: Carrega todas as respostas do projeto de um usuário e as mapeia para as chaves do template.
def load_all_project_data(user_id):
    """Busca todas as respostas do projeto do usuário e consolida em um dict."""
    if not db: return {}
    
    # 1. Busca todas as respostas do projeto para este usuário
    respostas_query = db.collection('respostas_projeto').where('usuario_id', '==', user_id).stream()
    
    all_data = {}
    
    # 2. Itera sobre os documentos e consolida os campos em um único dicionário
    for r_doc in respostas_query:
        # A resposta é o documento que contém os campos project_name, project_objective, etc.
        r = r_doc.to_dict()
        # O documento já está estruturado com as chaves corretas (ex: 'project_name')
        all_data.update(r)

    # Remove o 'usuario_id' do dicionário final, se existir
    all_data.pop('usuario_id', None)
    return all_data


# =========================================================
# 4. ROTAS DE AUTENTICAÇÃO
# =========================================================
# ... (Rotas 'cadastro', 'login', 'logout' permanecem as mesmas) ...

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    usuario = usuario_logado()
    if usuario:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        if not db:
            flash('Erro: O serviço de banco de dados não está disponível.', 'danger')
            return render_template('cadastro.html', nome_for_form=nome, email_for_form=email)
        
        # 1. Verifica se o e-mail já existe (Firestore Query)
        email_exists_query = db.collection('usuarios').where('email', '==', email).limit(1).stream()
        email_exists = next(email_exists_query, None)
        
        if email_exists:
            flash('Este e-mail já está cadastrado. Tente fazer o login.', 'danger')
            return render_template('cadastro.html', nome_for_form=nome, email_for_form=email)

        # 2. Cria novo usuário no Firebase Authentication e Firestore
        try:
            # 2.1 Criar no Firebase Authentication (para login seguro)
            user_auth = auth.create_user(email=email, password=senha, display_name=nome)
            user_id = user_auth.uid
            
            # 2.2 Salvar dados no Firestore (Coleção 'usuarios')
            novo_usuario_data = {
                'nome': nome,
                'email': email,
                'senha_hash': generate_password_hash(senha),
                'instituicao': '',
                'telefone': '',
                'cargo': 'Professor(a)',
                'created_at': firestore.SERVER_TIMESTAMP
            }
            db.collection('usuarios').document(user_id).set(novo_usuario_data)
            
            # 2.3 Cria um registro de progresso (Coleção 'progresso')
            novo_progresso_data = {
                'introducao_concluido': False,
                'decomposicao_concluido': False,
                'reconhecimento_padroes_concluido': False,
                'abstracao_concluido': False,
                'algoritmo_concluido': False,
                'projeto_final_concluido': False,
            }
            db.collection('progresso').document(user_id).set(novo_progresso_data)

            flash('Cadastro realizado com sucesso! Faça login para começar.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            flash(f'Erro interno ao cadastrar: {str(e)}', 'danger')
            
    return render_template('cadastro.html', user=usuario)

@app.route('/login', methods=['GET', 'POST'])
def login():
    usuario = usuario_logado()
    if usuario:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        if not db:
            flash('Erro: O serviço de banco de dados não está disponível.', 'danger')
            return render_template('login.html', email_for_form=email)
        
        # 1. Busca o usuário pelo e-mail
        user_query = db.collection('usuarios').where('email', '==', email).limit(1).stream()
        usuario_doc = next(user_query, None)
        
        if usuario_doc:
            usuario_data = usuario_doc.to_dict()
            usuario_data['id'] = usuario_doc.id # O ID é o UID/Doc ID
            
            # 2. Verifica a senha (usando o hash armazenado por compatibilidade)
            if 'senha_hash' in usuario_data and check_password_hash(usuario_data['senha_hash'], senha):
                session['usuario_id'] = usuario_data['id'] # Salva o ID (UID) no Flask Session
                flash(f'Bem-vindo(a), {usuario_data["nome"]}!', 'success')
                return redirect(url_for('dashboard'))

        flash('E-mail ou senha incorretos.', 'danger')
        return render_template('login.html', email_for_form=email)

    return render_template('login.html', user=usuario)

@app.route('/logout')
def logout():
    """Remove o ID da sessão e redireciona para a página inicial."""
    session.pop('usuario_id', None)
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('index'))


# =========================================================
# 4.1 ROTAS DE INFORMAÇÃO
# =========================================================
# ... (Rotas infor-curso-decomposicao, etc. permanecem as mesmas) ...

@app.route('/infor-curso-decomposicao')
def infor_curso_decomposicao():
    usuario = usuario_logado()
    return render_template('infor-curso-decomposicao.html', user=usuario)

@app.route('/infor-curso-rec-padrao')
def infor_curso_rec_padrao():
    usuario = usuario_logado()
    return render_template('infor-curso-rec-padrao.html', user=usuario)

@app.route('/infor-curso-abstracao')
def infor_curso_abstracao():
    usuario = usuario_logado()
    return render_template('infor-curso-abstracao.html', user=usuario)

@app.route('/infor-curso-algoritmo')
def infor_curso_algoritmo():
    usuario = usuario_logado()
    return render_template('infor-curso-algoritmo.html', user=usuario)


# =========================================================
# 5. ROTAS DE ÁREA RESTRITA E PERFIL
# =========================================================
# ... (Rotas 'index', 'dashboard', 'perfil', 'progresso' permanecem as mesmas) ...

@app.route('/')
def index():
    usuario = usuario_logado()
    return render_template('index.html', user=usuario)

@app.route('/dashboard')
@requires_auth
def dashboard():
    usuario = usuario_logado()
    return render_template('dashboard.html', user=usuario)


@app.route('/perfil', methods=['GET', 'POST']) 
@requires_auth
def perfil():
    usuario = usuario_logado()
    
    if request.method == 'POST':
        user_id = usuario['id']
        
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        institution = request.form.get('institution')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        tem_erro = False
        
        if not db:
            flash('Erro: O serviço de banco de dados não está disponível.', 'danger')
            return render_template('perfil.html', user=usuario)

        try:
            # 1. Dicionário para atualização no Firestore
            update_data = {}
            
            # 2. Checa e atualiza E-mail
            if email != usuario['email']:
                email_existente_query = db.collection('usuarios').where('email', '==', email).limit(1).stream()
                email_existente = next(email_existente_query, None)
                
                if email_existente and email_existente.id != user_id:
                    flash("Este novo e-mail já está em uso por outro usuário.", 'danger')
                    tem_erro = True
                else:
                    update_data['email'] = email
                    # Atualiza também no Firebase Auth
                    auth.update_user(user_id, email=email)
                    
            # 3. Processa a mudança de senha
            if new_password:
                if new_password != confirm_password:
                    flash("As novas senhas digitadas não coincidem.", 'danger')
                    tem_erro = True
                elif len(new_password) < 6:
                    flash("A nova senha deve ter no mínimo 6 caracteres.", 'danger')
                    tem_erro = True
                else:
                    # Atualiza no Firebase Authentication E no Firestore (para o hash)
                    auth.update_user(user_id, password=new_password)
                    update_data['senha_hash'] = generate_password_hash(new_password)
                    flash("Senha atualizada com sucesso!", 'success')

            # 4. Atualiza dados básicos
            update_data['nome'] = name
            update_data['telefone'] = phone
            update_data['instituicao'] = institution
            
            if not tem_erro and update_data:
                # 5. Commit no Firestore
                db.collection('usuarios').document(user_id).update(update_data)
                
                # Se não atualizou a senha, exibe sucesso nos dados
                if not new_password:
                    flash("Dados do perfil atualizados com sucesso!", 'success')
            
            # Redireciona para recarregar o usuário atualizado
            return redirect(url_for('perfil'))
                
        except Exception as e:
            flash(f"Ocorreu um erro inesperado ao salvar: {str(e)}", 'danger')
            return render_template('perfil.html', user=usuario) 

    # Lógica GET
    return render_template('perfil.html', user=usuario)

@app.route('/progresso')
@requires_auth
def progresso():
    usuario = usuario_logado()
    progresso_db = usuario.get('progresso', {}) 
    
    progresso_data = calculate_progress(progresso_db) 

    context = {
        'user': usuario,
        'title': "Meu Progresso",
        'progresso_data': progresso_data 
    }
    
    return render_template('progresso.html', **context)


# =========================================================
# 6. ROTAS DE CERTIFICADO
# =========================================================
# ... (Rotas 'certificado' e 'gerar_certificado' permanecem as mesmas) ...

@app.route('/certificado')
@requires_auth
def certificado():
    usuario = usuario_logado()
    progresso_db = usuario.get('progresso', {})
    
    progresso_data = calculate_progress(progresso_db)
    
    certificado_disponivel = progresso_data['overall_percent'] == 100
    data_emissao = datetime.now().strftime('%d/%m/%Y')
    
    context = {
        'user': usuario,
        'title': "Certificado",
        'certificado_disponivel': certificado_disponivel,
        'nome_usuario': usuario['nome'], 
        'data_emissao': data_emissao
    }
    return render_template('certificado.html', **context)

@app.route('/gerar-certificado')
@requires_auth
def gerar_certificado():
    usuario = usuario_logado()
    progresso_db = usuario.get('progresso', {})
    progresso_data = calculate_progress(progresso_db)
    
    if progresso_data['overall_percent'] != 100:
        flash('Você deve concluir todos os módulos para gerar o certificado.', 'warning')
        return redirect(url_for('certificado'))

    nome_completo = usuario['nome'].upper()
    data_conclusao_str = datetime.now().strftime('%d de \%B de \%Y')
    carga_horaria = 24 
    
    # generate_latex_certificate é uma função externa que gera o conteúdo .tex
    def generate_latex_certificate(nome, data, carga):
         # Exemplo básico de conteúdo LaTeX para demonstração.
        return f"""
\\documentclass{{article}}
\\usepackage{{geometry}}
\\usepackage[utf8]{{inputenc}}
\\geometry{{a4paper, margin=1in}}
\\begin{{document}}
\\centering
{{\\Huge Certificado de Conclusão}} \\\\
\\vspace{{0.5cm}}
Este documento certifica que
\\vspace{{0.5cm}}
{{\\Huge\\bfseries {nome}}} \\\\
\\vspace{{0.5cm}}
concluiu com sucesso o curso "Pensamento Computacional para Professores", com carga horária de {carga} horas, em {data}.
\\end{{document}}
"""
    
    latex_content = generate_latex_certificate(nome_completo, data_conclusao_str, carga_horaria)
    
    return Response(
        latex_content,
        mimetype='application/x-tex',
        headers={'Content-Disposition': f'attachment;filename=Certificado_{nome_completo.replace(" ", "_")}.tex'}
    )


# =========================================================
# 8. ROTAS DE CONTEÚDO DE CURSO (AJUSTADAS PARA PROJETO)
# =========================================================

@app.route('/modulos')
@requires_auth
def modulos():
    usuario = usuario_logado()
    progresso = usuario.get('progresso', {})
    
    progresso_data = calculate_progress(progresso)
    modulos_list = progresso_data.get('modules', []) 

    return render_template('modulos.html', user=usuario, modulos=modulos_list, progresso_data=progresso_data)


@app.route('/salvar-projeto-modulo/<string:modulo_slug>', methods=['POST'])
@requires_auth
def salvar_projeto_modulo(modulo_slug):
    usuario = usuario_logado()
    user_id = usuario['id']
    
    if not db:
        return jsonify({'success': False, 'message': 'Serviço de banco de dados indisponível.'}), 500
    
    # 1. Obtém as chaves de campo que este módulo deve salvar (ex: ['project_name', 'project_objective'])
    project_fields = PROJETO_FIELD_MAP.get(modulo_slug)
    if not project_fields:
        return jsonify({'success': False, 'message': f'Configuração de projeto não encontrada para o módulo {modulo_slug}.'}), 400

    # 2. Prepara os dados a serem salvos
    resposta_data = {'usuario_id': user_id, 'data_atualizacao': firestore.SERVER_TIMESTAMP}
    form_data = request.form # Usa request.form pois os templates estão enviando via POST de formulário

    for field_name in project_fields:
        value = form_data.get(field_name)
        if not value:
            flash(f"O campo '{field_name}' está vazio e não foi salvo.", 'warning')
        else:
            # Adiciona o campo e seu valor ao dicionário de atualização
            resposta_data[field_name] = value

    if len(resposta_data) <= 2: # Contém apenas 'usuario_id' e 'data_atualizacao'
        return jsonify({'success': False, 'message': 'Nenhum campo de projeto válido foi enviado para salvar.'}), 400

    # 3. Salva os dados na coleção 'respostas_projeto'. 
    # Usamos o UID do usuário como ID do documento, e o merge=True garante que só os campos fornecidos sejam atualizados.
    resposta_ref = db.collection('respostas_projeto').document(user_id)

    try:
        # Usa SET com merge=True para criar ou atualizar os campos no documento do usuário
        resposta_ref.set(resposta_data, merge=True)
        
        # Redireciona para o próximo módulo ou para a rota 'modulos'
        modulo_config = MODULO_BY_SLUG.get(modulo_slug)
        proximo_modulo_order = modulo_config['order'] + 1
        proximo_modulo = next((m for m in MODULO_CONFIG if m['order'] == proximo_modulo_order), None)

        if proximo_modulo:
            flash('Respostas salvas! Prossiga para o próximo módulo.', 'success')
            return redirect(url_for('conteudo_dinamico', modulo_slug=proximo_modulo['slug']))
        else:
            flash('Respostas salvas! Você completou a fase de projeto.', 'success')
            return redirect(url_for('modulos'))
            
    except Exception as e:
        flash(f'Erro interno ao salvar no DB: {str(e)}', 'danger')
        return redirect(url_for('conteudo_dinamico', modulo_slug=modulo_slug))


@app.route('/conteudo/<string:modulo_slug>')
@requires_auth
def conteudo_dinamico(modulo_slug):
    usuario = usuario_logado()
    user_id = usuario['id']
    progresso = usuario.get('progresso', {})
    
    modulo_config = MODULO_BY_SLUG.get(modulo_slug)

    if not modulo_config:
        flash('Módulo de conteúdo não encontrado.', 'danger')
        return redirect(url_for('modulos'))
    
    # 1. Verifica a dependência (lógica de desbloqueio)
    dependency_field = modulo_config.get('dependency_field')
    if dependency_field and not progresso.get(dependency_field, False):
        flash(f'Você deve completar o módulo anterior primeiro.', 'warning')
        return redirect(url_for('modulos'))
        
    # 2. CARREGA TODOS OS DADOS DO PROJETO SALVOS (para preencher campos/exibir resumo)
    all_project_data = load_all_project_data(user_id)
    
    # 3. LÓGICA ESPECÍFICA PARA O MÓDULO FINAL (carregar respostas)
    respostas_projeto_ordenadas = []
    if modulo_slug == 'projeto-final':
        for mod in MODULO_CONFIG:
            if mod['slug'] != 'projeto-final': 
                # Mapeia as chaves de campo para a exibição no resumo
                field_names = PROJETO_FIELD_MAP.get(mod['slug'])
                
                # Para Módulos com múltiplos campos (como Introdução), usamos um dicionário
                if len(field_names) > 1:
                     resposta_texto = {name: all_project_data.get(name, 'Não respondido.') for name in field_names}
                # Para Módulos com um campo, usamos a string diretamente
                else:
                    resposta_texto = all_project_data.get(field_names[0], 'Não respondido.')

                respostas_projeto_ordenadas.append({
                    'title': mod['title'],
                    'slug': mod['slug'],
                    'resposta': resposta_texto,
                    # Verifica se o primeiro campo do módulo foi salvo
                    'is_saved': all_project_data.get(field_names[0]) is not None 
                })
            
    
    # 4. Renderiza o template do módulo
    template_name = modulo_config['template']
    return render_template(
        template_name, 
        user=usuario, 
        progresso=progresso, 
        modulo=modulo_config, 
        project_data=all_project_data, # Passa todos os dados salvos para os templates
        respostas_projeto_ordenadas=respostas_projeto_ordenadas # Usado especificamente no 'projeto-final'
    )


# A rota 'concluir_modulo' permanece a mesma, pois só usa a lógica de progresso
@app.route('/concluir-modulo/<string:modulo_nome>', methods=['POST'])
@requires_auth
def concluir_modulo(modulo_nome):
    usuario = usuario_logado()
    user_id = usuario['id']
    progresso = usuario.get('progresso', {}) # Progresso como dicionário
    
    slug_normalizado = modulo_nome.replace('_', '-')
    modulo_config = MODULO_BY_SLUG.get(slug_normalizado)
    
    if not modulo_config:
        flash(f'Erro: Módulo "{modulo_nome}" não encontrado no mapeamento.', 'danger')
        return redirect(url_for('modulos'))

    db_field = modulo_config['field']
    
    # 1. VERIFICA DEPENDÊNCIA
    dependency_field = modulo_config.get('dependency_field')
    if dependency_field and not progresso.get(dependency_field, False):
        flash('Você deve completar o módulo anterior primeiro para registrar a conclusão deste.', 'warning')
        return redirect(url_for('modulos'))

    # 2. ATUALIZA o campo no documento de progresso do usuário no Firestore
    try:
        progresso_ref = db.collection('progresso').document(user_id)
        
        # Atualiza o campo específico no documento
        progresso_ref.update({
            db_field: True
        })
        
        # Encontra o próximo módulo (lógica de redirecionamento permanece a mesma)
        proximo_modulo_order = modulo_config['order'] + 1
        proximo_modulo = next((m for m in MODULO_CONFIG if m['order'] == proximo_modulo_order), None)
        
        if proximo_modulo:
            flash(f'Módulo "{modulo_config["title"]}" concluído com sucesso! Prossiga para o próximo: {proximo_modulo["title"]}', 'success')
            return redirect(url_for('conteudo_dinamico', modulo_slug=proximo_modulo['slug']))
        else:
            flash(f'Módulo "{modulo_config["title"]}" concluído com sucesso! Você finalizou o curso!', 'success')
        
    except Exception as e:
        flash(f'Erro ao concluir o módulo: {e}', 'danger')
        
    return redirect(url_for('modulos'))


# =========================================================
# 9. EXECUÇÃO
# =========================================================

if __name__ == '__main__':
    # Roda o servidor de desenvolvimento
    app.run(debug=True)
