from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
import os
from functools import wraps
from datetime import datetime
import json
from collections import OrderedDict # Para garantir a ordem no MODULO_CONFIG

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
cred = None
if not firebase_admin._apps:
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
    except Exception as e:
        print(f"ERRO ao carregar credenciais: {e}")

# Inicializa o Firebase apenas se as credenciais foram carregadas com sucesso
if not firebase_admin._apps and cred:
    firebase_admin.initialize_app(cred, {
        'projectId': "pc-teacher-6c75f", # SUBSTITUA PELO SEU PROJECT_ID
    })
    db = firestore.client()
    print("INFO: Firebase Admin SDK inicializado com sucesso.")
elif not firebase_admin._apps and not hasattr(app, 'db'):
    # Define um DB dummy para evitar erros, mas as rotas falharão
    class DummyDB:
        def __init__(self): print("ERRO CRÍTICO: Firebase Admin SDK não foi inicializado. Funções DB falharão.")
        def collection(self, name): return self
        def document(self, doc_id): return self
        def set(self, data, merge=False): pass
        def update(self, data): pass
        def get(self): return self
        def exists(self): return False
        def stream(self): return []
        def where(self, field, op, value): return self
        def limit(self, count): return self
    db = DummyDB()

# =========================================================
# 3. HELPERS E DECORATORS
# =========================================================

# --- CONFIGURAÇÃO ESTÁTICA DOS MÓDULOS ---
# Adicionado 'introducao' e 'projeto-final' para mapeamento
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
        'template': 'conteudo-algoritmo.html', 
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


def get_firestore_doc(collection_name, doc_id):
    """Auxiliar para buscar um documento no Firestore e retornar como dict."""
    try:
        doc_ref = db.collection(collection_name).document(str(doc_id))
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            data['id'] = doc.id # Adiciona o ID do documento ao dict
            return data
        return None
    except Exception as e:
        print(f"Erro ao buscar documento {doc_id} em {collection_name}: {e}")
        return None

def usuario_logado():
    """Retorna o objeto (dict) Usuario logado ou None, buscando no Firestore."""
    if 'usuario_id' in session:
        # Busca o usuário pelo ID armazenado na sessão
        user_data = get_firestore_doc('usuarios', session['usuario_id'])
        
        if user_data:
            # Busca o progresso associado (se existir)
            progresso_data = get_firestore_doc('progresso', session['usuario_id'])
            user_data['progresso'] = progresso_data if progresso_data else {}
            # Anexa o usuário logado ao objeto global `g` do Flask
            g.user = user_data 
            return user_data
    
    g.user = None
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
    """Calcula todas as métricas de progresso do curso."""
    
    total_modules = len(MODULO_CONFIG)
    completed_modules = 0
    total_lessons = sum(m['lessons'] for m in MODULO_CONFIG)
    total_exercises = sum(m['exercises'] for m in MODULO_CONFIG)
    completed_lessons = 0
    completed_exercises = 0
    
    dynamic_modules = []
    
    for module_config in MODULO_CONFIG:
        db_field = module_config['field']
        
        is_completed = progresso_db.get(db_field, False) 
        
        dependency_field = module_config.get('dependency_field')
        
        if dependency_field is None:
            is_unlocked_for_current_module = True
        else:
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

def get_resposta_from_array(answers_array, target_id):
    """
    Helper para extrair a resposta pelo ID dentro de um array de objetos.
    Usado na lógica de carregamento do Projeto Final.
    """
    if not answers_array or not isinstance(answers_array, list):
        return 'Nenhuma resposta salva.'
    for item in answers_array:
        if item.get('id') == target_id:
            return item.get('resposta', 'Resposta vazia.')
    return 'Nenhuma resposta salva.'

