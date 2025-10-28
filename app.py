from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import os
from functools import wraps
from datetime import datetime
import json
import io # Necessário para gerar o PDF na memória

# Importação para geração de PDF (WeasyPrint)
try:
    from weasyprint import HTML, CSS
    print("INFO: WeasyPrint importado com sucesso.")
    WEASYPRINT_AVAILABLE = True
except ImportError:
    print("AVISO: WeasyPrint não está instalado. A rota de PDF não funcionará.")
    WEASYPRINT_AVAILABLE = False
except Exception as e:
    print(f"AVISO: WeasyPrint falhou ao carregar: {e}. A rota de PDF não funcionará.")
    WEASYPRINT_AVAILABLE = False


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
# NOTA: A lógica para carregar as credenciais (via variável de ambiente ou arquivo)
# deve permanecer exatamente como você a configurou para garantir a conexão.
try:
    FIREBASE_SERVICE_ACCOUNT_JSON = os.environ.get('FIREBASE_CONFIG_JSON')
    
    if FIREBASE_SERVICE_ACCOUNT_JSON:
        cred_json = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
        cred = credentials.Certificate(cred_json)
        print("INFO: Credenciais carregadas da variável de ambiente 'FIREBASE_CONFIG_JSON'.")
    else:
        cred = credentials.Certificate('serviceAccountKey.json')
        print("INFO: Credenciais carregadas do arquivo local 'serviceAccountKey.json'.")
        
except FileNotFoundError:
    print("AVISO: Arquivo 'serviceAccountKey.json' não encontrado localmente.")
    cred = None
except Exception as e:
    print(f"ERRO ao carregar credenciais: {e}")
    cred = None

if not firebase_admin._apps and cred:
    firebase_admin.initialize_app(cred, {
        'projectId': "pc-teacher-6c75f",
    })
    db = firestore.client()
    print("INFO: Firebase Admin SDK inicializado com sucesso.")
elif not firebase_admin._apps:
    print("ERRO CRÍTICO: Firebase Admin SDK não foi inicializado. Verifique as credenciais.")


# =========================================================
# 3. HELPERS E DECORATORS
# =========================================================

# --- CONFIGURAÇÃO ESTÁTICA DOS MÓDULOS ---
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
    doc_ref = db.collection(collection_name).document(str(doc_id))
    doc = doc_ref.get()
    if doc.exists:
        data = doc.to_dict()
        data['id'] = doc.id 
        return data
    return None

def get_projeto_usuario(user_id):
    """Busca o documento de projeto do usuário. Retorna um dict ou um dict vazio."""
    projeto_data = get_firestore_doc('projetos', user_id)
    
    # Ajustei as chaves para corresponder às usadas nos templates (sem caracteres especiais)
    default_data = {
        'id': user_id, # Adicionado ID para garantir que ele exista
        'nome_projeto': '',
        'problema': '', # Ajustado para 'problema' (mais comum do que 'objetivo' nos templates)
        'publico_alvo': '',  # Ajustado de 'publico-alvo' para 'publico_alvo' (melhor em Python/Jinja)
        'decomposicao': '', # Ajustado de 'decomposição'
        'padroes': '', # Ajustado de 'rec-padrão'
        'abstracao': '',
        'algoritmo': ''
    }

    if projeto_data:
        # Mescla com os dados padrão para garantir que todas as chaves estejam presentes
        # Mapeamento de chaves antigas para novas (se necessário):
        if 'objetivo' in projeto_data: projeto_data['problema'] = projeto_data.pop('objetivo')
        if 'publico-alvo' in projeto_data: projeto_data['publico_alvo'] = projeto_data.pop('publico-alvo')
        if 'decomposição' in projeto_data: projeto_data['decomposicao'] = projeto_data.pop('decomposição')
        if 'rec-padrão' in projeto_data: projeto_data['padroes'] = projeto_data.pop('rec-padrão')

        default_data.update(projeto_data)
        return default_data
        
    return default_data


