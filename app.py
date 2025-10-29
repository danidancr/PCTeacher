from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import os
from functools import wraps
from datetime import datetime # Importação essencial
import json
import io 

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
# (Omissão da configuração do Firebase para brevidade, assumindo que está funcionando)
# =========================================================
# ... (Seu código de inicialização do Firebase Admin SDK permanece aqui) ...
try:
    FIREBASE_SERVICE_ACCOUNT_JSON = os.environ.get('FIREBASE_CONFIG_JSON')
    
    if FIREBASE_SERVICE_ACCOUNT_JSON:
        cred_json = json.loads(FIREBASE_SERVICE_ACCOUNT_JSON)
        cred = credentials.Certificate(cred_json)
    else:
        cred = credentials.Certificate('serviceAccountKey.json')
except FileNotFoundError:
    cred = None
except Exception:
    cred = None

if not firebase_admin._apps and cred:
    firebase_admin.initialize_app(cred, {
        'projectId': "pc-teacher-6c75f",
    })
    db = firestore.client()
# ... (Fim da omissão) ...


# =========================================================
# 3. HELPERS E DECORATORS
# (Seu código MODULO_CONFIG, get_firestore_doc, get_projeto_usuario, etc. permanece aqui)
# =========================================================

# --- CONFIGURAÇÃO ESTÁTICA DOS MÓDULOS ---
# ... (MODULO_CONFIG e MODULO_BY_SLUG permanecem aqui) ...
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
    # ... (Os outros módulos permanecem aqui) ...
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
# ... (Seu código helper get_firestore_doc, usuario_logado, requires_auth, calculate_progress, etc. permanece aqui) ...
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
    """
    Busca o documento de projeto do usuário. 
    Retorna um dict com as chaves padronizadas (nome_projeto, objetivo, etc.) ou um dict vazio.
    """
    projeto_data = get_firestore_doc('projetos', user_id)
    
    default_data = {
        'id': user_id, 
        'nome_projeto': '',
        'objetivo': '',
        'publico_alvo': '', 
        'decomposicao': '',
        'rec_padrao': '', 
        'abstracao': '',
        'algoritmo': ''
    }

    if projeto_data:
        if 'otimizacao_padrao' in projeto_data: 
            projeto_data['rec_padrao'] = projeto_data.pop('otimizacao_padrao')
        if 'publico-alvo' in projeto_data: 
            projeto_data['publico_alvo'] = projeto_data.pop('publico-alvo')

        default_data.update(projeto_data)
        return default_data
        
    return default_data


def usuario_logado():
    """Retorna o objeto (dict) Usuario logado ou None, buscando no Firestore."""
    if 'usuario_id' in session:
        user_id = session['usuario_id']
        user_data = get_firestore_doc('usuarios', user_id)
        
        if user_data:
            user_data['progresso'] = get_firestore_doc('progresso', user_id) or {}
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

def generate_latex_certificate(nome_completo, data_conclusao_str, carga_horaria):
    """Gera o conteúdo LaTeX para o certificado."""
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
# 4. ROTAS DE AUTENTICAÇÃO E 5. ROTAS DE ÁREA RESTRITA
# (Omissão das rotas de login/cadastro/perfil/dashboard/etc. para brevidade)
# =========================================================
# ... (Suas rotas de autenticação, perfil e dashboard permanecem aqui) ...

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    # ... (código de cadastro)
    pass
@app.route('/login', methods=['GET', 'POST'])
def login():
    # ... (código de login)
    pass
@app.route('/logout')
def logout():
    # ... (código de logout)
    pass
@app.route('/infor-curso-decomposicao')
def infor_curso_decomposicao():
    # ... (código de infor)
    pass
# ... (outras rotas de infor) ...
@app.route('/')
def index():
    # ... (código de index)
    pass
@app.route('/dashboard')
@requires_auth
def dashboard():
    # ... (código de dashboard)
    pass
@app.route('/perfil', methods=['GET', 'POST']) 
@requires_auth
def perfil():
    # ... (código de perfil)
    pass