# =========================================================
# 4. ROTAS DE AUTENTICAÇÃO
# =========================================================

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    usuario = usuario_logado()
    if usuario:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nome = request.form.get('nome')
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        try:
            # 1. Verifica se o e-mail já existe
            email_exists_query = db.collection('usuarios').where('email', '==', email).limit(1).stream()
            email_exists = next(email_exists_query, None)
            
            if email_exists:
                flash('Este e-mail já está cadastrado. Tente fazer o login.', 'danger')
                return render_template('cadastro.html', nome_for_form=nome, email_for_form=email)

            # 2. Cria novo usuário no Firebase Authentication
            user_auth = auth.create_user(email=email, password=senha, display_name=nome)
            user_id = user_auth.uid
            
            # 3. Salvar dados no Firestore (Coleção 'usuarios')
            novo_usuario_data = {
                'nome': nome,
                'email': email,
                'senha_hash': generate_password_hash(senha), # Mantido por compatibilidade
                'instituicao': '',
                'telefone': '',
                'cargo': 'Professor(a)',
                'created_at': firestore.SERVER_TIMESTAMP
            }
            db.collection('usuarios').document(user_id).set(novo_usuario_data)
            
            # 4. Cria um registro de progresso (Coleção 'progresso')
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
        
        try:
            # 1. Busca o usuário pelo e-mail
            user_query = db.collection('usuarios').where('email', '==', email).limit(1).stream()
            usuario_doc = next(user_query, None)
            
            if usuario_doc:
                usuario_data = usuario_doc.to_dict()
                usuario_data['id'] = usuario_doc.id # O ID é o UID/Doc ID
                
                # 2. Verifica a senha (usando o hash armazenado por compatibilidade)
                if 'senha_hash' in usuario_data and check_password_hash(usuario_data['senha_hash'], senha):
                    session['usuario_id'] = usuario_data['id']
                    flash(f'Bem-vindo(a), {usuario_data["nome"]}!', 'success')
                    return redirect(url_for('dashboard'))

        except Exception as e:
            # Captura erros como credenciais inválidas (se estivesse usando o client SDK)
            print(f"Erro de login: {e}")

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
# 4.1 INFORMAÇÃO
# =========================================================

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
        
        try:
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
                    
            # 3. Processa a mudança de senha
            if new_password:
                if new_password != confirm_password:
                    flash("As novas senhas digitadas não coincidem.", 'danger')
                    tem_erro = True
                elif len(new_password) < 6:
                    flash("A nova senha deve ter no mínimo 6 caracteres.", 'danger')
                    tem_erro = True
                else:
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
                
                if not new_password:
                    flash("Dados do perfil atualizados com sucesso!", 'success')
            
            # Recarrega o usuário no g.user/session para refletir as mudanças
            return redirect(url_for('perfil'))
                
        except Exception as e:
            flash(f"Ocorreu um erro inesperado ao salvar: {str(e)}", 'danger')
            return render_template('perfil.html', user=usuario) 

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

# Rota gerar_certificado (assumindo que generate_latex_certificate existe)
# ...

# =========================================================
# 7. ROTAS DE CONTEÚDO DE CURSO
# =========================================================

@app.route('/modulos')
@requires_auth
def modulos():
    usuario = usuario_logado()
    progresso = usuario.get('progresso', {})
    
    progresso_data = calculate_progress(progresso)
    modulos_list = progresso_data.get('modules', []) 

    return render_template('modulos.html', user=usuario, modulos=modulos_list, progresso_data=progresso_data)


@app.route('/salvar-projeto-array/<string:modulo_slug>', methods=['POST'])
@requires_auth
def salvar_projeto_array_unificado(modulo_slug):
    """
    Rota unificada para salvar o array de perguntas do projeto (M1 a M5) 
    diretamente no documento do projeto do usuário ('projetos/user_project_<uid>').
    """
    usuario = usuario_logado()
    user_id = usuario['id']
    project_doc_id = f'user_project_{user_id}'

    if not request.is_json:
        return jsonify({'success': False, 'message': 'Requisição deve ser JSON.'}), 400
        
    data = request.get_json()
    
    # Mapeamento de slug para campo do Firestore e ID do Módulo
    slug_to_field = {
        'introducao': 'perguntasM1', 
        'decomposicao': 'perguntasM1', # P1 e P2 estão no M1
        'rec-padrao': 'perguntasM2', 
        'abstracao': 'perguntasM4', # P4 e P5 (Abstração) no M3/M4
        'algoritmo': 'perguntasM5', 
    }
    
    db_field = slug_to_field.get(modulo_slug)
    
    if not db_field:
        return jsonify({'success': False, 'message': f'Slug de módulo inválido ou sem mapeamento de salvamento: {modulo_slug}'}), 400

    # O JSON deve conter o array com o nome do campo (ex: 'perguntasM1')
    perguntas_array = data.get(db_field)

    if not perguntas_array or not isinstance(perguntas_array, list):
        return jsonify({'success': False, 'message': 'Dados de perguntas ausentes ou mal-formados.'}), 400

    try:
        project_ref = db.collection('projetos').document(project_doc_id)
        
        # Cria o dicionário de atualização
        update_data = {
            db_field: perguntas_array,
            f'ultimaAtualizacao': firestore.SERVER_TIMESTAMP
        }
        
        # Usa set(data, merge=True) para criar ou atualizar o campo específico
        project_ref.set(update_data, merge=True)
        
        return jsonify({'success': True, 'message': f'Perguntas do Módulo {modulo_slug} salvas com sucesso.'})
    
    except Exception as e:
        print(f"Erro ao salvar array do projeto do módulo {modulo_slug}: {e}")
        return jsonify({'success': False, 'message': f'Erro interno ao salvar no DB: {str(e)}'}), 500


