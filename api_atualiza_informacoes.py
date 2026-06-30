# api_atualiza_informacoes.py - Blueprint para atualizar informações de eventos no BD
# MODIFICADO para também remover o evento concluído da tabela agenda_diaria_cache

from flask import Blueprint, jsonify, request
from flask_cors import CORS
import datetime
import sys
import psycopg2
from psycopg2 import OperationalError, Error

# Importa seu módulo de banco de dados
try:
    import database
except ImportError as e:
    print(f"Erro ao importar módulo: {e}. Certifique-se que database.py está no mesmo diretório ou no PYTHONPATH.")
    sys.exit(1)

# --- Criação do Blueprint ---
atualiza_informacoes_bp = Blueprint('atualiza_informacoes_bp', __name__)
CORS(atualiza_informacoes_bp)


# --- Rota para atualizar informações de um evento ---
@atualiza_informacoes_bp.route('/atualiza_informacoes/<event_id>', methods=['PUT'])
def atualiza_informacoes(event_id):
    print(f"\n--- Endpoint /atualiza_informacoes/{event_id} acessado (PUT) ---")
    data = request.get_json()

    # Validação básica dos dados recebidos
    if not data:
        print("Erro: Nenhum dado JSON recebido.")
        return jsonify({"erro": "Nenhum dado fornecido para atualização"}), 400

    dados_atualizados_payload = data.get('dados_atualizados')  # Vem do frontend, deve ser true ao concluir
    atualizado_por = data.get('atualizado_por')
    acao_usuario = data.get('acao_usuario')

    if dados_atualizados_payload is None or atualizado_por is None or acao_usuario is None:
        print("Erro: Dados incompletos para atualização.")
        return jsonify(
            {"erro": "Dados incompletos: 'dados_atualizados', 'atualizado_por' e 'acao_usuario' são obrigatórios"}), 400

    conn = None
    cursor = None
    try:
        conn, cursor = database.connect_db()
        if conn is None or cursor is None:
            print("Falha ao conectar ao banco de dados.")
            return jsonify({"erro": "Erro interno do servidor ao conectar ao BD"}), 500

        current_timestamp = datetime.datetime.now(datetime.timezone.utc)  # Timestamp atual em UTC

        # 1. Atualizar a tabela principal 'calendar_events'
        update_sql_main = """
        UPDATE calendar_events
        SET
            dados_atualizados = %s,
            atualizado_por = %s,
            acao_usuario = %s,
            data_atualizacao = %s 
        WHERE google_event_id = %s;
        """
        print(
            f"Executando UPDATE em 'calendar_events' para google_event_id: {event_id} com dados_atualizados: {dados_atualizados_payload}, atualizado_por: {atualizado_por}, acao_usuario: {acao_usuario}, data_atualizacao: {current_timestamp}")

        cursor.execute(update_sql_main,
                       (dados_atualizados_payload, atualizado_por, str(acao_usuario), current_timestamp, event_id))

        if cursor.rowcount == 0:
            conn.rollback()  # Desfaz se não encontrou o evento na tabela principal
            print(
                f"Aviso: Evento com google_event_id '{event_id}' não encontrado na tabela 'calendar_events' para atualização.")
            return jsonify(
                {"mensagem": f"Evento '{event_id}' não encontrado ou nenhum dado alterado na tabela principal."}), 404

        print(f"Evento '{event_id}' atualizado com sucesso na tabela 'calendar_events'.")

        # 2. Se o evento foi marcado como concluído (dados_atualizados = true),
        #    removê-lo da tabela 'agenda_diaria_cache'.
        if dados_atualizados_payload is True:
            delete_sql_cache = """
            DELETE FROM agenda_diaria_cache
            WHERE google_event_id = %s;
            """
            print(f"Evento concluído. Removendo google_event_id '{event_id}' da tabela 'agenda_diaria_cache'...")
            cursor.execute(delete_sql_cache, (event_id,))
            if cursor.rowcount > 0:
                print(f"Evento '{event_id}' removido com sucesso da 'agenda_diaria_cache'.")
            else:
                print(
                    f"Aviso: Evento '{event_id}' não encontrado na 'agenda_diaria_cache' para remoção (ou já havia sido removido).")

        conn.commit()  # Commit das alterações em ambas as tabelas (ou apenas na principal se não for concluído)

        return jsonify({"mensagem": f"Evento '{event_id}' processado com sucesso."}), 200

    except OperationalError as e:
        if conn: conn.rollback()
        print(f"ERRO OPERACIONAL no BD: {e}")
        return jsonify({"erro": f"Erro operacional ao atualizar o banco de dados: {e}"}), 500
    except Error as e:
        if conn: conn.rollback()
        print(f"ERRO GERAL no BD: {e}")
        return jsonify({"erro": f"Erro geral ao atualizar o banco de dados: {e}"}), 500
    except Exception as e:
        if conn: conn.rollback()
        print(f"ERRO INESPERADO: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"erro": f"Ocorreu um erro inesperado: {e}"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

