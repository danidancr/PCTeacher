from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import os
from functools import wraps
from datetime import datetime
import json # NOVO: Importa json para manipular a chave de serviço

import firebase_admin 
from firebase_admin import credentials, firestore, auth


# =========================================================
# 1. CONFIGURAÇÃO GERAL
# =========================================================
app = Flask(__name__)

# Configurações de segurança
# Em produção, o Render fornecerá a 'SECRET_KEY'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sua_chave_secreta_padrao_muito_longa')
# Define o ID do App para o uso no Frontend (Módulo 6 JS/Firestore)
# OBS: O ID do projeto (pc-teacher-6c75f) é o mais seguro, mas para o seu modelo de FS, 'prod' é suficiente.
APP_ID_FOR_FIREBASE = os.environ.get('APP_ID_FIREBASE', 'prod') 


# =========================================================
# 1.1 CONFIGURAÇÃO FIREBASE ADMIN SDK (NOVO)
# =========================================================
db = None # Inicializa db como None
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
# 3. HELPERS E DECORATORS (REVISADOS)
# =========================================================

# --- CONFIGURAÇÃO ESTÁTICA DOS MÓDULOS (Módulo 6 adicionado) ---
MODULO_CONFIG = [
    {
        'title': '1. Introdução ao Pensamento Computacional',
        'field': 'introducao_concluido',
        'slug': 'introducao',
        'template': 'conteudo-introducao.html', 
        'order': 1,
        'description': 'Entenda o que é o Pensamento Computacional, seus pilares e por que ele é crucial para o futuro.',
        'lessons': 1, 'exercises': 5, 'dependency_field': None,
        'project_field': 'objetivo_geral' ## NOVO: Campo de projeto associado
    },
    {
        'title': '2. Decomposição',
        'field': 'decomposicao_concluido',
        'slug': 'decomposicao',
        'template': 'conteudo-decomposicao.html', 
        'order': 2,
        'description': 'Aprenda a quebrar problemas complexos em partes menores e gerenciáveis.',
        'lessons': 1, 'exercises': 5, 'dependency_field': 'introducao_concluido',
        'project_field': 'decomposicao' ## NOVO: Campo de projeto associado
    },
    {
        'title': '3. Reconhecimento de Padrões',
        'field': 'reconhecimento_padroes_concluido',
        'slug': 'rec-padrao',
        'template': 'conteudo-rec-padrao.html', 
        'order': 3,
        'description': 'Identifique similaridades e tendências para simplificar a resolução de problemas.',
        'lessons': 1, 'exercises': 5, 'dependency_field': 'decomposicao_concluido',
        'project_field': 'reconhecimento_padroes' ## NOVO: Campo de projeto associado
    },
    {
        'title': '4. Abstração',
        'field': 'abstracao_concluido',
        'slug': 'abstracao',
        'template': 'conteudo-abstracao.html', 
        'order': 4,
        'description': 'Foque apenas nas informações importantes, ignorando detalhes irrelevantes.',
        'lessons': 1, 'exercises': 5, 'dependency_field': 'reconhecimento_padroes_concluido',
        'project_field': 'abstracao' ## NOVO: Campo de projeto associado
    },
    {
        'title': '5. Algoritmos',
        'field': 'algoritmo_concluido',
        'slug': 'algoritmo',
        'template': 'conteudo-algoritmo.html', 
        'order': 5,
        'description': 'Desenvolva sequências lógicas e organizadas para resolver problemas de forma eficaz.',
        'lessons': 1, 'exercises': 5, 'dependency_field': 'abstracao_concluido',
        'project_field': 'algoritmo' ## NOVO: Campo de projeto associado
    },
    {
        'title': '6. Projeto Final',
        'field': 'projeto_final_concluido',
        'slug': 'projeto-final',
        'template': 'conteudo-projeto-final.html', 
        'order': 6,
        'description': 'Aplique todos os pilares do PC para solucionar um desafio prático de sala de aula.',
        'lessons': 1, 'exercises': 0, 'dependency_field': 'algoritmo_concluido',
        'project_field': None ## Módulo final não tem campo de salvamento, só de resumo
    },
]

MODULO_BY_SLUG = {m['slug']: m for m in MODULO_CONFIG}


def get_firestore_doc(collection_name, doc_id):
    """Auxiliar para buscar um documento no Firestore e retornar como dict."""
    if not db: return None
    doc_ref = db.collection(collection_name).document(str(doc_id))
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        data['id'] = doc.id # Adiciona o ID do documento ao dict
        return data
    return None

## NOVO: Helper para o caminho padronizado do projeto
def get_project_doc_ref(user_id):
    """Retorna a referência para o documento principal do projeto do usuário."""
    if not db: return None
    # Estrutura: artifacts / [APP_ID] / users / [userId] / project_data / main_project
    # Isso corresponde ao que o JS no frontend está esperando.
    return db.collection('artifacts').document(APP_ID_FOR_FIREBASE).collection('users').document(user_id).collection('project_data').document('main_project')

