# api_dados_integrado.py
# MODIFICADO: Agora a rota principal lê de uma tabela cache.
# As funções de processamento são mantidas para serem usadas pela rotina de atualização do cache.

from flask import Blueprint, jsonify  # Removido request, pois a rota principal não o usará mais diretamente
from flask_cors import CORS
import datetime
import pytz
import psycopg2
import json  # Para serialização/desserialização
import unidecode
import sys  # Para sys.exit em caso de falha na importação do database
from psycopg2 import OperationalError, Error

# Importa a função de conexão do seu módulo database.py
try:
    import database  # Assume que database.py está no mesmo diretório ou no PYTHONPATH
except ImportError as e:
    print(f"Erro ao importar o módulo 'database': {e}")
    print("Certifique-se de que o arquivo 'database.py' está acessível.")
    sys.exit(1)

# --- Configurações e Blueprint ---
dados_mesclados_bp = Blueprint('dados_mesclados_bp', __name__)
CORS(dados_mesclados_bp)

# --- Constantes (mantidas) ---
LOCAL_TIMEZONE = pytz.timezone('America/Sao_Paulo')
UTC = pytz.utc
FRT_PG_TABLE_NAME = 'farmaceuticos_frt'

FIELD_MAP_SAGICON_DB = {
    'email_farmaceutico': {'pg_col': 'emres', 'output_key': 'email_farmaceutico'},
    'inscricao_farmaceutico': {'pg_col': 'regcli', 'output_key': 'inscricao_farmaceutico'},
    'nome_farmaceutico': {'pg_col': 'nome', 'output_key': 'nome_farmaceutico'},
    'telefone_farmaceutico': {'pg_col': 'fone', 'output_key': 'telefone_farmaceutico'},
}

COMPARISON_FIELDS = {
    'email_farmaceutico': 'email_farmaceutico',
    'nome_farmaceutico': 'nome_farmaceutico',
    'telefone_farmaceutico': 'telefone_farmaceutico',
}


# --- Funções de Apoio (Mantidas para uso da rotina de cache) ---

def are_names_partially_equal(name1, name2):
    """
    Compara dois nomes, normalizando-os (removendo acentos, espaços extras, case-insensitive).
    Verifica se todas as palavras do nome mais curto estão presentes no nome mais longo.
    """
    v1_str = name1 if name1 is not None else ""
    v2_str = name2 if name2 is not None else ""

    if not isinstance(v1_str, str): v1_str = str(v1_str)
    if not isinstance(v2_str, str): v2_str = str(v2_str)

    v1 = unidecode.unidecode(v1_str.strip().lower())
    v2 = unidecode.unidecode(v2_str.strip().lower())
    words1, words2 = v1.split(), v2.split()

    if not words1 and not words2:
        return True
    if not words1 or not words2:
        return False

    shorter_words, longer_words = (words1, words2) if len(words1) < len(words2) else (words2, words1)
    longer_words_set = set(longer_words)
    return all(word in longer_words_set for word in shorter_words)


def execute_pg_query_single_row(pg_cursor, sql_query, params):
    """
    Executa uma consulta PostgreSQL e retorna o primeiro registro como dicionário.
    Retorna None em caso de erro ou nenhum resultado.
    """
    try:
        pg_cursor.execute(sql_query, params)
        record_tuple = pg_cursor.fetchone()

        if record_tuple:
            columns = [column[0] for column in pg_cursor.description]
            return dict(zip(columns, record_tuple))
        else:
            return None
    except OperationalError as e:
        print(f"  ERRO OPERACIONAL durante a Consulta ao BD (single_row): {e}")
        return None
    except Error as e:
        print(f"  ERRO GERAL durante a Consulta ao BD (single_row): {e}")
        return None
    except Exception as e:
        print(f"  ERRO inesperado durante a consulta ao BD (single_row): {e}")
        return None


