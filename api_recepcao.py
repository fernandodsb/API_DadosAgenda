# api_recepcao.py - Blueprint para Gestão de Recepção e Fila de Atendimento (Goiânia)
from flask import Blueprint, jsonify, request
from flask_cors import CORS
import datetime
import sys

# Importa o módulo de banco de dados
try:
    import database
except ImportError as e:
    print(f"Erro ao importar database.py: {e}")
    sys.exit(1)

recepcao_bp = Blueprint('recepcao_bp', __name__)
CORS(recepcao_bp)

# 1. Marcar como CHEGOU
@recepcao_bp.route('/chegou/<event_id>', methods=['POST'])
def registrar_chegada(event_id):
    print(f"\n--- Registrar Chegada para google_event_id: {event_id} ---")
    conn, cursor = None, None
    try:
        conn, cursor = database.connect_db()
        if not conn or not cursor:
            return jsonify({"erro": "Erro ao conectar ao banco de dados"}), 500
        
        current_time = datetime.datetime.now(datetime.timezone.utc)
        
        update_sql = """
        UPDATE agenda_diaria_cache
        SET status_recepcao = 'chegou',
            chegada_em = %s
        WHERE google_event_id = %s;
        """
        cursor.execute(update_sql, (current_time, event_id))
        
        if cursor.rowcount == 0:
            return jsonify({"erro": "Evento não encontrado na agenda do dia."}), 404
            
        conn.commit()
        return jsonify({"mensagem": "Chegada registrada com sucesso!"}), 200
        
    except Exception as e:
        if conn: conn.rollback()
        print(f"Erro ao registrar chegada: {e}")
        return jsonify({"erro": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# 2. Iniciar ATENDIMENTO (Atendente puxa da fila)
@recepcao_bp.route('/atender/<event_id>', methods=['POST'])
def iniciar_atendimento(event_id):
    print(f"\n--- Iniciar Atendimento para google_event_id: {event_id} ---")
    data = request.get_json() or {}
    atendido_por = data.get('atendido_por')
    
    if not atendido_por:
        return jsonify({"erro": "Identificação do atendente é obrigatória."}), 400
        
    conn, cursor = None, None
    try:
        conn, cursor = database.connect_db()
        if not conn or not cursor:
            return jsonify({"erro": "Erro ao conectar ao banco de dados"}), 500
            
        current_time = datetime.datetime.now(datetime.timezone.utc)
        
        update_sql = """
        UPDATE agenda_diaria_cache
        SET status_recepcao = 'atendimento',
            atendido_por = %s,
            atendimento_inicio = %s
        WHERE google_event_id = %s;
        """
        cursor.execute(update_sql, (atendido_por, current_time, event_id))
        
        if cursor.rowcount == 0:
            return jsonify({"erro": "Evento não encontrado."}), 404
            
        conn.commit()
        return jsonify({"mensagem": "Atendimento iniciado!"}), 200
        
    except Exception as e:
        if conn: conn.rollback()
        print(f"Erro ao iniciar atendimento: {e}")
        return jsonify({"erro": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# 3. Finalizar ATENDIMENTO (Concluir atendimento e remover do cache diário)
@recepcao_bp.route('/finalizar/<event_id>', methods=['POST'])
def finalizar_atendimento(event_id):
    print(f"\n--- Finalizar Atendimento para google_event_id: {event_id} ---")
    data = request.get_json() or {}
    atendido_por = data.get('atendido_por', 'desconhecido')
    acao_usuario = data.get('acao_usuario', 'Atendimento concluído na recepção')
    
    conn, cursor = None, None
    try:
        conn, cursor = database.connect_db()
        if not conn or not cursor:
            return jsonify({"erro": "Erro ao conectar ao banco de dados"}), 500
            
        current_time = datetime.datetime.now(datetime.timezone.utc)
        
        # Primeiro, pegamos os dados atuais do cache para registrar o fim na tabela principal
        select_sql = "SELECT chegada_em, atendimento_inicio FROM agenda_diaria_cache WHERE google_event_id = %s"
        cursor.execute(select_sql, (event_id,))
        row = cursor.fetchone()
        
        chegada_em = row[0] if row else None
        atendimento_inicio = row[1] if row else None
        
        # 1. Atualizar a tabela principal 'calendar_events'
        update_sql_main = """
        UPDATE calendar_events
        SET dados_atualizados = true,
            atualizado_por = %s,
            acao_usuario = %s,
            data_atualizacao = %s
        WHERE google_event_id = %s;
        """
        cursor.execute(update_sql_main, (atendido_por, acao_usuario, current_time, event_id))
        
        # 2. Deletar do cache diário pois está concluído
        delete_sql_cache = "DELETE FROM agenda_diaria_cache WHERE google_event_id = %s;"
        cursor.execute(delete_sql_cache, (event_id,))
        
        conn.commit()
        return jsonify({"mensagem": "Atendimento finalizado com sucesso!"}), 200
        
    except Exception as e:
        if conn: conn.rollback()
        print(f"Erro ao finalizar atendimento: {e}")
        return jsonify({"erro": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