def usuario_logado():
    """Retorna o objeto (dict) Usuario logado ou None, buscando no Firestore."""
    if 'usuario_id' in session:
        # Busca o usuário pelo ID armazenado na sessão
        user_data = get_firestore_doc('usuarios', session['usuario_id'])
        
        if user_data:
            # Busca o progresso associado (se existir)
            progresso_data = get_firestore_doc('progresso', session['usuario_id'])
            # Anexa o progresso ao objeto do usuário para manter a compatibilidade
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

# =========================================================
# 4. ROTAS DE AUTENTICAÇÃO (REVISADAS)
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
        
        # 1. Verifica se o e-mail já existe (Firestore Query)
        email_exists_query = db.collection('usuarios').where('email', '==', email).limit(1).stream()
        email_exists = next(email_exists_query, None)
        
        if email_exists:
            flash('Este e-mail já está cadastrado. Tente fazer o login.', 'danger')
            return render_template('cadastro.html', nome_for_form=nome, email_for_form=email)

        # 2. Cria novo usuário no Firebase Authentication (Recomendado) e Firestore
        try:
            # 2.1 Criar no Firebase Authentication (para login seguro)
            # Isso gera um UID (ID do usuário) único
            user_auth = auth.create_user(email=email, password=senha, display_name=nome)
            user_id = user_auth.uid
            
            # 2.2 Salvar dados no Firestore (Coleção 'usuarios')
            novo_usuario_data = {
                'nome': nome,
                'email': email,
                'senha_hash': generate_password_hash(senha), # Mantém o hash da senha por compatibilidade, mas o Auth do Firebase deve ser a fonte de verdade
                'instituicao': '',
                'telefone': '',
                'cargo': 'Professor(a)',
                'created_at': firestore.SERVER_TIMESTAMP # Para registro de criação
            }
            # Usa o UID do Auth como ID do documento no Firestore
            db.collection('usuarios').document(user_id).set(novo_usuario_data)
            
            # 2.3 Cria um registro de progresso (Coleção 'progresso')
            # O progresso é um documento separado, usando o mesmo UID
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
            # Em caso de falha de criação, tente limpar o registro
            # Nota: O Firebase Auth lida com a maior parte da transação de forma atômica
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

# A rota /logout permanece a mesma, pois só usa o Flask session
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
# 5. ROTAS DE ÁREA RESTRITA E PERFIL (REVISADAS)
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
        user_id = usuario['id'] # Obtém o ID/UID do usuário logado
        
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        institution = request.form.get('institution')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        tem_erro = False
        
        try:
            # 1. Dicionário para atualização no Firestore
            update_data = {}
            
            # 2. Checa e atualiza E-mail
            if email != usuario['email']:
                # Verifica se o novo e-mail já existe para outro usuário (Firestore Query)
                email_existente_query = db.collection('usuarios').where('email', '==', email).limit(1).stream()
                email_existente = next(email_existente_query, None)
                
                # Garante que, se o e-mail existir, não é o documento do usuário atual
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
                    # MUDANÇA: Atualiza no Firebase Authentication E no Firestore (para o hash)
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
            # Retorna o template para não perder os dados do formulário
            return render_template('perfil.html', user=usuario) 

    # Lógica GET: A função usuario_logado já retorna o usuário atualizado
    return render_template('perfil.html', user=usuario)

@app.route('/progresso')
@requires_auth
def progresso():
    usuario = usuario_logado()
    # MUDANÇA: progresso_db agora é um dicionário contido dentro do objeto usuario
    progresso_db = usuario.get('progresso', {}) 
    
    progresso_data = calculate_progress(progresso_db) 

    context = {
        'user': usuario,
        'title': "Meu Progresso",
        'progresso_data': progresso_data 
    }
    
    return render_template('progresso.html', **context)


# =========================================================
# 6. ROTAS DE CERTIFICADO (REVISADAS)
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
    
    latex_content = generate_latex_certificate(nome_completo, data_conclusao_str, carga_horaria)
    
    return Response(
        latex_content,
        mimetype='application/x-tex',
        headers={'Content-Disposition': f'attachment;filename=Certificado_{nome_completo.replace(" ", "_")}.tex'}
    )