def fetch_raw_agenda_events_from_db():
    """
    Busca eventos brutos da tabela calendar_events no PostgreSQL,
    filtrando apenas os eventos do dia atual.
    Retorna uma lista de dicionários.
    Esta função será usada pela ROTINA DE ATUALIZAÇÃO DO CACHE.
    """
    print("Buscando eventos brutos da agenda do banco de dados (apenas dia atual)...")
    conn = None
    cursor = None
    agenda_events = []
    try:
        conn, cursor = database.connect_db()
        if conn is None or cursor is None:
            print("Falha ao obter conexão com o banco de dados para buscar eventos da agenda.")
            return []

        today = datetime.date.today()
        start_of_day_local = LOCAL_TIMEZONE.localize(datetime.datetime.combine(today, datetime.time.min))
        end_of_day_local = LOCAL_TIMEZONE.localize(datetime.datetime.combine(today, datetime.time.max))

        start_of_day_utc = start_of_day_local.astimezone(UTC)
        end_of_day_utc = end_of_day_local.astimezone(UTC)

        select_sql = """
        SELECT
            google_event_id, servico_agendado, email_farmaceutico, data_evento,
            telefone_farmaceutico, inscricao_farmaceutico, nome_farmaceutico,
            local_evento, fetched_at, dados_atualizados, atualizado_por,
            data_atualizacao,
            acao_usuario, status_evento, dado_diferente
        FROM calendar_events
        WHERE data_evento BETWEEN %s AND %s
        ORDER BY data_evento;
        """
        cursor.execute(select_sql, (start_of_day_utc, end_of_day_utc))
        records = cursor.fetchall()
        column_names = [desc[0] for desc in cursor.description]

        for record in records:
            item = dict(zip(column_names, record))
            # Convertendo data_atualizacao para 'atualizado_em' para consistência com o que o frontend pode esperar
            # e para manter a lógica original de como os dados eram preparados.
            if 'data_atualizacao' in item:
                item['atualizado_em'] = item.pop('data_atualizacao')
            else:
                item['atualizado_em'] = None

            # Mantém os datetimes como objetos datetime para processamento interno pela rotina
            agenda_events.append(item)

        print(f"Total de {len(agenda_events)} eventos da agenda carregados do BD para o dia atual.")
        return agenda_events

    except (OperationalError, Error) as e:
        print(f"ERRO no BD ao buscar eventos da agenda: {e}")
        return []
    except Exception as e:
        print(f"ERRO INESPERADO ao buscar eventos da agenda: {e}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


def fetch_sagicon_data_from_db_for_agenda(agenda_events_list):
    """
    Busca dados na tabela farmaceuticos_frt (Sagicon) para cada evento da agenda fornecida.
    Retorna uma lista de dicionários contendo dados do Sagicon formatados.
    Esta função será usada pela ROTINA DE ATUALIZAÇÃO DO CACHE.
    """
    print(
        f"Buscando dados do Sagicon (tabela '{FRT_PG_TABLE_NAME}') para {len(agenda_events_list)} eventos da agenda...")
    if not agenda_events_list:
        return []

    conn = None
    cursor = None
    sagicon_matched_data_list = []

    try:
        conn, cursor = database.connect_db()
        if conn is None or cursor is None:
            print("Falha ao conectar ao banco de dados PostgreSQL para dados Sagicon.")
            return []

        print(f"Conexão com BD (Sagicon - {FRT_PG_TABLE_NAME}) estabelecida.")

        for i, agenda_event in enumerate(agenda_events_list):
            google_event_id = agenda_event.get('google_event_id', 'N/A')
            inscricao_agenda = agenda_event.get('inscricao_farmaceutico')
            nome_agenda = agenda_event.get('nome_farmaceutico')
            # email_agenda = agenda_event.get('email_farmaceutico') # Não usado na busca primária/secundária aqui
            # telefone_agenda = agenda_event.get('telefone_farmaceutico') # Não usado na busca primária/secundária aqui

            found_sagicon_db_data = None

            if inscricao_agenda and str(inscricao_agenda).strip() and str(inscricao_agenda).strip() not in ('0', '00'):
                cleaned_inscricao = str(inscricao_agenda).strip()
                sql_query_inscricao = f"SELECT regcli, nome, emres, fone FROM {FRT_PG_TABLE_NAME} WHERE {FIELD_MAP_SAGICON_DB['inscricao_farmaceutico']['pg_col']} = %s"
                params_inscricao = [cleaned_inscricao]
                found_sagicon_db_data = execute_pg_query_single_row(cursor, sql_query_inscricao, params_inscricao)
                if found_sagicon_db_data:
                    pg_nome = found_sagicon_db_data.get(FIELD_MAP_SAGICON_DB['nome_farmaceutico']['pg_col'])
                    if nome_agenda and pg_nome:
                        if not are_names_partially_equal(nome_agenda, pg_nome):
                            found_sagicon_db_data = None
                    elif nome_agenda and not pg_nome:
                        found_sagicon_db_data = None

            if not found_sagicon_db_data:
                where_clauses_sdk = []
                params_secondary_sdk = []
                if nome_agenda and str(nome_agenda).strip():
                    cleaned_nome_sdk = str(nome_agenda).strip()
                    where_clauses_sdk.append(f"{FIELD_MAP_SAGICON_DB['nome_farmaceutico']['pg_col']} ILIKE %s")
                    params_secondary_sdk.append(f"%{cleaned_nome_sdk}%")
                # Adicionar outras condições de busca secundária se necessário (email, telefone)
                # Exemplo:
                # email_agenda = agenda_event.get('email_farmaceutico')
                # if email_agenda and str(email_agenda).strip():
                #    cleaned_email_sdk = str(email_agenda).strip().lower()
                #    where_clauses_sdk.append(f"LOWER({FIELD_MAP_SAGICON_DB['email_farmaceutico']['pg_col']}) = %s")
                #    params_secondary_sdk.append(cleaned_email_sdk)

                if where_clauses_sdk:
                    sql_query_secondary_sdk = f"SELECT regcli, nome, emres, fone FROM {FRT_PG_TABLE_NAME} WHERE {' OR '.join(where_clauses_sdk)}"
                    found_sagicon_db_data = execute_pg_query_single_row(cursor, sql_query_secondary_sdk,
                                                                        params_secondary_sdk)

            if found_sagicon_db_data:
                output_item = {'google_event_id': google_event_id}
                for _agenda_key, sagicon_map_details in FIELD_MAP_SAGICON_DB.items():
                    output_item[sagicon_map_details['output_key']] = found_sagicon_db_data.get(
                        sagicon_map_details['pg_col'])
                sagicon_matched_data_list.append(output_item)

        print(f"Busca de dados do Sagicon (BD) concluída. {len(sagicon_matched_data_list)} matches encontrados.")

    except (OperationalError, Error) as e:
        print(f"ERRO no BD ao buscar dados do Sagicon: {e}")
    except Exception as e:
        print(f"ERRO INESPERADO ao buscar dados do Sagicon: {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
        print(f"Conexão com BD (Sagicon - {FRT_PG_TABLE_NAME}) fechada.")
    return sagicon_matched_data_list


def process_and_merge_data_in_memory(agenda_raw_data, sagicon_processed_data):
    """
    Mescla dados brutos da agenda e dados processados do Sagicón,
    realiza a comparação de campos e retorna a lista de eventos processados.
    Esta função será usada pela ROTINA DE ATUALIZAÇÃO DO CACHE.
    """
    print("Iniciando processamento e mesclagem de dados em memória...")
    sagicon_lookup = {item.get('google_event_id'): item for item in sagicon_processed_data if
                      item.get('google_event_id')}
    print(f"Criado lookup de dados do SAGICON com {len(sagicon_lookup)} IDs únicos para mesclagem.")

    merged_events = []

    if agenda_raw_data:
        for agenda_event in agenda_raw_data:
            google_event_id = agenda_event.get('google_event_id')
            servico_agendado = agenda_event.get('servico_agendado')

            sagicon_data_for_merge = None
            sagicon_fields_match_result = False
            # Pega o valor de 'dado_diferente' do BD como base inicial ou False se não existir
            dado_diferente_result = agenda_event.get('dado_diferente', False)

            merged_item = agenda_event.copy()  # Copia todos os campos do evento da agenda

            if servico_agendado == "Inscrição Profissional (somente pessoa física)":
                # Para este serviço, a lógica original mantinha 'dado_diferente' como o valor do BD.
                # Se a intenção é sempre recalcular, esta condição pode ser ajustada.
                # Por ora, vamos definir como False, indicando que não há divergência a ser checada aqui.
                dado_diferente_result = False
            elif google_event_id and google_event_id in sagicon_lookup:
                sagicon_match = sagicon_lookup[google_event_id]
                sagicon_data_for_merge = sagicon_match

                all_fields_match_current_comparison = True
                for agenda_key, sagicon_data_key in COMPARISON_FIELDS.items():
                    agenda_value = agenda_event.get(agenda_key)
                    sagicon_value = sagicon_match.get(sagicon_data_key)
                    is_name = (agenda_key == 'nome_farmaceutico')
                    values_equal = are_names_partially_equal(agenda_value, sagicon_value) if is_name else \
                        (str(agenda_value or "").strip().lower() == str(sagicon_value or "").strip().lower())
                    if not values_equal:
                        all_fields_match_current_comparison = False
                        break

                sagicon_fields_match_result = all_fields_match_current_comparison

                # Recalcula 'dado_diferente' baseado na comparação atual
                if sagicon_data_for_merge is not None and not sagicon_fields_match_result:
                    dado_diferente_result = True
                else:
                    dado_diferente_result = False
            else:  # Nenhum match do SAGICON encontrado.
                if sagicon_data_for_merge is None:  # Garante que se não há dados Sagicon, não é "diferente"
                    dado_diferente_result = False
                # Se 'dado_diferente' já era True no BD (por algum motivo anterior), e não há dados Sagicon,
                # a lógica atual o tornaria False. Ajuste se o comportamento desejado for diferente.

            merged_item['sagicon_data'] = sagicon_data_for_merge
            merged_item['sagicon_fields_match'] = sagicon_fields_match_result
            merged_item['dado_diferente'] = dado_diferente_result

            merged_events.append(merged_item)
    else:
        print("Nenhum dado da agenda fornecido para processar.")

    print(f"Processamento e mesclagem em memória concluídos. Total: {len(merged_events)} eventos mesclados.")
    return merged_events


def update_dado_diferente_in_db(processed_events):
    """
    Atualiza apenas o campo 'dado_diferente' na tabela calendar_events.
    Esta função será usada pela ROTINA DE ATUALIZAÇÃO DO CACHE.
    """
    print("Iniciando atualização do campo 'dado_diferente' na tabela 'calendar_events'...")
    if not processed_events:
        print("Nenhum evento processado para atualizar 'dado_diferente'.")
        return

    conn = None
    cursor = None
    try:
        conn, cursor = database.connect_db()
        if conn is None or cursor is None:
            print("Falha ao obter conexão com o banco de dados para atualizar 'dado_diferente'.")
            return

        update_sql = """
        UPDATE calendar_events
        SET dado_diferente = %s
        WHERE google_event_id = %s;
        """
        updated_count = 0

        # Prepara os dados para executemany
        update_tuples = []
        for event in processed_events:
            google_event_id = event.get('google_event_id')
            dado_diferente_value = event.get('dado_diferente', False)  # Default para False se não presente
            if google_event_id:
                update_tuples.append((dado_diferente_value, google_event_id))

        if update_tuples:
            cursor.executemany(update_sql, update_tuples)
            conn.commit()
            # rowcount com executemany pode não ser preciso em todas as DB APIs/drivers para PostgreSQL com psycopg2.
            # Contar o número de tuplas é uma aproximação do número de operações tentadas.
            updated_count = len(update_tuples)
            print(
                f"Atualização de 'dado_diferente' na tabela 'calendar_events' concluída. {updated_count} eventos processados para atualização.")
        else:
            print("Nenhum evento válido encontrado em 'processed_events' para atualizar 'dado_diferente'.")


    except (OperationalError, Error) as e:
        if conn: conn.rollback()
        print(f"ERRO no BD ao atualizar 'dado_diferente' na tabela 'calendar_events': {e}")
    except Exception as e:
        if conn: conn.rollback()
        print(f"ERRO INESPERADO ao atualizar 'dado_diferente' na tabela 'calendar_events': {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# --- Rota Principal da API (MODIFICADA PARA LER DO CACHE) ---
@dados_mesclados_bp.route('/agenda/mesclada/realtime', methods=['GET'])
def get_data_from_cache():
    """
    Endpoint para buscar dados da agenda processados de uma tabela cache.
    """
    print(f"\n--- Endpoint /agenda/mesclada/realtime acessado (lendo do cache agenda_diaria_cache) ---")
    conn, cursor = None, None
    try:
        conn, cursor = database.connect_db()
        if not conn or not cursor:
            print("Erro: Falha ao conectar ao banco de dados para ler o cache.")
            return jsonify({"error": "Erro interno ao conectar ao BD"}), 500

        # Consulta os dados da tabela cache.
        # Ajuste as colunas conforme a definição da sua tabela 'agenda_diaria_cache'
        # e a estrutura que o frontend espera.
        select_sql = """
        SELECT 
            google_event_id, servico_agendado, email_farmaceutico, data_evento,
            telefone_farmaceutico, inscricao_farmaceutico, nome_farmaceutico,
            local_evento, fetched_at, dados_atualizados, atualizado_por,
            acao_usuario, status_evento, dado_diferente, 
            data_atualizacao_registro AS atualizado_em, -- Renomeando para consistência com o frontend
            sagicon_data_json AS sagicon_data,      -- Renomeando e será desserializado
            sagicon_fields_match,
            status_recepcao, chegada_em, atendido_por, atendimento_inicio, atendimento_fim
        FROM agenda_diaria_cache
        ORDER BY data_evento ASC; 
        """

        cursor.execute(select_sql)

        column_names = [desc[0] for desc in cursor.description]
        results = []
        for row in cursor.fetchall():
            row_dict = dict(zip(column_names, row))

            # Desserializar sagicon_data se estiver armazenado como JSON string
            if 'sagicon_data' in row_dict and isinstance(row_dict['sagicon_data'], str):
                try:
                    row_dict['sagicon_data'] = json.loads(row_dict['sagicon_data'])
                except json.JSONDecodeError:
                    # Se não for um JSON válido, pode manter como None ou a string original, ou logar erro
                    print(f"Aviso: Falha ao desserializar sagicon_data para o evento {row_dict.get('google_event_id')}")
                    row_dict['sagicon_data'] = None
            elif 'sagicon_data' in row_dict and row_dict['sagicon_data'] is None:
                pass  # Mantém None se for None do banco
            elif 'sagicon_data' in row_dict:  # Se já for um dict (JSONB pode retornar como dict)
                pass

            # Converter datetimes para ISO string se o frontend espera assim
            # O frontend agenda.html parece lidar bem com objetos Date, mas ISO string é mais seguro para JSON.
            for key in ['data_evento', 'fetched_at', 'atualizado_em', 'chegada_em', 'atendimento_inicio', 'atendimento_fim']:
                if key in row_dict and isinstance(row_dict[key], datetime.datetime):
                    row_dict[key] = row_dict[key].isoformat()

            results.append(row_dict)

        print(f"Retornando {len(results)} eventos do cache agenda_diaria_cache.")
        return jsonify(results), 200

    except Exception as e:
        print(f"ERRO INESPERADO ao ler do cache da agenda: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Erro interno do servidor ao ler dados do cache: {str(e)}"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# Se você tiver um app.py para registrar o blueprint:
# from flask import Flask
# app = Flask(__name__)
# app.register_blueprint(dados_mesclados_bp, url_prefix='/api')
# if __name__ == '__main__':
#     app.run(debug=True, port=5001)
