# api_login.py - Blueprint de Autenticação de Usuário no BD PostgreSQL
# MODIFICADO para login case-insensitive para o nome de usuário.

from flask import Blueprint, jsonify, request # Importa Blueprint
from flask_cors import CORS # Permite requisições de diferentes origens
import sys
import bcrypt # Importa a biblioteca bcrypt para hashing de senhas

# Importa seu módulo de banco de dados
try:
    import database
except ImportError as e:
    print(f"Erro ao importar módulo: {e}. Certifique-se que database.py está no mesmo diretório ou no PYTHONPATH.")
    sys.exit(1)

from psycopg2 import OperationalError, Error # Importa classes de erro do psycopg2

# --- Criação do Blueprint ---
login_bp = Blueprint('login_bp', __name__)
CORS(login_bp) # Habilita CORS para este Blueprint

# --- Rota da API para Login (agora usando o Blueprint) ---
@login_bp.route('/login', methods=['POST'])
def login():
    """
    Endpoint para autenticação de usuário.
    Recebe JSON com 'username' e 'password'.
    Retorna JSON com 'authenticated', 'message', e 'userType' (se autenticado).
    Login de usuário agora é case-insensitive.
    """
    print("\n--- Endpoint /login acessado ---")

    # 1. Obter dados do request JSON
    request_data = request.get_json()
    if not request_data:
        print("Erro: Request não contém JSON ou JSON inválido.")
        return jsonify({"authenticated": False, "message": "Dados JSON inválidos"}), 400

    usuario_input = request_data.get('username') # Frontend envia 'username'
    senha_fornecida = request_data.get('password') # Frontend envia 'password'

    if not usuario_input or not senha_fornecida:
        print("Erro: Usuário ou senha não fornecidos no JSON.")
        return jsonify({"authenticated": False, "message": "Usuário e senha são obrigatórios"}), 400

    print(f"Tentativa de login para o usuário (input): '{usuario_input}'")

    db_conn = None
    db_cursor = None

    try:
        # 2. Conectar ao banco de dados PostgreSQL
        db_conn, db_cursor = database.connect_db()
        if db_conn is None or db_cursor is None:
           print("Falha ao conectar ao banco de dados PostgreSQL.")
           return jsonify({"authenticated": False, "message": "Erro interno do servidor ao conectar ao BD"}), 500

        print("Conexão com o BD estabelecida.")

        # 3. Consultar usuário no banco de forma case-insensitive
        # Seleciona a senha HASH, o status, o tipo_usuario, pode_criar_usuario e o nome de usuário original do banco
        # A comparação é feita usando LOWER() em ambos os lados ou LOWER() no lado do BD e passando o input em minúsculas.
        # Vamos usar LOWER() no lado do BD e passar o input em minúsculas.
        select_sql = """
        SELECT senha, status, tipo_usuario, pode_criar_usuario, usuario, local 
        FROM usuarios_sistema 
        WHERE LOWER(usuario) = %s;
        """
        # Converte o nome de usuário do input para minúsculas para a consulta
        db_cursor.execute(select_sql, (usuario_input.lower(),))
        user_record = db_cursor.fetchone()

        # 4. Verificar resultado da consulta e credenciais
        if user_record:
            senha_hash_armazenada = user_record[0]
            status_ativo = user_record[1]
            tipo_usuario_db = user_record[2]
            pode_criar_usuario_db = user_record[3]
            usuario_db_cased = user_record[4] # Nome de usuário com o case original do banco
            local_db = user_record[5]

            print(f"Usuário encontrado no BD (case original: '{usuario_db_cased}'). Status Ativo: {status_ativo}, Tipo: {tipo_usuario_db}, Pode Criar Usuário: {pode_criar_usuario_db}, Local: {local_db}.")

            if senha_hash_armazenada and bcrypt.checkpw(senha_fornecida.encode('utf-8'), senha_hash_armazenada.encode('utf-8')):
                print("Senha corresponde.")
                if status_ativo:
                    print("Usuário ativo. Autenticação BEM-SUCEDIDA.")
                    # O frontend já armazena o 'username' como foi digitado.
                    # Se você quisesse usar o nome de usuário com o case do banco, poderia retorná-lo:
                    # "username_db": usuario_db_cased
                    return jsonify({
                        "authenticated": True,
                        "message": "Login bem-sucedido!",
                        "userType": tipo_usuario_db,
                        "pode_criar_usuario": pode_criar_usuario_db,
                        "local": local_db
                        # "username_db": usuario_db_cased # Opcional: se o frontend precisar do nome exato do BD
                    }), 200
                else:
                    print("Usuário INATIVO. Autenticação FALHOU.")
                    return jsonify({
                        "authenticated": False,
                        "message": "Usuário inativo."
                    }), 403 # Forbidden
            else:
                print("Senha NÃO corresponde ou hash inválido. Autenticação FALHOU.")
                return jsonify({
                    "authenticated": False,
                    "message": "Credenciais inválidas." # Mensagem genérica para senha incorreta
                }), 401 # Unauthorized
        else:
            print(f"Usuário '{usuario_input}' (após conversão para lower na query) NÃO encontrado no banco de dados. Autenticação FALHOU.")
            return jsonify({
                "authenticated": False,
                "message": "Usuário não encontrado."
            }), 404 # Not Found

    except OperationalError as e:
        print(f"ERRO OPERACIONAL no BD durante login: {e}")
        return jsonify({"authenticated": False, "message": "Erro interno do servidor (DB Op)"}), 500
    except Error as e:
        print(f"ERRO GERAL no BD durante login: {e}")
        return jsonify({"authenticated": False, "message": "Erro interno do servidor (DB Gen)"}), 500
    except Exception as e:
        print(f"ERRO INESPERADO durante login: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"authenticated": False, "message": "Erro interno do servidor (Exc)"}), 500
    finally:
        # Fechar cursor e conexão
        if db_cursor is not None:
            try:
                db_cursor.close()
                print("Cursor do BD fechado.")
            except Error as e_cursor:
                print(f"AVISO: Erro ao fechar cursor do BD: {e_cursor}", file=sys.stderr)
        if db_conn is not None:
            try:
                db_conn.close()
                print("Conexão com o PostgreSQL fechada.")
            except Error as e_conn:
                 print(f"AVISO: Erro ao fechar conexão com o BD: {e_conn}", file=sys.stderr)
