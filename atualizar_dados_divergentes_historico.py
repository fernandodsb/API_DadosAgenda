# atualizar_dados_divergentes_historico.py
# Script para reprocessar eventos históricos (últimos 3 anos),
# comparar com dados do Sagicon (farmaceuticos_frt) e atualizar o campo 'dado_diferente'.

import datetime
import pytz
import sys
import re
import json
import psycopg2
import unidecode
from dateutil.relativedelta import relativedelta  # Para subtrair anos facilmente

# Importa seu módulo de banco de dados
try:
    import database  # Assume que database.py está no mesmo diretório ou no PYTHONPATH
except ImportError as e:
    print(f"Erro ao importar o módulo 'database': {e}")
    print("Certifique-se de que o arquivo 'database.py' está acessível.")
    sys.exit(1)

from psycopg2 import OperationalError, Error

# --- Constantes ---
LOCAL_TIMEZONE_STR = 'America/Sao_Paulo'
LOCAL_TIMEZONE = pytz.timezone(LOCAL_TIMEZONE_STR)
UTC = pytz.utc
FRT_PG_TABLE_NAME = 'farmaceuticos_frt'  # Tabela Sagicon/FRT

# Mapeamento de Campos para busca de dados do Sagicon (farmaceuticos_frt)
FIELD_MAP_SAGICON_DB = {
    'email_farmaceutico': {'pg_col': 'emres', 'output_key': 'email_farmaceutico'},
    'inscricao_farmaceutico': {'pg_col': 'regcli', 'output_key': 'inscricao_farmaceutico'},
    'nome_farmaceutico': {'pg_col': 'nome', 'output_key': 'nome_farmaceutico'},
    'telefone_farmaceutico': {'pg_col': 'fone', 'output_key': 'telefone_farmaceutico'},
}

# Mapeamento de Campos para Comparação (Agenda vs. Sagicón/FRT)
COMPARISON_FIELDS = {
    'email_farmaceutico': 'email_farmaceutico',
    'nome_farmaceutico': 'nome_farmaceutico',
    'telefone_farmaceutico': 'telefone_farmaceutico',
}


# --- Funções de Apoio (Reutilizadas e Adaptadas) ---

def are_names_partially_equal(name1, name2):
    """Compara dois nomes, normalizando-os e verificando palavras parciais."""
    v1_str = name1 if name1 is not None else ""
    v2_str = name2 if name2 is not None else ""
    if not isinstance(v1_str, str): v1_str = str(v1_str)
    if not isinstance(v2_str, str): v2_str = str(v2_str)
    v1 = unidecode.unidecode(v1_str.strip().lower())
    v2 = unidecode.unidecode(v2_str.strip().lower())
    words1, words2 = v1.split(), v2.split()
    if not words1 and not words2: return True
    if not words1 or not words2: return False
    shorter_words, longer_words = (words1, words2) if len(words1) < len(words2) else (words2, words1)
    longer_words_set = set(longer_words)
    return all(word in longer_words_set for word in shorter_words)


def execute_pg_query_single_row(pg_cursor, sql_query, params):
    """Executa consulta e retorna a primeira linha como dicionário."""
    try:
        pg_cursor.execute(sql_query, params)
        record_tuple = pg_cursor.fetchone()
        if record_tuple:
            columns = [column[0] for column in pg_cursor.description]
            return dict(zip(columns, record_tuple))
        return None
    except (OperationalError, Error) as e:
        print(f"  ERRO no BD (single_row query): {e}")
        return None


def fetch_raw_agenda_events_from_db_historic(time_min_utc, time_max_utc):
    """Busca eventos brutos da tabela calendar_events no PostgreSQL para um período histórico."""
    print(
        f"Buscando eventos da agenda do BD (de {time_min_utc.strftime('%Y-%m-%d')} a {time_max_utc.strftime('%Y-%m-%d')})...")
    conn = None
    cursor = None
    agenda_events = []
    try:
        conn, cursor = database.connect_db()
        if conn is None or cursor is None:
            print("Falha ao conectar ao banco de dados para buscar eventos da agenda.")
            return []

        select_sql = """
        SELECT
            google_event_id, servico_agendado, email_farmaceutico, data_evento,
            telefone_farmaceutico, inscricao_farmaceutico, nome_farmaceutico,
            local_evento, fetched_at, dados_atualizados, atualizado_por,
            data_atualizacao, acao_usuario, status_evento, dado_diferente
        FROM calendar_events
        WHERE data_evento BETWEEN %s AND %s
        ORDER BY data_evento;
        """
        cursor.execute(select_sql, (time_min_utc, time_max_utc))
        records = cursor.fetchall()
        column_names = [desc[0] for desc in cursor.description]

        for record in records:
            item = dict(zip(column_names, record))
            # Converte datetimes para string ISO para consistência, se necessário,
            # mas para processamento interno, manter como datetime pode ser melhor.
            # Para este script, manteremos como datetime.
            agenda_events.append(item)

        print(f"Total de {len(agenda_events)} eventos da agenda carregados do BD para o período.")
        return agenda_events

    except (OperationalError, Error) as e:
        print(f"ERRO no BD ao buscar eventos históricos da agenda: {e}")
        return []
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


