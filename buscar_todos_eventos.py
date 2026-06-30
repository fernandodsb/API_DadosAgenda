# buscar_todos_eventos.py
# Script para buscar eventos dos últimos 3 anos e inserir/atualizar no banco de dados.

import datetime
import pytz
import sys
import re
import json
import psycopg2
from dateutil.relativedelta import relativedelta  # Para subtrair anos facilmente

# Importa seus módulos de autenticação e banco de dados
try:
    import auth
    import database
except ImportError as e:
    print(
        f"Erro ao importar módulo: {e}. Certifique-se que auth.py e database.py estão no mesmo diretório ou no PYTHONPATH.")
    sys.exit(1)

from googleapiclient.errors import HttpError
from psycopg2 import OperationalError, Error

# --- Configurações ---
MAIN_CALENDAR_ID = 'centraldeatendimento@crfgo.org.br'
SECTIONAL_CALENDAR_IDS = [
    'anapolis@crfgo.org.br',
    'luziania@crfgo.org.br',
    'rioverde@crfgo.org.br',
    'uruacu@crfgo.org.br',
]

CALENDAR_IDS = [MAIN_CALENDAR_ID] + SECTIONAL_CALENDAR_IDS

LOCAL_TIMEZONE_STR = 'America/Sao_Paulo'
LOCAL_TIMEZONE = pytz.timezone(LOCAL_TIMEZONE_STR)
UTC = pytz.utc


# --- Função para buscar eventos de um único calendário (com maxResults=100) ---
def fetch_events_from_calendar(service, calendar_id, time_min_rfc3339, time_max_rfc3339):
    """Busca eventos de um calendário específico em um range de tempo com paginação."""
    print(f"\n--- Buscando eventos no calendário: {calendar_id} (com paginação de 100) ---")
    print(f"  Intervalo (UTC): de {time_min_rfc3339} a {time_max_rfc3339}")

    all_events = []
    page_token = None
    page_num = 1

    while True:
        try:
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min_rfc3339,
                timeMax=time_max_rfc3339,
                singleEvents=True,
                orderBy='startTime',
                pageToken=page_token,
                maxResults=100  # Busca em lotes de 100
            ).execute()

            events = events_result.get('items', [])
            if not events:
                print(
                    f"  Nenhum evento encontrado na página {page_num} para {calendar_id}. Paginação completa ou nenhum evento no range.")
                break

            print(f"  Encontrados {len(events)} eventos na página {page_num} para {calendar_id}.")
            all_events.extend(events)

            page_token = events_result.get('nextPageToken')
            if not page_token:
                print(f"  Paginação completa para {calendar_id}. Última página alcançada.")
                break
            page_num += 1
            print(f"  Próxima página ({page_num}) para {calendar_id}...")


        except HttpError as error:
            print(f'  Ocorreu um erro na API ao buscar eventos do calendário {calendar_id}: {error}')
            break
        except Exception as e:
            print(f'  Ocorreu um erro inesperado ao buscar eventos do calendário {calendar_id}: {e}')
            break

    print(f"--- Busca concluída para o calendário {calendar_id}. Total: {len(all_events)} eventos. ---")
    return all_events