def usuario_logado():
    """Retorna o objeto (dict) Usuario logado ou None, buscando no Firestore."""
    if 'usuario_id' in session:
        user_id = session['usuario_id']
        user_data = get_firestore_doc('usuarios', user_id)
        
        if user_data:
            # 1. Carrega o progresso
            progresso_data = get_firestore_doc('progresso', user_id)
            user_data['progresso'] = progresso_data if progresso_data else {}
            
            # 2. Carrega os dados do Projeto
            user_data['projeto'] = get_projeto_usuario(user_id) 

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

# ... (A função calculate_progress permanece a mesma) ...
def calculate_progress(progresso_db):
    """Calcula todas as métricas de progresso do curso."""
    # (A lógica de cálculo de progresso permanece a mesma)
    
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
# ... (Fim da função calculate_progress) ...

# Lógica para gerar o certificado (permanece a mesma)
def generate_latex_certificate(nome_completo, data_conclusao_str, carga_horaria):
    """Gera o conteúdo LaTeX para o certificado."""
    # (Template LaTeX omitido para brevidade, mas permanece inalterado)
    latex_template = r"""
\documentclass[10pt, a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[portuguese]{babel}
\usepackage{geometry}
\usepackage{fancybox}
\usepackage{graphicx}
\usepackage{color}

\geometry{
    a4paper,
    landscape,
    margin=1.5cm
}

\pagestyle{empty}

\begin{document}
\begin{center}
\fcolorbox{black}{white}{\setlength{\fboxsep}{1cm}\fbox{
\begin{minipage}{0.95\textwidth}
\centering

\vspace{1cm}
{\Huge\bfseries Certificado de Conclusão}

\vspace{0.8cm}
{\Large Certificamos que}

\vspace{1cm}
{\color{blue}\Huge\bfseries %s}

\vspace{0.5cm}
{\Large Concluiu o curso online:}

\vspace{0.8cm}
{\huge\bfseries Pensamento Computacional para Professores}

\vspace{0.8cm}
{\Large com carga horária total de \textbf{%d horas}.}

\vspace{1.5cm}
{\Large Emitido em Manaus, Amazonas, em %s.}

\vspace{2cm}
\begin{tabular}{cc}
\begin{minipage}{0.4\textwidth}
\centering
\hrule
\vspace{0.2cm}
\small Assinatura da Coordenação
\end{minipage}
&
\begin{minipage}{0.4\textwidth}
\centering
\hrule
\vspace{0.2cm}
\small Assinatura do Instrutor
\end{minipage}
\end{tabular}

\end{minipage}
}}
\end{center}
\end{document}
""" % (nome_completo, carga_horaria, data_conclusao_str)
    
    return latex_template

# =========================================================
# 4. ROTAS DE AUTENTICAÇÃO
# (Mantidas as rotas de autenticação)
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
        
        # 1. Verifica se o e-mail já existe
        email_exists_query = db.collection('usuarios').where('email', '==', email).limit(1).stream()
        email_exists = next(email_exists_query, None)
        
        if email_exists:
            flash('Este e-mail já está cadastrado. Tente fazer o login.', 'danger')
            return render_template('cadastro.html', nome_for_form=nome, email_for_form=email)

        # 2. Cria novo usuário no Firebase Auth e Firestore
        try:
            user_auth = auth.create_user(email=email, password=senha, display_name=nome)
            user_id = user_auth.uid
            
            # Salvar dados no Firestore (Coleção 'usuarios')
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

            # === AJUSTE DE PROJETOS: CRIAÇÃO INICIAL DO DOCUMENTO 'PROJETOS'
            # (Usando as chaves padronizadas: problema, publico_alvo, decomposicao, etc.)
            novo_projeto_data = {
                'nome_projeto': '',
                'objetivo': '', # Ajustado
                'publico_alvo': '', # Ajustado
                'decomposicao': '',
                'otimizacao_padrao': '',
                'abstracao': '',
                'algoritmo': ''
            }
            db.collection('projetos').document(user_id).set(novo_projeto_data)
            
            # Cria um registro de progresso (Coleção 'progresso')
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
        
        # 1. Busca o usuário pelo e-mail
        user_query = db.collection('usuarios').where('email', '==', email).limit(1).stream()
        usuario_doc = next(user_query, None)
        
        if usuario_doc:
            usuario_data = usuario_doc.to_dict()
            usuario_data['id'] = usuario_doc.id 
            
            # 2. Verifica a senha (usando o hash armazenado por compatibilidade)
            if 'senha_hash' in usuario_data and check_password_hash(usuario_data['senha_hash'], senha):
                session['usuario_id'] = usuario_data['id'] 
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
# 4.1 INFORMAÇÃO
# (Mantidas as rotas de informação)
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
# (Mantidas as rotas de área restrita)
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
# (Mantidas as rotas de certificado)
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
        headers={'Content-Disposition': f'attachment:filename=Certificado_{nome_completo.replace(" ", "_")}.tex'}
    )


