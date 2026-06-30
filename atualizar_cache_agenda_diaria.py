# atualizar_cache_agenda_diaria.py
import sys
import os
import json
import datetime

# Adiciona o diretório raiz ao sys.path para permitir importações de módulos do projeto
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.append(project_root)

import database  # Seu módulo de conexão com o BD

# Importa as funções necessárias do seu script api_dados_integrado
# Certifique-se de que essas funções sejam importáveis (não estão aninhadas em outras funções, etc.)
try:
    from api_dados_integrado import (
        fetch_raw_agenda_events_from_db,
        fetch_sagicon_data_from_db_for_agenda,
        process_and_merge_data_in_memory,
        update_dado_diferente_in_db  # Função para atualizar 'dado_diferente' na tabela principal
    )
except ImportError as e:
    print(f"Erro ao importar módulos de api_dados_integrado: {e}")
    print("Verifique se api_dados_integrado.py está no mesmo diretório ou no PYTHONPATH.")
    sys.exit(1)


def run_atualizacao_cache_diaria():
    print(f"--- {datetime.datetime.now()} - Iniciando rotina de atualização do cache da agenda diária ---")
    conn = None
    cursor = None

    try:
        conn, cursor = database.connect_db()
        if not conn or not cursor:
            print("ERRO: Não foi possível conectar ao banco de dados.")
            return

        # 1. Buscar eventos brutos da agenda do banco de dados (para o dia atual)
        # A função fetch_raw_agenda_events_from_db já busca apenas os eventos do dia atual.
        print("Buscando eventos da agenda do dia...")
        agenda_raw_data = fetch_raw_agenda_events_from_db()

        if not agenda_raw_data:
            print("Nenhum evento da agenda encontrado para o dia atual.")
            # Limpar o cache se não houver eventos para o dia
            print("Limpando a tabela agenda_diaria_cache...")
            cursor.execute("TRUNCATE TABLE agenda_diaria_cache;")
            conn.commit()
            print("Tabela agenda_diaria_cache limpa.")
            return

        print(f"Encontrados {len(agenda_raw_data)} eventos da agenda para o dia atual.")

        # 2. Buscar dados do Sagicon (direto do BD farmaceuticos_frt) para os eventos da agenda
        print("Buscando dados do Sagicon para os eventos encontrados...")
        sagicon_processed_db_data = fetch_sagicon_data_from_db_for_agenda(agenda_raw_data)
        print(f"Encontrados {len(sagicon_processed_db_data)} matches de dados do Sagicon.")

        # 3. Processar e mesclar os dados em memória
        print("Processando e mesclando dados...")
        # Esta função já deve retornar a lista de eventos com 'dado_diferente',
        # 'sagicon_data', 'sagicon_fields_match' e outros campos necessários.
        processed_events_list = process_and_merge_data_in_memory(agenda_raw_data, sagicon_processed_db_data)
        print(f"{len(processed_events_list)} eventos processados e mesclados.")

        # 4. ATUALIZAR o campo 'dado_diferente' na tabela principal 'calendar_events'
        # Esta etapa é importante para manter a tabela principal correta.
        print("Atualizando 'dado_diferente' na tabela principal 'calendar_events'...")
        update_dado_diferente_in_db(processed_events_list)  # Passa a lista já processada
        print("'dado_diferente' atualizado na tabela principal.")

        # 5. Limpar a tabela cache e inserir os dados processados
        print("Limpando a tabela agenda_diaria_cache...")
        cursor.execute("TRUNCATE TABLE agenda_diaria_cache;")

        if not processed_events_list:
            print("Nenhum evento processado para inserir no cache (após mesclagem).")
            conn.commit()  # Commit do truncate
            return

        print(f"Inserindo {len(processed_events_list)} eventos processados na tabela agenda_diaria_cache...")

        # Adapte o SQL de INSERT e a preparação dos dados para corresponder
        # exatamente às colunas da sua tabela 'agenda_diaria_cache'
        sql_insert_cache = """
        INSERT INTO agenda_diaria_cache (
            google_event_id, servico_agendado, email_farmaceutico, data_evento,
            telefone_farmaceutico, inscricao_farmaceutico, nome_farmaceutico,
            local_evento, fetched_at, dados_atualizados, atualizado_por,
            acao_usuario, status_evento, dado_diferente, data_atualizacao_registro,
            sagicon_data_json, sagicon_fields_match, rotina_executada_em
        ) VALUES (
            %(google_event_id)s, %(servico_agendado)s, %(email_farmaceutico)s, %(data_evento)s,
            %(telefone_farmaceutico)s, %(inscricao_farmaceutico)s, %(nome_farmaceutico)s,
            %(local_evento)s, %(fetched_at)s, %(dados_atualizados)s, %(atualizado_por)s,
            %(acao_usuario)s, %(status_evento)s, %(dado_diferente)s, %(atualizado_em)s, -- 'atualizado_em' é o 'data_atualizacao'
            %(sagicon_data_json)s, %(sagicon_fields_match)s, CURRENT_TIMESTAMP
        )
        """

        data_for_cache_insert = []
        for item_data in processed_events_list:
            # Prepara o dicionário para o insert, garantindo que todas as chaves existam
            # e serializando 'sagicon_data' para JSON.
            record = {
                'google_event_id': item_data.get('google_event_id'),
                'servico_agendado': item_data.get('servico_agendado'),
                'email_farmaceutico': item_data.get('email_farmaceutico'),
                'data_evento': item_data.get('data_evento'),  # Deve estar no formato datetime
                'telefone_farmaceutico': item_data.get('telefone_farmaceutico'),
                'inscricao_farmaceutico': item_data.get('inscricao_farmaceutico'),
                'nome_farmaceutico': item_data.get('nome_farmaceutico'),
                'local_evento': item_data.get('local_evento'),
                'fetched_at': item_data.get('fetched_at'),  # Deve estar no formato datetime
                'dados_atualizados': item_data.get('dados_atualizados'),
                'atualizado_por': item_data.get('atualizado_por'),
                'acao_usuario': item_data.get('acao_usuario'),
                'status_evento': item_data.get('status_evento'),
                'dado_diferente': item_data.get('dado_diferente'),
                'atualizado_em': item_data.get('atualizado_em'),
                # Este vem como 'data_atualizacao' do BD e é renomeado para 'atualizado_em' no JSON
                'sagicon_data_json': json.dumps(item_data.get('sagicon_data')) if item_data.get(
                    'sagicon_data') else None,
                'sagicon_fields_match': item_data.get('sagicon_fields_match')
            }
            data_for_cache_insert.append(record)

        if data_for_cache_insert:
            cursor.executemany(sql_insert_cache, data_for_cache_insert)

        conn.commit()
        print(f"Tabela agenda_diaria_cache atualizada com {len(data_for_cache_insert)} registros.")

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"ERRO CRÍTICO durante a execução da rotina de atualização do cache: {e}")
        import traceback
        traceback.print_exc()  # Imprime o stack trace completo do erro
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        print(f"--- {datetime.datetime.now()} - Rotina de atualização do cache da agenda diária finalizada ---")


if __name__ == "__main__":
    run_atualizacao_cache_diaria()