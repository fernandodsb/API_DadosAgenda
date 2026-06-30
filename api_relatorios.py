# api_relatorios.py
# MODIFICADO para verificação de status de admin case-insensitive.
from flask import Blueprint, jsonify, request
from flask_cors import CORS
import database  # Seu módulo database.py
from psycopg2 import Error, sql  # Importar sql para queries dinâmicas seguras
import datetime
import sys  # Adicionado para sys.exit em caso de falha na importação

# Importa seu módulo de banco de dados
try:
    import database
except ImportError as e:
    print(
        f"Erro ao importar módulo database: {e}. Certifique-se que database.py está no mesmo diretório ou no PYTHONPATH.")
    sys.exit(1)

relatorios_bp = Blueprint('relatorios_bp', __name__)
CORS(relatorios_bp)


def check_admin_status(username_param):
    """
    Verifica no banco de dados se o usuário fornecido tem o tipo 'admin'.
    A verificação do nome de usuário é CASE-INSENSITIVE.
    Retorna True se admin, False caso contrário ou em caso de erro.
    """
    if not username_param:
        return False
    conn = None
    cursor = None
    try:
        conn, cursor = database.connect_db()
        if not conn or not cursor:
            print("check_admin_status: Falha ao conectar ao BD.")
            return False

        # Modificado para consulta case-insensitive
        sql_query = "SELECT tipo_usuario FROM usuarios_sistema WHERE LOWER(usuario) = LOWER(%s) AND status = TRUE"
        cursor.execute(sql_query, (username_param,))
        user_record = cursor.fetchone()

        is_admin = bool(user_record and user_record[0] == 'admin')
        print(
            f"check_admin_status para '{username_param}': Encontrado? {'Sim' if user_record else 'Não'}, Tipo: {user_record[0] if user_record else 'N/A'}, É Admin? {is_admin}")
        return is_admin
    except Error as e:
        print(f"Erro no BD ao verificar status de admin para {username_param}: {e}")
        return False
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


def validate_dates_optional(data_inicio_str, data_fim_str):
    """Valida o formato das datas (YYYY-MM-DD) se fornecidas."""
    data_inicio, data_fim = None, None
    if data_inicio_str:
        try:
            data_inicio = datetime.datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        except ValueError:
            return None, None, "Formato de data inicial inválido. Use YYYY-MM-DD."
    if data_fim_str:
        try:
            data_fim = datetime.datetime.strptime(data_fim_str, '%Y-%m-%d').date()
        except ValueError:
            return None, None, "Formato de data final inválido. Use YYYY-MM-DD."

    if data_inicio and data_fim and data_inicio > data_fim:
        return None, None, "A data de início não pode ser posterior à data final."
    return data_inicio, data_fim, None


def validate_dates(data_inicio_str, data_fim_str):
    """Valida o formato das datas (YYYY-MM-DD) e se a data de início não é posterior à data final."""
    if not data_inicio_str or not data_fim_str:
        return False, "Datas de início e fim são obrigatórias."
    try:
        data_inicio = datetime.datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        data_fim = datetime.datetime.strptime(data_fim_str, '%Y-%m-%d').date()
        if data_inicio > data_fim:
            return False, "A data de início não pode ser posterior à data final."
        return True, None
    except ValueError:
        return False, "Formato de data inválido. Use YYYY-MM-DD."