# =========================================================
# 7. ROTAS DE GERENCIAMENTO DE PROJETOS (NOVAS/REVISADAS)
# =========================================================

@app.route('/projeto/salvar', methods=['POST'])
@requires_auth
def salvar_projeto():
    """
    Recebe os dados do projeto (parciais ou totais) e salva no Firestore.
    Esta rota deve ser usada pelos formulários em 'conteudo-<modulo>.html'.
    """
    usuario = usuario_logado()
    user_id = usuario['id']
    
    data = request.form.to_dict() # Captura todos os dados do formulário
    
    # Padroniza as chaves do formulário (Ex: 'decomposicao' para 'decomposicao')
    update_data = {}
    for key, value in data.items():
        if key in ['nome_projeto', 'objetivo', 'publico_alvo', 'decomposicao', 'otimizacao_padrao', 'abstracao', 'algoritmo']:
            update_data[key] = value.strip()
    
    if not update_data:
        # Retorna um JSON de erro se for uma chamada AJAX, se não, faz o flash.
        if request.is_json or request.accept_mimetypes.accept_json:
            return jsonify({'success': False, 'message': 'Nenhum dado válido para salvar.'}), 400
        flash('Nenhum dado válido enviado para salvar o projeto.', 'warning')
        return redirect(request.referrer or url_for('dashboard')) 

    try:
        # Atualiza o documento de projeto.
        db.collection('projetos').document(user_id).update(update_data)
        
        # Resposta otimizada para chamadas AJAX (salvamento automático)
        if request.is_json or request.accept_mimetypes.accept_json:
            return jsonify({'success': True, 'message': 'Salvo automaticamente.'})
        
        flash('Dados do projeto salvos com sucesso!', 'success')
        return redirect(request.referrer or url_for('dashboard'))
        
    except Exception as e:
        if request.is_json or request.accept_mimetypes.accept_json:
             return jsonify({'success': False, 'message': f'Erro ao salvar: {str(e)}'}), 500
        flash(f'Erro ao salvar os dados do projeto: {str(e)}', 'danger')
        return redirect(request.referrer or url_for('dashboard'))


