# server.py - Aplicação Flask Principal para Consolidar APIs e Servir HTML

import sys
import os

# Adiciona o diretório pai (raiz do projeto) ao PYTHONPATH para permitir importações de pacotes
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.append(project_root)

from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS

# Importa os Blueprints das suas APIs existentes
from api_login import login_bp
from api_atualiza_informacoes import atualiza_informacoes_bp
from api_dados_integrado import dados_mesclados_bp

# NOVO: Importa o Blueprint da API de relatórios
from api_relatorios import relatorios_bp # <<<< ADICIONADO

from api_gestao_usuarios import gestao_usuarios_bp # Crie este arquivo
from api_recepcao import recepcao_bp # Blueprint para Recepção/Fila

# --- Configuração da Aplicação Flask Principal ---
app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app) # Habilita CORS para toda a aplicação

# --- Registro dos Blueprints ---
app.register_blueprint(login_bp, url_prefix='/auth')
app.register_blueprint(atualiza_informacoes_bp, url_prefix='/api/atualiza')
app.register_blueprint(dados_mesclados_bp, url_prefix='/api/agenda')
app.register_blueprint(relatorios_bp, url_prefix='/api/relatorios') # <<<< ADICIONADO
app.register_blueprint(gestao_usuarios_bp, url_prefix='/api/gestao_usuarios')
app.register_blueprint(recepcao_bp, url_prefix='/api/recepcao')


# --- Rotas para servir arquivos HTML ---
@app.route('/')
def serve_login_html():
    # Serve login.html da raiz do projeto (onde static_folder='.') aponta
    return send_from_directory('.', 'login.html')

@app.route('/agenda.html')
def serve_agenda_html():
    return send_from_directory('.', 'agenda.html')

# NOVO: Rota para servir a página de relatórios
@app.route('/relatorios.html')
def serve_relatorios_html():
    return send_from_directory('.', 'relatorios.html')


# --- Rota de Teste Simples para a Aplicação Principal ---
@app.route('/status')
def status_check():
    return jsonify({"message": "Servidor principal Flask está online!"}), 200


# --- Bloco Principal para Executar o Servidor ---
if __name__ == '__main__':
    PORT = 8080
    HOST = '0.0.0.0' # Permite acesso de outras máquinas na rede

    print(f"\n--- Iniciando Servidor Flask Principal ---")
    print(f"Servidor disponível em http://{HOST}:{PORT}")
    print(f"Página de Login: http://{HOST}:{PORT}/")
    print(f"Página da Agenda: http://{HOST}:{PORT}/agenda.html")
    print(f"Página de Relatórios: http://{HOST}:{PORT}/relatorios.html") # NOVO
    print(f"\nEndpoints da API:")
    print(f"  Login: http://{HOST}:{PORT}/auth/login")
    print(f"  Dados Mesclados (Agenda): http://{HOST}:{PORT}/api/agenda/agenda/mesclada/realtime")
    print(f"  Atualização de Evento: http://{HOST}:{PORT}/api/atualiza/atualiza_informacoes/<event_id>")
    print(f"  Relatórios: http://{HOST}:{PORT}/api/relatorios/gerar/...") # NOVO
    print(f"  Status do Servidor: http://{HOST}:{PORT}/status")
    print("\nVerifique se todos os Blueprints estão registrados corretamente.")

    app.run(host=HOST, port=PORT, debug=True) # debug=True é útil para desenvolvimento
