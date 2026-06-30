# api_gestao_usuarios.py
# MODIFICADO para verificação de permissão de admin case-insensitive.
from flask import Blueprint, jsonify, request
from flask_cors import CORS
import bcrypt
import sys  # Adicionado para sys.exit em caso de falha na importação

# Importa seu módulo de banco de dados
try:
    import database
except ImportError as e:
    print(
        f"Erro ao importar módulo database: {e}. Certifique-se que database.py está no mesmo diretório ou no PYTHONPATH.")
    sys.exit(1)

from psycopg2 import Error

gestao_usuarios_bp = Blueprint('gestao_usuarios_bp', __name__)
CORS(gestao_usuarios_bp)


def check_admin_permission(username_requesting):
    """
    Verifica se o usuário que está fazendo a requisição tem permissão para gerenciar usuários.
    A verificação do nome de usuário é CASE-INSENSITIVE.
    """
    if not username_requesting:
        print(f"check_admin_permission: Nome de usuário solicitante não fornecido.")
        return False

    conn, cursor = None, None
    try:
        conn, cursor = database.connect_db()
        if not conn or not cursor:
            print(f"check_admin_permission para '{username_requesting}': Falha ao conectar ao BD.")
            return False

        # Modificado para consulta case-insensitive
        # Compara o nome de usuário no banco (convertido para minúsculas) 
        # com o nome de usuário solicitante (também convertido para minúsculas).
        sql_query = "SELECT pode_criar_usuario FROM usuarios_sistema WHERE LOWER(usuario) = LOWER(%s) AND status = TRUE"
        cursor.execute(sql_query, (username_requesting,))
        record = cursor.fetchone()

        has_permission = bool(record and record[0] is True)
        print(
            f"check_admin_permission para '{username_requesting}': Encontrado? {'Sim' if record else 'Não'}, Pode Criar (BD)? {record[0] if record else 'N/A'}, Tem Permissão Final? {has_permission}")
        return has_permission
    except Error as e:
        print(f"Erro no BD ao verificar permissão de admin para '{username_requesting}': {e}")
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@gestao_usuarios_bp.route('/usuarios', methods=['POST'])
def criar_usuario():
    data = request.get_json()
    usuario_solicitante = data.get('usuario_solicitante')

    print(f"/usuarios (POST) solicitado por: {usuario_solicitante}")
    if not usuario_solicitante or not check_admin_permission(
            usuario_solicitante):  # Esta chamada agora é case-insensitive
        print(f"/usuarios (POST): Acesso negado para '{usuario_solicitante}' criar usuários.")
        return jsonify({"erro": "Acesso não autorizado para criar usuários."}), 403

    print(f"/usuarios (POST): Acesso permitido para '{usuario_solicitante}' criar usuários.")
    nome = data.get('nome')
    novo_usuario_input = data.get('usuario')  # Nome de usuário como o usuário digitou
    senha_texto_puro = data.get('senha')
    tipo_usuario = data.get('tipo_usuario', 'padrao')
    pode_criar = data.get('pode_criar_usuario', False)
    local = data.get('local', 'Goiânia')

    if not all([nome, novo_usuario_input, senha_texto_puro]):
        return jsonify({"erro": "Campos nome, usuário e senha são obrigatórios"}), 400

    # Validação para não permitir criar um usuário com nome de login já existente (case-insensitive)
    conn_check, cursor_check = None, None
    try:
        conn_check, cursor_check = database.connect_db()
        if not conn_check or not cursor_check:
            print("Erro ao criar usuário: Falha ao conectar ao BD para verificar existência.")
            return jsonify({"erro": "Erro interno do servidor ao verificar usuário existente."}), 500

        # Compara o novo_usuario_input (em minúsculas) com os usuários no banco (em minúsculas)
        cursor_check.execute("SELECT id FROM usuarios_sistema WHERE LOWER(usuario) = LOWER(%s)", (novo_usuario_input,))
        if cursor_check.fetchone():
            print(f"Tentativa de criar usuário '{novo_usuario_input}' que já existe (case-insensitive).")
            return jsonify({"erro": "Nome de usuário já existe"}), 409  # Conflict
    except Error as e_check:
        print(f"Erro ao verificar se usuário '{novo_usuario_input}' já existe: {e_check}")
        return jsonify({"erro": f"Erro no banco de dados ao verificar usuário: {e_check}"}), 500
    finally:
        if cursor_check: cursor_check.close()
        if conn_check: conn_check.close()

    senha_hasheada = bcrypt.hashpw(senha_texto_puro.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    conn, cursor = None, None
    try:
        conn, cursor = database.connect_db()
        if not conn or not cursor:  # Adicionado verificação
            print("Erro ao criar usuário: Falha ao conectar ao BD para inserção.")
            return jsonify({"erro": "Erro interno do servidor ao conectar ao BD para criar usuário."}), 500

        # Insere o novo_usuario_input com o case original fornecido pelo usuário
        insert_sql = """
        INSERT INTO usuarios_sistema (nome, usuario, senha, tipo_usuario, pode_criar_usuario, local)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;
        """
        cursor.execute(insert_sql, (nome, novo_usuario_input, senha_hasheada, tipo_usuario, pode_criar, local))
        new_user_id = cursor.fetchone()[0]
        conn.commit()
        print(f"Usuário '{novo_usuario_input}' (ID: {new_user_id}) criado com sucesso.")
        return jsonify({"message": "Usuário criado com sucesso!", "id": new_user_id}), 201
    except Error as e:
        if conn: conn.rollback()
        print(f"Erro ao criar usuário '{novo_usuario_input}' no BD: {e}")
        return jsonify({"erro": f"Erro no banco de dados: {e}"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@gestao_usuarios_bp.route('/usuarios', methods=['GET'])
def listar_usuarios():
    usuario_solicitante = request.args.get('usuario_solicitante')
    print(f"/usuarios (GET) solicitado por: {usuario_solicitante}")
    if not usuario_solicitante or not check_admin_permission(
            usuario_solicitante):  # Esta chamada agora é case-insensitive
        print(f"/usuarios (GET): Acesso negado para '{usuario_solicitante}' listar usuários.")
        return jsonify({"erro": "Acesso não autorizado."}), 403

    print(f"/usuarios (GET): Acesso permitido para '{usuario_solicitante}' listar usuários.")
    conn, cursor = None, None
    try:
        conn, cursor = database.connect_db()
        if not conn or not cursor:  # Adicionado verificação
            print("Erro ao listar usuários: Falha ao conectar ao BD.")
            return jsonify({"erro": "Erro interno do servidor ao conectar ao BD para listar usuários."}), 500

        cursor.execute(
            "SELECT id, nome, usuario, tipo_usuario, status, pode_criar_usuario, data_criacao, local FROM usuarios_sistema ORDER BY nome")
        usuarios = []
        for row in cursor.fetchall():
            usuarios.append({
                "id": row[0], "nome": row[1], "usuario": row[2],  # 'usuario' aqui é o case original do BD
                "tipo_usuario": row[3], "status": row[4],
                "pode_criar_usuario": row[5],
                "data_criacao": row[6].isoformat() if row[6] else None,
                "local": row[7]
            })
        return jsonify(usuarios), 200
    except Error as e:
        print(f"Erro ao listar usuários no BD: {e}")
        return jsonify({"erro": f"Erro no banco de dados: {e}"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@gestao_usuarios_bp.route('/usuarios/<int:user_id>', methods=['PUT'])
def alterar_usuario(user_id):
    data = request.get_json()
    usuario_solicitante = data.get('usuario_solicitante')

    print(f"/usuarios/{user_id} (PUT) solicitado por: {usuario_solicitante}")
    if not usuario_solicitante or not check_admin_permission(
            usuario_solicitante):  # Esta chamada agora é case-insensitive
        print(f"/usuarios/{user_id} (PUT): Acesso negado para '{usuario_solicitante}' alterar usuários.")
        return jsonify({"erro": "Acesso não autorizado para alterar usuários."}), 403

    print(f"/usuarios/{user_id} (PUT): Acesso permitido para '{usuario_solicitante}' alterar usuários.")
    nome = data.get('nome')
    # O nome de usuário (login) não deve ser alterado por esta rota para simplicidade.
    # Se precisar alterar, deve-se ter cuidado com duplicidade (case-insensitive).
    tipo_usuario = data.get('tipo_usuario')
    status = data.get('status')  # boolean
    pode_criar = data.get('pode_criar_usuario')  # boolean
    local = data.get('local', 'Goiânia')
    nova_senha_texto_puro = data.get('nova_senha')  # Opcional

    if nome is None or tipo_usuario is None or status is None or pode_criar is None or local is None:
        return jsonify(
            {"erro": "Campos nome, tipo_usuario, status, pode_criar_usuario e local são obrigatórios para atualização."}), 400

    conn, cursor = None, None
    try:
        conn, cursor = database.connect_db()
        if not conn or not cursor:  # Adicionado verificação
            print(f"Erro ao alterar usuário {user_id}: Falha ao conectar ao BD.")
            return jsonify({"erro": "Erro interno do servidor ao conectar ao BD para alterar usuário."}), 500

        set_clauses = ["nome = %s", "tipo_usuario = %s", "status = %s", "pode_criar_usuario = %s", "local = %s"]
        params = [nome, tipo_usuario, status, pode_criar, local]

        if nova_senha_texto_puro:
            nova_senha_hasheada = bcrypt.hashpw(nova_senha_texto_puro.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            set_clauses.append("senha = %s")
            params.append(nova_senha_hasheada)

        params.append(user_id)

        update_sql = f"UPDATE usuarios_sistema SET {', '.join(set_clauses)} WHERE id = %s;"

        cursor.execute(update_sql, tuple(params))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"message": "Usuário não encontrado ou nenhum dado alterado."}), 404

        print(f"Usuário ID {user_id} atualizado com sucesso.")
        return jsonify({"message": f"Usuário ID {user_id} atualizado com sucesso!"}), 200
    except Error as e:
        if conn: conn.rollback()
        print(f"Erro ao atualizar usuário ID {user_id} no BD: {e}")
        return jsonify({"erro": f"Erro no banco de dados ao atualizar: {e}"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