@app.route('/concluir-modulo/<string:modulo_nome>', methods=['POST'])
@requires_auth
def concluir_modulo(modulo_nome):
    usuario = usuario_logado()
    user_id = usuario['id']
    progresso = usuario.get('progresso', {})
    
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

    # 2. ATUALIZA o campo no documento de progresso
    try:
        progresso_ref = db.collection('progresso').document(user_id)
        progresso_ref.update({
            db_field: True
        })
        
        # Encontra o próximo módulo
        proximo_modulo_order = modulo_config['order'] + 1
        proximo_modulo = next((m for m in MODULO_CONFIG if m['order'] == proximo_modulo_order), None)
        
        if proximo_modulo:
            flash(f'Módulo "{modulo_config["title"]}" concluído! Prossiga para o próximo: {proximo_modulo["title"]}', 'success')
        else:
            flash(f'Módulo "{modulo_config["title"]}" concluído! Você finalizou o curso!', 'success')
            
    except Exception as e:
        flash(f'Erro ao concluir o módulo: {e}', 'danger')
        
    return redirect(url_for('modulos'))


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
        
    extra_context = {}
    project_doc_id = f'user_project_{user_id}'
    project_doc = get_firestore_doc('projetos', project_doc_id)

    # 2. LÓGICA DE CARREGAMENTO DE RESPOSTAS (FRONT-END)
    if modulo_slug == 'projeto-final':
        # Mapeamento para carregar TODAS as partes do projeto
        project_parts = [
            # M1: Problema Inicial (P1)
            {'title': 'Módulo 0 - Problema Inicial:', 'id': 'proj-mod0', 'db_array': project_doc.get('perguntasM1', []), 'db_id': 'mod1_p1_problema_inicial'},
            # M1: Decomposição (P2)
            {'title': 'Módulo 1 - Decomposição:', 'id': 'proj-mod1', 'db_array': project_doc.get('perguntasM1', []), 'db_id': 'mod1_p2_decomposicao'},
            # M2: Padrões (P3)
            {'title': 'Módulo 2 - Padrões:', 'id': 'proj-mod2', 'db_array': project_doc.get('perguntasM2', []), 'db_id': 'mod2_p3_padroes_identificados'},
            # M3/M4: Abstração (P6)
            {'title': 'Módulo 3 - Abstração:', 'id': 'proj-mod3', 'db_array': project_doc.get('perguntasM4', []), 'db_id': 'mod4_p6_abstracao_projeto'},
            # M5: Algoritmo (P7)
            {'title': 'Módulo 4 - Algoritmo (Solução):', 'id': 'proj-mod4', 'db_array': project_doc.get('perguntasM5', []), 'db_id': 'mod5_p7_algoritmo_projeto'},
        ]
        
        # Prepara um dicionário para carregar o JS no front-end
        respostas_projeto_js = {}
        for part in project_parts:
            resposta = get_resposta_from_array(part['db_array'], part['db_id'])
            respostas_projeto_js[part['id']] = resposta
            
        extra_context = {'respostas_projeto_js': json.dumps(respostas_projeto_js)}
        
    else:
        # Para Módulos 1-5: Carrega a resposta anterior para preencher o campo de texto
        
        # Mapeamento de slug para campo e ID do DB para pré-preenchimento
        prefill_map = {
            'introducao': {'array': project_doc.get('perguntasM1', []), 'id': 'mod1_p1_problema_inicial'},
            'decomposicao': {'array': project_doc.get('perguntasM1', []), 'id': 'mod1_p2_decomposicao'},
            'rec-padrao': {'array': project_doc.get('perguntasM2', []), 'id': 'mod2_p3_padroes_identificados'},
            'abstracao': {'array': project_doc.get('perguntasM3', []), 'id': 'mod3_p5_dados_essenciais'}, # M3 usa P5 (dados essenciais)
            'algoritmo': {'array': project_doc.get('perguntasM5', []), 'id': 'mod5_p7_algoritmo_projeto'},
        }

        # Abstração (M4) - A P6 (abstração final) é salva aqui, mas o M4 carrega o M4.
        if modulo_slug == 'abstracao':
            prefill_map['abstracao'] = {'array': project_doc.get('perguntasM4', []), 'id': 'mod4_p6_abstracao_projeto'}

        prefill_data = prefill_map.get(modulo_slug)

        resposta_anterior = ''
        if prefill_data:
            resposta_anterior = get_resposta_from_array(prefill_data['array'], prefill_data['id'])
            # Se a resposta for o valor padrão de não salvo, limpa a string
            if resposta_anterior in ['Nenhuma resposta salva.', 'Resposta vazia.']:
                resposta_anterior = ''
            
        extra_context = {
            'resposta_anterior': resposta_anterior
        }

    # 3. Renderiza o template do módulo
    template_name = modulo_config['template']
    return render_template(template_name, user=usuario, progresso=progresso, modulo=modulo_config, **extra_context)


# =========================================================
# 8. EXECUÇÃO
# =========================================================

if __name__ == '__main__':
    app.run(debug=True)