# =========================================================
# 7.1. ROTA DE DOWNLOAD PDF (NOVA)
# =========================================================
@app.route('/download-projeto-pdf/<string:projeto_id>')
@requires_auth
def download_projeto_pdf(projeto_id):
    """Gera o projeto final do usuário como um arquivo PDF."""
    
    if not WEASYPRINT_AVAILABLE:
        flash('A função de geração de PDF não está disponível no servidor.', 'danger')
        return redirect(url_for('conteudo_dinamico', modulo_slug='projeto-final'))
        
    # Verifica se o ID corresponde ao usuário logado (segurança)
    usuario = usuario_logado()
    if usuario['id'] != projeto_id:
        flash('Acesso negado ao projeto solicitado.', 'danger')
        return redirect(url_for('dashboard'))
        
    # Carrega os dados do projeto
    projeto_data = usuario.get('projeto', {})
    
    if not projeto_data:
        flash('Nenhum dado de projeto encontrado para download.', 'warning')
        return redirect(url_for('conteudo_dinamico', modulo_slug='projeto-final'))

    try:
        # 1. Renderiza o HTML limpo para o PDF
        # *Você precisará criar o template 'pdf_template.html' para um layout otimizado*
        html_content = render_template(
            'pdf_template.html', 
            projeto_data=projeto_data, 
            user=usuario
        )

        # 2. Gera o PDF na memória
        pdf_file = HTML(string=html_content).write_pdf()
        
        # 3. Nome do arquivo
        nome_projeto_limpo = projeto_data.get('nome_projeto', 'Projeto_Final').replace(' ', '_').replace('.', '')
        filename = f"{nome_projeto_limpo}_PC_Completo.pdf"

        # 4. Retorna o arquivo como anexo
        return send_file(
            io.BytesIO(pdf_file), 
            mimetype='application/pdf', 
            as_attachment=True, 
            download_name=filename
        )
        
    except Exception as e:
        print(f"ERRO DE GERAÇÃO DE PDF: {e}")
        flash(f'Erro ao gerar o PDF. Verifique a configuração do WeasyPrint ou o template: {str(e)}', 'danger')
        return redirect(url_for('conteudo_dinamico', modulo_slug='projeto-final'))


# =========================================================
# 8. ROTAS DE CONTEÚDO DE CURSO
# =========================================================

@app.route('/modulos')
@requires_auth
def modulos():
    usuario = usuario_logado()
    progresso = usuario.get('progresso', {})
    
    progresso_data = calculate_progress(progresso)
    modulos_list = progresso_data.get('modules', []) 

    return render_template('modulos.html', user=usuario, modulos=modulos_list, progresso_data=progresso_data)


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

    # 2. ATUALIZA o campo de progresso no Firestore
    try:
        progresso_ref = db.collection('progresso').document(user_id)
        
        progresso_ref.update({
            db_field: True
        })
        
        # Lógica de redirecionamento
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
    progresso = usuario.get('progresso', {})
    projeto_data = usuario.get('projeto', {}) # Pega os dados do projeto
    
    modulo_config = MODULO_BY_SLUG.get(modulo_slug)

    if not modulo_config:
        flash('Módulo de conteúdo não encontrado.', 'danger')
        return redirect(url_for('modulos'))
    
    # 1. Verifica a dependência (lógica de desbloqueio)
    dependency_field = modulo_config.get('dependency_field')
    if dependency_field and not progresso.get(dependency_field, False):
        flash(f'Você deve completar o módulo anterior primeiro.', 'warning')
        return redirect(url_for('modulos'))
        
    # 2. Renderiza o template do módulo
    template_name = modulo_config['template']
    
    # Passa os dados do projeto para que o frontend possa pré-preencher formulários.
    return render_template(
        template_name, 
        user=usuario, 
        progresso=progresso, 
        modulo=modulo_config,
        projeto_data=projeto_data 
    )


#==========================================================
# add algo
#==========================================================

def get_firebase_client_config():
    """Retorna as configurações do Firebase Client SDK.
        As chaves públicas devem ser armazenadas em variáveis de ambiente.
    """
    # (Mantido, mas será menos crítico se o salvamento for via Flask)
    return {
        "apiKey": os.environ.get("FIREBASE_API_KEY", "SUA_API_KEY_AQUI"),
        "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN", "pc-teacher-6c75f.firebaseapp.com"),
        "projectId": os.environ.get("FIREBASE_PROJECT_ID", "pc-teacher-6c75f"),
        "storageBucket": os.environ.get("FIREBASE_STORAGE_BUCKET", "pc-teacher-6c75f.appspot.com"),
        "messagingSenderId": os.environ.get("FIREBASE_MESSAGING_SENDER_ID", "SEU_SENDER_ID"),
        "appId": os.environ.get("FIREBASE_APP_ID", "SEU_APP_ID")
    }


@app.context_processor
def inject_globals():
    """Injeta variáveis que devem estar disponíveis em todos os templates."""
    return dict(firebase_config=get_firebase_client_config())


# =========================================================
# 9. EXECUÇÃO
# =========================================================

if __name__ == '__main__':
    app.run(debug=True)