def fetch_sagicon_data_from_db_for_agenda(agenda_events_list):
    """Busca dados do Sagicon (farmaceuticos_frt) para os eventos da agenda fornecidos."""
    print(f"Buscando dados do Sagicon (tabela '{FRT_PG_TABLE_NAME}') para {len(agenda_events_list)} eventos...")
    if not agenda_events_list:
        return []
    conn = None
    cursor = None
    sagicon_matched_data_list = []
    try:
        conn, cursor = database.connect_db()
        if conn is None or cursor is None:
            print("Falha ao conectar ao BD para dados Sagicon.")
            return []

        total_events = len(agenda_events_list)
        for i, agenda_event in enumerate(agenda_events_list):
            if (i + 1) % 100 == 0 or i == total_events - 1:
                print(f"  Processando busca Sagicon para evento {i + 1}/{total_events}...")

            google_event_id = agenda_event.get('google_event_id')
            inscricao_agenda = agenda_event.get('inscricao_farmaceutico')
            nome_agenda = agenda_event.get('nome_farmaceutico')
            # Os campos telefone e email da agenda não são usados diretamente na query primária/secundária aqui
            # mas são usados na comparação posterior.

            found_sagicon_db_data = None
            if inscricao_agenda and str(inscricao_agenda).strip() and str(inscricao_agenda).strip() not in ('0', '00'):
                cleaned_inscricao = str(inscricao_agenda).strip()
                sql_query_inscricao = f"SELECT regcli, nome, emres, fone FROM {FRT_PG_TABLE_NAME} WHERE {FIELD_MAP_SAGICON_DB['inscricao_farmaceutico']['pg_col']} = %s"
                found_sagicon_db_data = execute_pg_query_single_row(cursor, sql_query_inscricao, [cleaned_inscricao])
                if found_sagicon_db_data:
                    pg_nome = found_sagicon_db_data.get(FIELD_MAP_SAGICON_DB['nome_farmaceutico']['pg_col'])
                    if nome_agenda and pg_nome and not are_names_partially_equal(nome_agenda, pg_nome):
                        found_sagicon_db_data = None
                    elif nome_agenda and not pg_nome:
                        found_sagicon_db_data = None

            if not found_sagicon_db_data:  # Busca secundária se necessário
                where_clauses_sdk = []
                params_secondary_sdk = []
                if nome_agenda and str(nome_agenda).strip():
                    where_clauses_sdk.append(f"{FIELD_MAP_SAGICON_DB['nome_farmaceutico']['pg_col']} ILIKE %s")
                    params_secondary_sdk.append(f"%{str(nome_agenda).strip()}%")
                # Adicionar outras condições de busca secundária se necessário (email, telefone)
                # Exemplo:
                # email_agenda = agenda_event.get('email_farmaceutico')
                # if email_agenda and str(email_agenda).strip():
                #    where_clauses_sdk.append(f"LOWER({FIELD_MAP_SAGICON_DB['email_farmaceutico']['pg_col']}) = %s")
                #    params_secondary_sdk.append(str(email_agenda).strip().lower())

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
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    return sagicon_matched_data_list


def process_and_merge_data_in_memory(agenda_raw_data, sagicon_processed_data):
    """Mescla dados e recalcula 'dado_diferente'."""
    print("Iniciando processamento e mesclagem de dados em memória...")
    sagicon_lookup = {item.get('google_event_id'): item for item in sagicon_processed_data if
                      item.get('google_event_id')}

    reprocessed_events = []
    for agenda_event in agenda_raw_data:
        google_event_id = agenda_event.get('google_event_id')
        servico_agendado = agenda_event.get('servico_agendado')

        # Pega o valor original de 'dado_diferente' para referência, se necessário, mas vamos recalcular.
        # original_dado_diferente = agenda_event.get('dado_diferente', False)

        current_dado_diferente = False  # Default para não divergente
        sagicon_data_for_event = sagicon_lookup.get(google_event_id)

        if servico_agendado == "Inscrição Profissional (somente pessoa física)":
            # Para este serviço específico, a lógica original mantinha o valor do BD.
            # Se a intenção é sempre recalcular, essa condição pode ser removida ou ajustada.
            # Por ora, vamos assumir que para este serviço, 'dado_diferente' não é aplicável ou é False.
            current_dado_diferente = False
        elif sagicon_data_for_event:
            all_fields_match = True
            for agenda_key, sagicon_data_key in COMPARISON_FIELDS.items():
                agenda_value = agenda_event.get(agenda_key)
                sagicon_value = sagicon_data_for_event.get(sagicon_data_key)

                is_name = (agenda_key == 'nome_farmaceutico')
                values_equal = are_names_partially_equal(agenda_value, sagicon_value) if is_name else \
                    (str(agenda_value or "").strip().lower() == str(sagicon_value or "").strip().lower())

                if not values_equal:
                    all_fields_match = False
                    break

            if not all_fields_match:  # Se algum campo não bateu, e há dados Sagicon
                current_dado_diferente = True

        # Cria um novo dicionário ou atualiza o existente
        # É importante manter os outros campos do agenda_event
        updated_event = agenda_event.copy()
        updated_event['dado_diferente'] = current_dado_diferente
        # Adiciona sagicon_data e sagicon_fields_match se quiser retorná-los, mas não são necessários para o update
        # updated_event['sagicon_data_debug'] = sagicon_data_for_event
        # updated_event['sagicon_fields_match_debug'] = all_fields_match if sagicon_data_for_event else False
        reprocessed_events.append(updated_event)

    print(f"Processamento e mesclagem em memória concluídos. Total: {len(reprocessed_events)} eventos reprocessados.")
    return reprocessed_events