# --- Função para processar eventos e preparar para o BD ---
# Esta função é idêntica à do script busca_eventos_semana.py
def process_events_for_db(events, calendar_id):
    """Processa a lista de eventos buscados, aplicando lógica condicional por calendário,
       e retorna uma lista de dicionários formatados internamente, com status_evento."""
    print(f"\n--- Processando {len(events)} eventos para o calendário: {calendar_id} ---")

    processed_data = []

    for event in events:
        event_summary = event.get('summary', '')
        google_event_status = event.get('status')

        db_status_evento = 'A'

        if event_summary and isinstance(event_summary, str):
            normalized_summary = event_summary.strip().lower()
            if normalized_summary.startswith("cancelar:") or normalized_summary.startswith("cancelados:"):
                db_status_evento = 'C'
                print(
                    f"  Evento ID {event.get('id', 'N/A')} marcado como 'C' (Cancelado) devido ao summary: '{event_summary}'")
            elif google_event_status == 'cancelled':
                db_status_evento = 'C'
                print(
                    f"  Evento ID {event.get('id', 'N/A')} marcado como 'C' (Cancelado) devido ao status oficial do Google: '{google_event_status}'")
            # else:
            # print(f"  Evento ID {event.get('id', 'N/A')} marcado como 'A' (Ativo).")

        event_data = {
            'id_google_calendar': event.get('id'),
            'calendar_id': calendar_id,
            'summary': event_summary,
            'description': event.get('description'),
            'location': event.get('location'),
            'html_link': event.get('htmlLink'),
            'status': google_event_status,
            'status_evento': db_status_evento,
            'created': event.get('created'),
            'updated': event.get('updated'),
            'servico_agendado': None,
            'attendees_emails_string': "",
            'is_full_day': False,
            'start_time': None,
            'end_time': None,
            'telefone': None,
            'numero_crf': None,
            'nome_convidado': None,
            'local_evento': None,
        }

        try:
            created_str = event_data.get('created')
            if created_str:
                created_dt = datetime.datetime.fromisoformat(created_str.replace('Z', '+00:00'))  # Lida com 'Z'
                event_data['created'] = created_dt.astimezone(UTC)
        except (ValueError, TypeError):
            print(
                f"  AVISO: Erro ao converter created time para evento ID {event_data.get('id_google_calendar', 'N/A')}")
            event_data['created'] = None

        try:
            updated_str = event_data.get('updated')
            if updated_str:
                updated_dt = datetime.datetime.fromisoformat(updated_str.replace('Z', '+00:00'))  # Lida com 'Z'
                event_data['updated'] = updated_dt.astimezone(UTC)
        except (ValueError, TypeError):
            print(
                f"  AVISO: Erro ao converter updated time para evento ID {event_data.get('id_google_calendar', 'N/A')}")
            event_data['updated'] = None

        start_info = event.get('start', {})
        end_info = event.get('end', {})

        if 'dateTime' in start_info:
            event_data['is_full_day'] = False
            try:
                start_dt_str = start_info.get('dateTime')
                end_dt_str = end_info.get('dateTime')

                if start_dt_str:
                    start_dt = datetime.datetime.fromisoformat(start_dt_str)
                    if start_dt.tzinfo is None:
                        event_data['start_time'] = LOCAL_TIMEZONE.localize(start_dt).astimezone(UTC)
                    else:
                        event_data['start_time'] = start_dt.astimezone(UTC)

                if end_dt_str:
                    end_dt = datetime.datetime.fromisoformat(end_dt_str)
                    if end_dt.tzinfo is None:
                        event_data['end_time'] = LOCAL_TIMEZONE.localize(end_dt).astimezone(UTC)
                    else:
                        event_data['end_time'] = end_dt.astimezone(UTC)

            except (ValueError, TypeError) as e:
                print(
                    f"  AVISO: Erro ao converter start/end dateTime para o evento ID {event_data.get('id_google_calendar', 'N/A')}: {e}")
                event_data['start_time'] = None
                event_data['end_time'] = None
        elif 'date' in start_info:  # Lida com eventos de dia inteiro
            event_data['is_full_day'] = True
            try:
                start_date_str = start_info.get('date')
                # Para eventos de dia inteiro, o 'end' é exclusivo.
                # Se for um evento de um dia, start_date e end_date serão diferentes.
                # Ex: start: 2023-10-10, end: 2023-10-11 significa que o evento é no dia 10.
                # Armazenamos o início do dia em UTC.
                start_dt = datetime.datetime.strptime(start_date_str, '%Y-%m-%d')
                event_data['start_time'] = LOCAL_TIMEZONE.localize(start_dt).astimezone(UTC)
                # Para end_time, podemos pegar o final do dia do start_time ou usar o end_date se disponível
                # Por simplicidade, vamos usar o início do dia seguinte como 'end_time' para consistência
                # ou o início do 'end_date' fornecido pelo Google.
                end_date_str = end_info.get('date')
                if end_date_str:
                    end_dt = datetime.datetime.strptime(end_date_str, '%Y-%m-%d')
                    event_data['end_time'] = LOCAL_TIMEZONE.localize(end_dt).astimezone(UTC)
                else:  # Se não houver end_date, considera o final do dia do start_date
                    event_data['end_time'] = (
                                LOCAL_TIMEZONE.localize(start_dt) + datetime.timedelta(days=1)).astimezone(UTC)

            except (ValueError, TypeError) as e:
                print(
                    f"  AVISO: Erro ao converter start/end date (dia inteiro) para o evento ID {event_data.get('id_google_calendar', 'N/A')}: {e}")
                event_data['start_time'] = None
                event_data['end_time'] = None
        else:
            print(
                f"  AVISO: Formato de data/hora desconhecido para o evento ID {event_data.get('id_google_calendar', 'N/A')}. Definindo start/end como None.")
            event_data['start_time'] = None
            event_data['end_time'] = None

        description = event_data.get('description')

        if calendar_id == MAIN_CALENDAR_ID:
            if description and isinstance(description, str):
                servico_match = re.search(r"Selecione o serviço a ser agendado::\s*(.*?)\n", description)
                email_match = re.search(r"E-mail do convidado:\s*(.*?)\n", description)
                nome_match = re.search(r"Convidado:\s*(.*?)\n", description)
                telefone_match = re.search(r"Telefone:\s*(.*?)\n", description)
                crf_match = re.search(r"Inscrição \(Nº CRF\):\s*(.*?)\n", description)

                if servico_match: event_data['servico_agendado'] = servico_match.group(1).strip()
                if email_match: event_data['attendees_emails_string'] = email_match.group(1).strip()
                if nome_match: event_data['nome_convidado'] = nome_match.group(1).strip()
                if telefone_match: event_data['telefone'] = telefone_match.group(1).strip()
                if crf_match: event_data['numero_crf'] = crf_match.group(1).strip()

        elif calendar_id in SECTIONAL_CALENDAR_IDS:
            if description and isinstance(description, str):
                servico_match = re.search(r"Selecione o serviço a ser agendado::\s*(.*?)\n", description, re.IGNORECASE)
                if servico_match: event_data['servico_agendado'] = servico_match.group(1).strip()

            nome_convidado = None
            summary_for_name = event_data.get('summary', '')
            if summary_for_name and isinstance(summary_for_name, str) and summary_for_name.strip().lower().startswith(
                    "cancelar:"):
                summary_for_name = summary_for_name.replace("Cancelar:", "", 1).strip()

            if summary_for_name:
                nome_match_summary = re.match(r"(.*?)\s+e\s+CRF-GO", summary_for_name, re.IGNORECASE)
                if nome_match_summary:
                    nome_convidado = nome_match_summary.group(1).strip()
                else:
                    parts = summary_for_name.split(' e ', 1)
                    if parts and parts[0].strip():
                        nome_convidado = parts[0].strip()
                    else:
                        nome_convidado = summary_for_name.strip()
            event_data['nome_convidado'] = nome_convidado

            attendees = event.get('attendees')
            guest_email = None
            if attendees:
                calendar_emails = [MAIN_CALENDAR_ID.lower()] + [id.lower() for id in SECTIONAL_CALENDAR_IDS]
                for att in attendees:
                    email = att.get('email')
                    if email and email.lower() not in calendar_emails:
                        guest_email = email
                        break
            event_data['attendees_emails_string'] = guest_email if guest_email else ""

            telefone = None
            if description and isinstance(description, str):
                telefone_match_desc = re.search(r"Telefone:\s*(.*?)\n", description)
                if telefone_match_desc: telefone = telefone_match_desc.group(1).strip()
            event_data['telefone'] = telefone

            numero_crf = None
            if description and isinstance(description, str):
                crf_match_desc = re.search(r"Inscrição \(Nº CRF\):\s*(.*?)\n", description)
                if crf_match_desc: numero_crf = crf_match_desc.group(1).strip()
            event_data['numero_crf'] = numero_crf

        telefone = event_data.get('telefone')
        if telefone is not None and isinstance(telefone, str):
            event_data['telefone'] = re.sub(r'[^\d\+]', '', telefone)

        numero_crf = event_data.get('numero_crf')
        if numero_crf is not None and isinstance(numero_crf, str):
            cleaned_numero_crf_strip = numero_crf.strip()
            if cleaned_numero_crf_strip in ["0", "00", "000", "0000", "00000"] or len(cleaned_numero_crf_strip) > 5:
                event_data['numero_crf'] = None
            else:
                event_data['numero_crf'] = cleaned_numero_crf_strip

        location_map = {
            MAIN_CALENDAR_ID: 'Goiânia', 'anapolis@crfgo.org.br': 'Anápolis',
            'luziania@crfgo.org.br': 'Luziânia', 'rioverde@crfgo.org.br': 'Rio Verde',
            'uruacu@crfgo.org.br': 'Uruaçu',
        }
        event_data['local_evento'] = location_map.get(event_data.get('calendar_id'))

        string_fields_to_check = [
            'summary', 'description', 'location', 'html_link', 'status',
            'servico_agendado', 'attendees_emails_string', 'nome_convidado',
            'telefone', 'numero_crf', 'status_evento'
        ]
        for field in string_fields_to_check:
            current_value = event_data.get(field)
            if current_value is None or (isinstance(current_value, str) and not current_value.strip()):
                if field not in ['numero_crf', 'telefone'] or event_data.get(
                        field) is not None:  # Mantém None se já for None
                    event_data[field] = "Não Informado" if field == 'servico_agendado' else (
                        "A" if field == 'status_evento' else "")

        MAX_LEN_VARCHAR_255 = 255
        field_limits = {
            'id_google_calendar': MAX_LEN_VARCHAR_255, 'telefone': MAX_LEN_VARCHAR_255,
            'numero_crf': MAX_LEN_VARCHAR_255, 'status': 50, 'status_evento': 1,
            'calendar_id': MAX_LEN_VARCHAR_255,
        }
        for field, max_len in field_limits.items():
            if event_data.get(field) is not None and isinstance(event_data[field], str) and len(
                    event_data[field]) > max_len:
                event_data[field] = event_data[field][:max_len]

        processed_data.append(event_data)

    # print(f"--- Processamento concluído para o calendário {calendar_id}. Total: {len(processed_data)} eventos processados. ---")
    return processed_data