# --- Endpoints para buscar opções para dropdowns ---
def fetch_distinct_options(column_name, table_name="calendar_events"):
    requesting_user = request.args.get('usuario_request')
    print(f"fetch_distinct_options para '{column_name}' solicitado por: {requesting_user}")
    if not check_admin_status(requesting_user):  # Esta chamada agora é case-insensitive
        print(f"fetch_distinct_options: Acesso negado para '{requesting_user}'.")
        return jsonify({"erro": "Acesso não autorizado."}), 403

    print(f"fetch_distinct_options: Acesso permitido para '{requesting_user}'. Buscando opções...")
    conn = None
    cursor = None
    try:
        conn, cursor = database.connect_db()
        if not conn or not cursor:
            return jsonify({"erro": "Erro interno do servidor ao conectar ao BD."}), 500

        # Usando sql.Identifier para segurança contra SQL injection nos nomes de colunas/tabelas
        query = sql.SQL("SELECT DISTINCT {} FROM {} WHERE {} IS NOT NULL AND TRIM({}) <> '' ORDER BY {} ASC").format(
            sql.Identifier(column_name), sql.Identifier(table_name),
            sql.Identifier(column_name), sql.Identifier(column_name),  # TRIM aplicado à mesma coluna
            sql.Identifier(column_name)
        )
        cursor.execute(query)
        results = cursor.fetchall()
        options = [row[0] for row in results]
        return jsonify(options), 200
    except Error as e:
        print(f"Erro no BD em fetch_distinct_options para '{column_name}': {e}")
        return jsonify({"erro": f"Erro no banco de dados: {str(e)}"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@relatorios_bp.route('/opcoes/usuarios_conclusao', methods=['GET'])
def get_opcoes_usuarios_conclusao():
    return fetch_distinct_options('atualizado_por')


@relatorios_bp.route('/opcoes/localidades', methods=['GET'])
def get_opcoes_localidades():
    return fetch_distinct_options('local_evento')


# --- FIM: Endpoints para buscar opções para dropdowns ---


@relatorios_bp.route('/filtrar_eventos', methods=['GET'])
def get_eventos_filtrados():
    requesting_user = request.args.get('usuario_request')
    print(f"/filtrar_eventos solicitado por: {requesting_user}")
    if not check_admin_status(requesting_user):  # Esta chamada agora é case-insensitive
        print(f"/filtrar_eventos: Acesso negado para '{requesting_user}'.")
        return jsonify({"erro": "Acesso não autorizado."}), 403

    print(f"/filtrar_eventos: Acesso permitido para '{requesting_user}'. Aplicando filtros...")
    data_inicio_str = request.args.get('data_inicio')
    data_fim_str = request.args.get('data_fim')
    localidade_filtro = request.args.get('localidade')
    dados_diferentes_str = request.args.get('dados_diferentes')
    atualizado_por_filtro = request.args.get('atualizado_por')
    inscricao_filtro = request.args.get('inscricao')
    nome_farmaceutico_filtro = request.args.get('nome_farmaceutico')
    status_evento_filtro = request.args.get('status_evento')

    data_inicio, data_fim, date_error_message = validate_dates_optional(data_inicio_str, data_fim_str)
    if date_error_message:
        return jsonify({"erro": date_error_message}), 400

    conn = None
    cursor = None
    try:
        conn, cursor = database.connect_db()
        if not conn or not cursor:
            return jsonify({"erro": "Erro interno do servidor ao conectar ao BD."}), 500

        query_fields = [
            sql.Identifier("google_event_id"), sql.Identifier("servico_agendado"),
            sql.Identifier("email_farmaceutico"),
            sql.SQL(
                "TO_CHAR(data_evento AT TIME ZONE 'America/Sao_Paulo', 'DD/MM/YYYY HH24:MI') AS data_evento_formatada"),
            sql.Identifier("telefone_farmaceutico"), sql.Identifier("inscricao_farmaceutico"),
            sql.Identifier("nome_farmaceutico"), sql.Identifier("local_evento"),
            sql.SQL(
                "TO_CHAR(fetched_at AT TIME ZONE 'America/Sao_Paulo', 'DD/MM/YYYY HH24:MI') AS fetched_at_formatada"),
            sql.Identifier("dados_atualizados"), sql.Identifier("atualizado_por"),
            sql.Identifier("acao_usuario"),
            sql.SQL(
                "TO_CHAR(data_atualizacao AT TIME ZONE 'America/Sao_Paulo', 'DD/MM/YYYY HH24:MI') AS data_atualizacao_formatada"),
            sql.Identifier("status_evento"), sql.Identifier("dado_diferente"),
            sql.Identifier("data_evento")  # Adicionado para ordenação precisa antes da formatação
        ]
        base_query = sql.SQL("SELECT {} FROM calendar_events").format(sql.SQL(', ').join(query_fields))

        conditions = []
        params = []

        if status_evento_filtro and status_evento_filtro.upper() in ['A', 'C']:
            conditions.append(sql.SQL("status_evento = %s"))
            params.append(status_evento_filtro.upper())

        if data_inicio and data_fim:
            conditions.append(
                sql.SQL("DATE(data_evento AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo') BETWEEN %s AND %s"))
            params.extend([data_inicio, data_fim])
        elif data_inicio:
            conditions.append(sql.SQL("DATE(data_evento AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo') >= %s"))
            params.append(data_inicio)
        elif data_fim:
            conditions.append(sql.SQL("DATE(data_evento AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo') <= %s"))
            params.append(data_fim)

        if localidade_filtro:
            conditions.append(sql.SQL("local_evento = %s"))
            params.append(localidade_filtro)

        if dados_diferentes_str is not None and dados_diferentes_str != "":
            if dados_diferentes_str.lower() == 'true':
                conditions.append(sql.SQL("dado_diferente = TRUE"))
            elif dados_diferentes_str.lower() == 'false':
                conditions.append(sql.SQL("dado_diferente = FALSE"))

        if atualizado_por_filtro:
            conditions.append(sql.SQL("atualizado_por = %s"))
            params.append(atualizado_por_filtro)

        if inscricao_filtro:
            conditions.append(sql.SQL("inscricao_farmaceutico ILIKE %s"))  # ILIKE para case-insensitive
            params.append(f"%{inscricao_filtro}%")

        if nome_farmaceutico_filtro:
            conditions.append(sql.SQL("nome_farmaceutico ILIKE %s"))  # ILIKE para case-insensitive
            params.append(f"%{nome_farmaceutico_filtro}%")

        if conditions:
            base_query += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(conditions)

        base_query += sql.SQL(" ORDER BY data_evento ASC")  # Ordenação ascendente

        # final_sql_query_debug = cursor.mogrify(base_query, params) # Para debug
        # print(f"DEBUG: SQL Query Final para /filtrar_eventos: {final_sql_query_debug.decode('utf-8', errors='ignore')}")

        cursor.execute(base_query, params)
        resultados = cursor.fetchall()

        lista_eventos = []
        colunas_desc = [desc[0] for desc in cursor.description]

        for row_tuple in resultados:
            evento_dict = dict(zip(colunas_desc, row_tuple))
            if 'data_evento' in evento_dict:  # Remove a coluna de data_evento original se não for usada no JSON final
                del evento_dict['data_evento']
            lista_eventos.append(evento_dict)

        return jsonify(lista_eventos), 200

    except Error as e:
        print(f"Erro no BD ao filtrar eventos: {e}")
        return jsonify({"erro": f"Erro no banco de dados: {str(e)}"}), 500
    except Exception as e_gen:
        print(f"Erro inesperado ao filtrar eventos: {e_gen}")
        import traceback
        traceback.print_exc()
        return jsonify({"erro": f"Erro inesperado no servidor: {str(e_gen)}"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# --- Endpoints de Relatórios Agregados (Mantidos por enquanto, mas também precisam de check_admin_status) ---
@relatorios_bp.route('/gerar/atendimentos_por_localidade', methods=['GET'])
def get_atendimentos_por_localidade():
    requesting_user = request.args.get('usuario')  # O frontend envia 'usuario' aqui
    if not check_admin_status(requesting_user):
        return jsonify({"erro": "Acesso não autorizado. Permissão de administrador necessária."}), 403

    data_inicio_str = request.args.get('inicio')
    data_fim_str = request.args.get('fim')
    is_valid, error_message = validate_dates(data_inicio_str, data_fim_str)
    if not is_valid:
        return jsonify({"erro": error_message}), 400

    conn = None
    cursor = None
    try:
        conn, cursor = database.connect_db()
        if not conn or not cursor:
            return jsonify({"erro": "Erro interno do servidor ao conectar ao BD."}), 500
        sql_query = """
        SELECT
            COALESCE(local_evento, 'Não Especificado') AS local_evento,
            COUNT(*) AS total_atendimentos
        FROM
            calendar_events
        WHERE
            status_evento = 'A' AND
            dados_atualizados = TRUE AND
            DATE(data_evento AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo') BETWEEN %s AND %s
        GROUP BY
            local_evento
        ORDER BY
            total_atendimentos DESC, local_evento ASC;
        """
        cursor.execute(sql_query, (data_inicio_str, data_fim_str))
        resultados = cursor.fetchall()
        lista_relatorio = []
        for row in resultados:
            lista_relatorio.append({"local_evento": row[0], "total_atendimentos": row[1]})
        return jsonify(lista_relatorio), 200
    except Error as e:
        return jsonify({"erro": f"Erro no banco de dados: {str(e)}"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@relatorios_bp.route('/gerar/atendimentos_por_servico', methods=['GET'])
def get_atendimentos_por_servico():
    requesting_user = request.args.get('usuario')
    if not check_admin_status(requesting_user):
        return jsonify({"erro": "Acesso não autorizado."}), 403

    data_inicio_str = request.args.get('inicio')
    data_fim_str = request.args.get('fim')
    is_valid, error_message = validate_dates(data_inicio_str, data_fim_str)
    if not is_valid:
        return jsonify({"erro": error_message}), 400

    conn = None
    cursor = None
    try:
        conn, cursor = database.connect_db()
        if not conn or not cursor:
            return jsonify({"erro": "Erro interno do servidor ao conectar ao BD."}), 500
        sql_query = """
        SELECT
            COALESCE(servico_agendado, 'Não Especificado') AS servico_agendado,
            COUNT(*) AS total_atendimentos
        FROM
            calendar_events
        WHERE
            status_evento = 'A' AND
            dados_atualizados = TRUE AND 
            DATE(data_evento AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo') BETWEEN %s AND %s
        GROUP BY
            servico_agendado
        ORDER BY
            total_atendimentos DESC, servico_agendado ASC;
        """
        cursor.execute(sql_query, (data_inicio_str, data_fim_str))
        resultados = cursor.fetchall()
        lista_relatorio = []
        for row in resultados:
            lista_relatorio.append({"servico_agendado": row[0], "total_atendimentos": row[1]})
        return jsonify(lista_relatorio), 200
    except Error as e:
        return jsonify({"erro": f"Erro no banco de dados: {str(e)}"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@relatorios_bp.route('/gerar/atendimentos_dados_diferentes', methods=['GET'])
def get_atendimentos_dados_diferentes():
    requesting_user = request.args.get('usuario')
    if not check_admin_status(requesting_user):
        return jsonify({"erro": "Acesso não autorizado."}), 403

    data_inicio_str = request.args.get('inicio')
    data_fim_str = request.args.get('fim')
    is_valid, error_message = validate_dates(data_inicio_str, data_fim_str)
    if not is_valid:
        return jsonify({"erro": error_message}), 400

    conn = None
    cursor = None
    try:
        conn, cursor = database.connect_db()
        if not conn or not cursor:
            return jsonify({"erro": "Erro interno do servidor ao conectar ao BD."}), 500
        sql_query = """
        SELECT
            google_event_id,
            COALESCE(nome_farmaceutico, 'Não Informado') AS nome_farmaceutico,
            COALESCE(inscricao_farmaceutico, 'N/A') AS inscricao_farmaceutico,
            COALESCE(servico_agendado, 'Não Especificado') AS servico_agendado,
            COALESCE(local_evento, 'Não Especificado') AS local_evento,
            TO_CHAR(data_evento AT TIME ZONE 'America/Sao_Paulo', 'DD/MM/YYYY HH24:MI') AS data_evento_formatada,
            COALESCE(atualizado_por, 'Não Informado') AS atualizado_por,
            CASE 
                WHEN data_atualizacao IS NOT NULL THEN TO_CHAR(data_atualizacao AT TIME ZONE 'America/Sao_Paulo', 'DD/MM/YYYY HH24:MI')
                ELSE 'Não Registrada'
            END AS data_verificacao_divergencia,
            acao_usuario
        FROM
            calendar_events
        WHERE
            dado_diferente = TRUE AND
            status_evento = 'A' AND 
            DATE(data_evento AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo') BETWEEN %s AND %s
        ORDER BY
            data_evento DESC;
        """
        cursor.execute(sql_query, (data_inicio_str, data_fim_str))
        resultados = cursor.fetchall()
        lista_relatorio = []
        colunas = [desc[0] for desc in cursor.description]
        for row in resultados:
            lista_relatorio.append(dict(zip(colunas, row)))
        return jsonify(lista_relatorio), 200
    except Error as e:
        return jsonify({"erro": f"Erro no banco de dados: {str(e)}"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@relatorios_bp.route('/gerar/atividades_usuarios', methods=['GET'])
def get_atividades_usuarios():
    requesting_user = request.args.get('usuario')
    if not check_admin_status(requesting_user):
        return jsonify({"erro": "Acesso não autorizado."}), 403

    data_inicio_str = request.args.get('inicio')
    data_fim_str = request.args.get('fim')
    is_valid, error_message = validate_dates(data_inicio_str, data_fim_str)
    if not is_valid:
        return jsonify({"erro": error_message}), 400

    conn = None
    cursor = None
    try:
        conn, cursor = database.connect_db()
        if not conn or not cursor:
            return jsonify({"erro": "Erro interno do servidor ao conectar ao BD."}), 500
        sql_query = """
        SELECT
            COALESCE(atualizado_por, 'Sistema/Não Identificado') AS usuario_conclusao,
            COUNT(*) AS total_conclusoes
        FROM
            calendar_events
        WHERE
            dados_atualizados = TRUE AND 
            status_evento = 'A' AND
            DATE(data_atualizacao AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo') BETWEEN %s AND %s
        GROUP BY
            atualizado_por
        ORDER BY
            total_conclusoes DESC, usuario_conclusao ASC;
        """
        cursor.execute(sql_query, (data_inicio_str, data_fim_str))
        resultados = cursor.fetchall()
        lista_relatorio = []
        colunas = [desc[0] for desc in cursor.description]
        for row in resultados:
            lista_relatorio.append(dict(zip(colunas, row)))
        return jsonify(lista_relatorio), 200
    except Error as e:
        return jsonify({"erro": f"Erro no banco de dados: {str(e)}"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