def update_dado_diferente_in_db_batch(events_to_update):
    """Atualiza o campo 'dado_diferente' no banco de dados em lotes."""
    if not events_to_update:
        print("Nenhum evento para atualizar 'dado_diferente'.")
        return

    print(f"Iniciando atualização de 'dado_diferente' para {len(events_to_update)} eventos no BD...")
    conn = None
    cursor = None
    try:
        conn, cursor = database.connect_db()
        if conn is None or cursor is None:
            print("Falha ao conectar ao BD para atualizar 'dado_diferente'.")
            return

        update_sql = """
        UPDATE calendar_events
        SET dado_diferente = %s
        WHERE google_event_id = %s;
        """

        # Prepara os dados para executemany: lista de tuplas (dado_diferente, google_event_id)
        update_data_tuples = [
            (event.get('dado_diferente', False), event.get('google_event_id'))
            for event in events_to_update if event.get('google_event_id') is not None
        ]

        if not update_data_tuples:
            print("Nenhum dado válido para a atualização de 'dado_diferente'.")
            return

        batch_size = 500  # Ajuste o tamanho do lote conforme necessário
        updated_total_count = 0

        for i in range(0, len(update_data_tuples), batch_size):
            batch = update_data_tuples[i:i + batch_size]
            try:
                cursor.executemany(update_sql, batch)
                conn.commit()  # Commit por lote
                updated_count_in_batch = cursor.rowcount  # Pode não ser 100% preciso para todas as configs
                updated_total_count += len(batch)  # Assume que todos no lote foram processados
                print(
                    f"  Lote de {len(batch)} atualizações de 'dado_diferente' processado. (Afetou aprox. {updated_count_in_batch} linhas)")
            except (OperationalError, Error) as e_batch:
                print(f"  ERRO no BD ao atualizar lote de 'dado_diferente': {e_batch}")
                if conn: conn.rollback()  # Rollback do lote atual
                # Decide se quer continuar com próximos lotes ou parar tudo
                # Por segurança, vamos parar se um lote falhar
                print("  Interrompendo atualizações devido a erro no lote.")
                return

        print(f"Atualização de 'dado_diferente' concluída. {updated_total_count} eventos processados para atualização.")

    except (OperationalError, Error) as e:
        if conn: conn.rollback()
        print(f"ERRO GERAL no BD ao atualizar 'dado_diferente': {e}")
    except Exception as e_ex:
        if conn: conn.rollback()
        print(f"ERRO INESPERADO ao atualizar 'dado_diferente': {e_ex}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# --- Lógica Principal do Script ---
if __name__ == '__main__':
    print("--- Iniciando Script de Atualização Histórica de 'dado_diferente' ---")

    # 1. Calcular range de datas (últimos 3 anos)
    today_local = datetime.datetime.now(LOCAL_TIMEZONE)
    time_max_local = today_local.replace(hour=23, minute=59, second=59, microsecond=999999)
    time_min_local = (today_local - relativedelta(years=3)).replace(hour=0, minute=0, second=0, microsecond=0)

    time_min_utc = time_min_local.astimezone(UTC)
    time_max_utc = time_max_local.astimezone(UTC)

    print(f"Período de busca: de {time_min_utc.strftime('%Y-%m-%d')} a {time_max_utc.strftime('%Y-%m-%d')}")

    # 2. Buscar todos os eventos da agenda no período
    agenda_raw_data = fetch_raw_agenda_events_from_db_historic(time_min_utc, time_max_utc)
    if not agenda_raw_data:
        print("Nenhum evento da agenda encontrado no período especificado. Encerrando.")
        sys.exit(0)

    # 3. Buscar dados do Sagicon para os eventos encontrados
    sagicon_db_data = fetch_sagicon_data_from_db_for_agenda(agenda_raw_data)
    # sagicon_db_data pode estar vazio se não houver matches, o que é normal.

    # 4. Processar e mesclar os dados, recalculando 'dado_diferente'
    reprocessed_events = process_and_merge_data_in_memory(agenda_raw_data, sagicon_db_data)

    # 5. Atualizar o campo 'dado_diferente' no banco de dados
    if reprocessed_events:
        update_dado_diferente_in_db_batch(reprocessed_events)
    else:
        print("Nenhum evento foi reprocessado, nenhuma atualização no BD necessária.")

    print("\n--- Script de Atualização Histórica Concluído ---")