# --- Lógica principal ---
if __name__ == '__main__':
    print("--- Iniciando Processo de Busca Histórica de Eventos (Últimos 3 Anos) ---")

    try:
        # --- 1. Calcular range de datas (últimos 3 anos) ---
        print("\n--- Calculando range de datas (últimos 3 anos) ---")

        today_local = datetime.datetime.now(LOCAL_TIMEZONE)
        # Data final é o final do dia de hoje (local)
        time_max_local = today_local.replace(hour=23, minute=59, second=59, microsecond=999999)

        # Data inicial é 3 anos antes do início do dia de hoje (local)
        three_years_ago_local = (today_local - relativedelta(years=3)).replace(hour=0, minute=0, second=0,
                                                                               microsecond=0)
        time_min_local = three_years_ago_local

        # Converter para UTC e formato RFC3339
        time_min_utc = time_min_local.astimezone(UTC)
        time_max_utc = time_max_local.astimezone(UTC)

        time_min_rfc3339 = time_min_utc.isoformat()  # isoformat() já inclui 'Z' para UTC se tzinfo estiver correto
        time_max_rfc3339 = time_max_utc.isoformat()

        # Correção para garantir 'Z' se não estiver presente (embora .isoformat() para UTC deva incluir)
        if not time_min_rfc3339.endswith('Z'):
            time_min_rfc3339 = time_min_rfc3339.split('+')[0] + 'Z'
        if not time_max_rfc3339.endswith('Z'):
            time_max_rfc3339 = time_max_rfc3339.split('+')[0] + 'Z'

        print(f"  Timezone Local: {LOCAL_TIMEZONE_STR}")
        print(f"  Data Inicial Local para busca: {time_min_local.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Data Final Local para busca:   {time_max_local.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Range para API (UTC/RFC3339): De {time_min_rfc3339} até {time_max_rfc3339}")

        # --- 2. Autenticar com Google Calendar API ---
        print("\n--- Autenticando com Google Calendar API ---")
        service = auth.get_calendar_service()

        if not service:
            print("Falha ao obter o serviço do Google Calendar. Saindo.")
            sys.exit(1)

            # --- 3. Buscar e processar eventos ---
        all_processed_events_for_db = []

        print(f"\n--- Buscando e processando eventos de {len(CALENDAR_IDS)} calendários... ---")
        for calendar_id in CALENDAR_IDS:
            events = fetch_events_from_calendar(service, calendar_id, time_min_rfc3339, time_max_rfc3339)
            if events:
                processed_events = process_events_for_db(events, calendar_id)
                all_processed_events_for_db.extend(processed_events)
            else:
                print(f"Nenhum evento encontrado para o calendário {calendar_id} no range especificado.")

        print(
            f"\n--- Busca e processamento de todos os calendários concluído. Total de eventos processados para BD: {len(all_processed_events_for_db)} ---")

        # --- 4. Conectar ao Banco de Dados e realizar UPSERT ---
        print("\n--- Conectando ao Banco de Dados ---")
        db_conn = None
        db_cursor = None

        try:
            db_conn, db_cursor = database.connect_db()

            if db_conn is None or db_cursor is None:
                print("Falha ao obter conexão com o banco de dados. Os dados NÃO serão salvos.")
            else:
                print("Conexão com o banco de dados estabelecida com sucesso.")
                print(f"\nRealizando UPSERT de {len(all_processed_events_for_db)} eventos no Banco de Dados...")

                if not all_processed_events_for_db:
                    print("Nenhum evento processado para realizar o UPSERT.")
                else:
                    upsert_sql = """
                   INSERT INTO calendar_events (
                       google_event_id, servico_agendado, email_farmaceutico, data_evento,
                       telefone_farmaceutico, inscricao_farmaceutico, nome_farmaceutico,
                       local_evento, fetched_at, status_evento
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (google_event_id)
                    DO UPDATE SET
                       servico_agendado = EXCLUDED.servico_agendado,
                       email_farmaceutico = EXCLUDED.email_farmaceutico,
                       data_evento = EXCLUDED.data_evento,
                       telefone_farmaceutico = EXCLUDED.telefone_farmaceutico,
                       inscricao_farmaceutico = EXCLUDED.inscricao_farmaceutico,
                       nome_farmaceutico = EXCLUDED.nome_farmaceutico,
                       local_evento = EXCLUDED.local_evento,
                       fetched_at = EXCLUDED.fetched_at,
                       status_evento = EXCLUDED.status_evento
                    ;
                   """
                    current_utc_time = datetime.datetime.now(UTC)
                    data_to_upsert = [
                        (
                            event_data.get('id_google_calendar'),
                            (event_data.get('servico_agendado').strip() if isinstance(
                                event_data.get('servico_agendado'), str) else event_data.get(
                                'servico_agendado')) or None,
                            (event_data.get('attendees_emails_string').strip() if isinstance(
                                event_data.get('attendees_emails_string'), str) else event_data.get(
                                'attendees_emails_string')) or None,
                            event_data.get('start_time'),
                            (event_data.get('telefone').strip() if isinstance(event_data.get('telefone'),
                                                                              str) else event_data.get(
                                'telefone')) or None,
                            (event_data.get('numero_crf').strip() if isinstance(event_data.get('numero_crf'),
                                                                                str) else event_data.get(
                                'numero_crf')) or None,
                            (event_data.get('nome_convidado').strip() if isinstance(event_data.get('nome_convidado'),
                                                                                    str) else event_data.get(
                                'nome_convidado')) or None,
                            event_data.get('local_evento'),
                            current_utc_time,
                            event_data.get('status_evento')
                        )
                        for event_data in all_processed_events_for_db
                    ]

                    if data_to_upsert:
                        # Dividir em lotes para executemany se for um volume muito grande
                        batch_size = 500  # Ajuste conforme necessário
                        for i in range(0, len(data_to_upsert), batch_size):
                            batch = data_to_upsert[i:i + batch_size]
                            db_cursor.executemany(upsert_sql, batch)
                            db_conn.commit()
                            print(
                                f"Lote de {len(batch)} eventos (de {i} a {i + len(batch) - 1}) processado e salvo no BD.")
                        print(f"UPSERT de {len(data_to_upsert)} eventos concluído com sucesso.")
                    else:
                        print("Nenhum dado para realizar UPSERT no banco de dados.")

        except OperationalError as e_op:
            if db_conn: db_conn.rollback()
            print(f"\n--- ERRO OPERACIONAL durante o UPSERT no BD: {e_op} ---")
        except Error as e_db:
            if db_conn: db_conn.rollback()
            print(f"\n--- ERRO GERAL durante o UPSERT no BD: {e_db} ---")
        except Exception as e_exc:
            if db_conn: db_conn.rollback()
            print(f"\n--- ERRO INESPERADO durante o UPSERT no BD: {e_exc} ---")

    except Exception as e_main:
        print(f"\n--- ERRO INESPERADO NO PROCESSO PRINCIPAL: {e_main} ---")

    finally:
        if 'db_cursor' in locals() and db_cursor is not None:
            try:
                db_cursor.close()
                print("Cursor do BD fechado.")
            except Error as e_f_cursor:
                print(f"AVISO: Erro ao fechar cursor do BD: {e_f_cursor}", file=sys.stderr)
        if 'db_conn' in locals() and db_conn is not None:
            try:
                db_conn.close()
                print("Conexão com o PostgreSQL fechada.")
            except Error as e_f_conn:
                print(f"AVISO: Erro ao fechar conexão com o BD: {e_f_conn}", file=sys.stderr)
        print("\n--- Processo de Busca Histórica Concluído ---")