# =========================================================
# 8. ROTAS DE CONTEÚDO DE CURSO (REVISADAS)
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
    user_id = usuario['id'] # UID do Firestore
    
    if not request.is_json:
        return jsonify({'success': False, 'message': 'Requisição deve ser JSON.'}), 400
        
    data = request.get_json() 
    
    # AJUSTADO: Usa o campo 'project_field' do MODULO_CONFIG para saber qual chave salvar
    modulo_config = MODULO_BY_SLUG.get(modulo_slug)
    if not modulo_config or not modulo_config.get('project_field'):
        return jsonify({'success': False, 'message': 'Módulo ou campo de projeto não configurado.'}), 400
        
    project_field_name = modulo_config['project_field']
    # A resposta deve vir no JSON com a chave do campo de projeto
    project_idea = data.get(project_field_name) 

    if not project_idea or len(project_idea.strip()) < 10:
        return jsonify({'success': False, 'message': 'Resposta muito curta ou ausente.'}), 400

    # AJUSTADO: Usa a referência padronizada do projeto
    project_ref = get_project_doc_ref(user_id)

    try:
        # Cria um dicionário para a atualização (ex: {'decomposicao': 'minha resposta'})
        update_data = {
            project_field_name: project_idea,
            f'data_atualizacao_{modulo_slug}': firestore.SERVER_TIMESTAMP 
        }
        
        # Use set(data, merge=True) para criar o documento (project_data/main_project) se não existir ou atualizar se existir
        project_ref.set(update_data, merge=True)
        
        return jsonify({'success': True, 'message': 'Ideia de projeto salva com sucesso!'})
    
    except Exception as e:
        print(f"Erro ao salvar projeto do módulo {modulo_slug}: {e}") 
        return jsonify({'success': False, 'message': f'Erro interno ao salvar no DB: {str(e)}'}), 500


@app.route('/concluir-modulo/<string:modulo_nome>', methods=['POST'])
@requires_auth
def concluir_modulo(modulo_nome):
    # Lógica de conclusão de módulo (permanece a mesma)
    usuario = usuario_logado()
    user_id = usuario['id']
    progresso = usuario.get('progresso', {}) # Progresso como dicionário
    
    slug_normalizado = modulo_nome.replace('_', '-')
    modulo_config = MODULO_BY_SLUG.get(slug_normalizado)
    
    if not modulo_config:
        flash(f'Erro: Módulo "{modulo_nome}" não encontrado no mapeamento.', 'danger')
        return redirect(url_for('modulos'))

    db_field = modulo_config['field']
    
    # 1. VERIFICA DEPENDÊNCIA (usa o dicionário 'progresso')
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
        else:
            flash(f'Módulo "{modulo_config["title"]}" concluído com sucesso! Você finalizou o curso!', 'success')
        
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
    
    # 2. Verifica a dependência (lógica de desbloqueio)
    dependency_field = modulo_config.get('dependency_field')
    if dependency_field and not progresso.get(dependency_field, False):
        flash(f'Você deve completar o módulo anterior primeiro.', 'warning')
        return redirect(url_for('modulos'))
        
    # 3. LÓGICA DE CARREGAMENTO DAS RESPOSTAS DO PROJETO
    
    # AJUSTADO: Carrega o documento 'main_project' para todos os módulos (1-5 para pré-preenchimento, 6 para resumo)
    project_doc_ref = get_project_doc_ref(user_id)
    project_doc_snap = project_doc_ref.get()
    project_data = project_doc_snap.to_dict() if project_doc_snap.exists else {}

    extra_context = {}
    
    if modulo_slug == 'projeto-final':
        ## NOVO: Lógica de Carregamento para o Módulo Final (Módulo 6)
        
        # Cria uma lista ordenada com os dados do projeto para o template, usando os campos do MODULO_CONFIG
        respostas_projeto_ordenadas = []
        for mod in MODULO_CONFIG:
            if mod.get('project_field'):
                field_name = mod['project_field']
                respostas_projeto_ordenadas.append({
                    'title': mod['title'],
                    'slug': mod['slug'],
                    # Puxa a resposta do documento consolidado (project_data)
                    'resposta': project_data.get(field_name, 'Nenhuma resposta salva.'),
                    'is_saved': field_name in project_data
                })
        
        # Este contexto não é estritamente necessário se o frontend usar o JS/Firestore, 
        # mas mantém a opção de renderização via Flask:
        extra_context['respostas_projeto'] = respostas_projeto_ordenadas 

    else:
        # Para outros módulos (1 a 5), pré-preenche o campo de texto se houver resposta salva
        project_field = modulo_config.get('project_field')
        if project_field:
            extra_context = {
                'resposta_anterior': project_data.get(project_field, '')
            }

    ## NOVO: Injeta as configurações do Firebase Client SDK no template
    firebase_client_config = os.environ.get('FIREBASE_CLIENT_CONFIG', None)
    
    extra_context['__firebase_config'] = firebase_client_config
    extra_context['__initial_auth_token'] = auth.create_custom_token(user_id).decode()
    extra_context['__app_id'] = APP_ID_FOR_FIREBASE
        
    # 4. Renderiza o template do módulo
    template_name = modulo_config['template']
    return render_template(template_name, user=usuario, progresso=progresso, modulo=modulo_config, **extra_context)


# =========================================================
# 9. EXECUÇÃO
# =========================================================

if __name__ == '__main__':
    # Roda o servidor de desenvolvimento
    app.run(debug=True)