@app.route('/progresso')
@requires_auth
def progresso():
    # ... (código de progresso)
    pass
@app.route('/certificado')
@requires_auth
def certificado():
    # ... (código de certificado)
    pass
@app.route('/gerar-certificado')
@requires_auth
def gerar_certificado():
    # ... (código de gerar-certificado)
    pass


# =========================================================
# 7. ROTAS DE GERENCIAMENTO DE PROJETOS
# =========================================================

@app.route('/projeto/salvar', methods=['POST'])
@requires_auth
def salvar_projeto():
    """
    Recebe os dados do projeto (parciais ou totais) e salva no Firestore,
    usando os nomes de variáveis de projeto fornecidos.
    """
    usuario = usuario_logado()
    user_id = usuario['id']
    
    data = request.form.to_dict() # Captura todos os dados do formulário
    
    update_data = {}
    valid_keys = ['nome_projeto', 'objetivo', 'publico_alvo', 'decomposicao', 'rec_padrao', 'abstracao', 'algoritmo']
    
    for key, value in data.items():
        if key in valid_keys:
            update_data[key] = value.strip()
    
    if not update_data:
        if request.is_json or request.accept_mimetypes.accept_json:
            return jsonify({'success': False, 'message': 'Nenhum dado válido para salvar.'}), 400
        flash('Nenhum dado válido enviado para salvar o projeto.', 'warning')
        return redirect(request.referrer or url_for('dashboard')) 

    try:
        db.collection('projetos').document(user_id).update(update_data)
        
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
# 7.1. ROTA DE DOWNLOAD PDF (AJUSTADA)
# =========================================================
@app.route('/download-projeto-pdf/<string:projeto_id>')
@requires_auth
def download_projeto_pdf(projeto_id):
    """Gera o projeto final do usuário como um arquivo PDF."""
    
    if not WEASYPRINT_AVAILABLE:
        flash('A função de geração de PDF não está disponível no servidor.', 'danger')
        return redirect(url_for('conteudo_dinamico', modulo_slug='projeto-final'))
        
    usuario = usuario_logado()
    if usuario['id'] != projeto_id:
        flash('Acesso negado ao projeto solicitado.', 'danger')
        return redirect(url_for('dashboard'))
        
    projeto_data = usuario.get('projeto', {})
    
    if not projeto_data:
        flash('Nenhum dado de projeto encontrado para download.', 'warning')
        return redirect(url_for('conteudo_dinamico', modulo_slug='projeto-final'))

    try:
        # 1. Renderiza o HTML limpo para o PDF
        # CHAVE DO AJUSTE: Passando a classe 'datetime' para o template
        html_content = render_template(
            'pdf_template.html', 
            projeto_data=projeto_data, 
            user=usuario,
            datetime=datetime # <--- VARIÁVEL 'datetime' AGORA DISPONÍVEL NO TEMPLATE
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
        # Mensagem de erro aprimorada para ajudar na depuração
        print(f"ERRO DE GERAÇÃO DE PDF: {e}")
        flash(f'Erro ao gerar o PDF. Verifique a configuração do WeasyPrint ou o template: {str(e)}', 'danger')
        return redirect(url_for('conteudo_dinamico', modulo_slug='projeto-final'))


# =========================================================
# 8. ROTAS DE CONTEÚDO DE CURSO
# (Omissão das rotas de módulo e conteúdo para brevidade)
# =========================================================
# ... (Suas rotas de módulos, concluir_modulo e conteudo_dinamico permanecem aqui) ...
@app.route('/modulos')
@requires_auth
def modulos():
    # ... (código de modulos)
    pass

@app.route('/concluir-modulo/<string:modulo_nome>', methods=['POST'])
@requires_auth
def concluir_modulo(modulo_nome):
    # ... (código de concluir_modulo)
    pass

@app.route('/conteudo/<string:modulo_slug>')
@requires_auth
def conteudo_dinamico(modulo_slug):
    # ... (código de conteudo_dinamico)
    pass


#==========================================================
# add algo
#==========================================================
def get_firebase_client_config():
    """Retorna as configurações do Firebase Client SDK."""
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
