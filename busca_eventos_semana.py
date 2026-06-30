# busca_eventos_semana.py - Código FINAL atualizado para incluir tratamento de "Cancelar:" no summary
# e status_evento no banco de dados ('A' ou 'C'), GARANTINDO A ATUALIZAÇÃO DO STATUS.

import datetime
import pytz
import sys
import re
import json
import psycopg2

# Importa seus módulos de autenticação e banco de dados
try:
    import auth
    import database
except ImportError as e:
    print(f"Erro ao importar módulo: {e}. Certifique-se que auth.py e database.py estão no mesmo diretório ou no PYTHONPATH.")
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
def fetch_events_from_calendar(service, calendar_id, time_min, time_max):
    """Busca eventos de um calendário específico em um range de tempo com paginação."""
    print(f"\n--- Buscando eventos no calendário: {calendar_id} (com paginação de 100) ---")
    print(f"  Intervalo (UTC): de {time_min} a {time_max}")

    all_events = []
    page_token = None
    page_num = 1

    while True:
        try:
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime',
                pageToken=page_token,
                maxResults=100
            ).execute()

            events = events_result.get('items', [])
            if not events:
                 print(f"  Nenhum evento encontrado na página {page_num}. Paginação completa ou nenhum evento no range.")
                 break

            print(f"  Encontrados {len(events)} eventos na página {page_num}.")
            all_events.extend(events)

            page_token = events_result.get('nextPageToken')
            if not page_token:
                print("  Paginação completa. Última página alcançada.")
                break
            page_num += 1

        except HttpError as error:
            print(f'  Ocorreu um erro na API ao buscar eventos do calendário {calendar_id}: {error}')
            break
        except Exception as e:
            print(f'  Ocorreu um erro inesperado ao buscar eventos do calendário {calendar_id}: {e}')
            break

    print(f"--- Busca concluída para o calendário {calendar_id}. Total: {len(all_events)} eventos. ---")
    return all_events

# --- Função para processar eventos e preparar para o BD (ATUALIZADA para sempre processar e definir status_evento) ---
def process_events_for_db(events, calendar_id):
    """Processa a lista de eventos buscados, aplicando lógica condicional por calendário,
       e retorna uma lista de dicionários formatados internamente, com status_evento."""
    print(f"\n--- Processando {len(events)} eventos para o calendário: {calendar_id} ---")

    processed_data = []

    for event in events:
        event_summary = event.get('summary', '')
        google_event_status = event.get('status') # Pega o status oficial do Google: 'confirmed', 'cancelled', etc.

        # 1. Determinar o status para o banco de dados (A ou C)
        # Prioridade 1: Se o summary começar com "Cancelar:" ou "Cancelados:", defina como 'C'.
        # Prioridade 2: Senão, se o status oficial do Google for 'cancelled', defina como 'C'.
        # Caso contrário, será 'A'.
        db_status_evento = 'A' # Default para Ativo

        if event_summary and isinstance(event_summary, str):
            normalized_summary = event_summary.strip().lower()
            if normalized_summary.startswith("cancelar:") or normalized_summary.startswith("cancelados:"):
                db_status_evento = 'C'
                print(f"  Evento ID {event.get('id', 'N/A')} marcado como 'C' (Cancelado) devido ao summary: '{event_summary}'")
            elif google_event_status == 'cancelled':
                db_status_evento = 'C'
                print(f"  Evento ID {event.get('id', 'N/A')} marcado como 'C' (Cancelado) devido ao status oficial do Google: '{google_event_status}'")
            else:
                print(f"  Evento ID {event.get('id', 'N/A')} marcado como 'A' (Ativo).")

        # NENHUM 'continue' aqui. O evento SEMPRE será processado para que seu status_evento possa ser atualizado.

        # Inicializa o dicionário com todos os campos possíveis que extraímos/processamos
        event_data = {
            'id_google_calendar': event.get('id'),
            'calendar_id': calendar_id,
            'summary': event_summary, # Usa o summary já obtido
            'description': event.get('description'),
            'location': event.get('location'), # Mantido o campo original location
            'html_link': event.get('htmlLink'),
            'status': google_event_status, # Mantém o status original do Google para referência interna
            'status_evento': db_status_evento, # NOVO CAMPO para o banco de dados (A ou C)
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

        # --- Tratamento de Data/Hora ---
        try:
            created_str = event_data.get('created')
            if created_str:
                 created_dt = datetime.datetime.fromisoformat(created_str)
                 if created_dt.tzinfo is not None:
                      event_data['created'] = created_dt.astimezone(UTC)
                 else:
                      event_data['created'] = created_dt.replace(tzinfo=UTC)
        except (ValueError, TypeError):
             print(f"  AVISO: Erro ao converter created time para evento ID {event_data.get('id_google_calendar', 'N/A')}")
             event_data['created'] = None

        try:
            updated_str = event_data.get('updated')
            if updated_str:
                updated_dt = datetime.datetime.fromisoformat(updated_str)
                if updated_dt.tzinfo is not None:
                     event_data['updated'] = updated_dt.astimezone(UTC)
                else:
                     event_data['updated'] = updated_dt.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            print(f"  AVISO: Erro ao converter updated time para evento ID {event_data.get('id_google_calendar', 'N/A')}")
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
                 print(f"  AVISO: Erro ao converter start/end dateTime para o evento ID {event_data.get('id_google_calendar', 'N/A')}: {e}")
                 event_data['start_time'] = None
                 event_data['end_time'] = None
        else:
             print(f"  AVISO: Formato de data/hora desconhecido para o evento ID {event_data.get('id_google_calendar', 'N/A')}. Definindo start/end como None.")
             event_data['start_time'] = None
             event_data['end_time'] = None


        # --- Processamento CONDICIONAL baseado no calendar_id ---
        description = event_data.get('description') # Obtém a descrição, pode ser None

        if calendar_id == MAIN_CALENDAR_ID:
            print(f"  Aplicando lógica da Central de Atendimento para evento ID {event_data.get('id_google_calendar', 'N/A')}...")

            if description and isinstance(description, str):
                servico_match = re.search(r"Selecione o serviço a ser agendado::\s*(.*?)\n", description)
                email_match = re.search(r"E-mail do convidado:\s*(.*?)\n", description)
                nome_match = re.search(r"Convidado:\s*(.*?)\n", description)
                telefone_match = re.search(r"Telefone:\s*(.*?)\n", description)
                crf_match = re.search(r"Inscrição \(Nº CRF\):\s*(.*?)\n", description)

                if servico_match:
                    event_data['servico_agendado'] = servico_match.group(1).strip()
                if email_match:
                     event_data['attendees_emails_string'] = email_match.group(1).strip()
                if nome_match:
                     event_data['nome_convidado'] = nome_match.group(1).strip()
                if telefone_match:
                     event_data['telefone'] = telefone_match.group(1).strip()
                if crf_match:
                     event_data['numero_crf'] = crf_match.group(1).strip()
            else:
                print(f"  AVISO: Descrição ausente ou não é string para evento ID {event_data.get('id_google_calendar', 'N/A')}. Ignorando extração de descrição.")




        elif calendar_id in SECTIONAL_CALENDAR_IDS:

            print(

                f"  Aplicando lógica da Seccional ({calendar_id}) para evento ID {event_data.get('id_google_calendar', 'N/A')}...")

            description = event_data.get('description')  # Pega a descrição do evento

            # --- Adicionar Lógica para extrair Servico Agendado (Seccional) ---

            if description and isinstance(description, str):

                # Usar a regex com DOIS dois-pontos, conforme sua solicitação

                servico_match = re.search(r"Selecione o serviço a ser agendado::\s*(.*?)\n", description, re.IGNORECASE)

                if servico_match:

                    event_data['servico_agendado'] = servico_match.group(1).strip()

                    print(f"    - SERVIÇO EXTRAÍDO (SECCIONAL): '{event_data['servico_agendado']}'")  # Debug print

                else:

                    print(f"    - AVISO (SECCIONAL): Padrão de serviço NÃO ENCONTRADO na descrição.")  # Debug print

            else:

                print(f"    - AVISO (SECCIONAL): Descrição ausente ou não é string. Ignorando extração de serviço.")

            # --- Extrair Nome do Convidado ---

            nome_convidado = None

            summary_for_name = event_data.get('summary', '')

            # NOVO: Remover "Cancelar:" do summary antes de extrair o nome

            if summary_for_name and isinstance(summary_for_name, str) and summary_for_name.strip().lower().startswith(
                    "cancelar:"):
                # Remove "Cancelar:" e qualquer espaço após, ex: "Cancelar: Nome" -> "Nome"

                summary_for_name = summary_for_name.replace("Cancelar:", "", 1).strip()

                print(
                    f"    - 'Cancelar:' removido do summary para extração do nome. Novo summary para nome: '{summary_for_name}'")

            if summary_for_name:

                nome_match_summary = re.match(r"(.*?)\s+e\s+CRF-GO", summary_for_name, re.IGNORECASE)

                if nome_match_summary:

                    nome_convidado = nome_match_summary.group(1).strip()

                    print(f"    - Nome do convidado extraído do summary ('Nome e CRF-GO' padrão).")

                else:

                    parts = summary_for_name.split(' e ', 1)

                    if parts and parts[0].strip():

                        nome_convidado = parts[0].strip()

                        print(f"    - Nome do convidado extraído do summary (alternativa 'Nome e ...').")

                    else:

                        nome_convidado = summary_for_name.strip()

                        print(f"    - Nome do convidado definido como summary completo.")

            event_data['nome_convidado'] = nome_convidado

            # ... (restante do código para email, telefone, crf) ...


            # --- Extrair E-mail do Convidado ---
            attendees = event.get('attendees')
            guest_email = None
            if attendees:
                 calendar_emails = [MAIN_CALENDAR_ID.lower()] + [id.lower() for id in SECTIONAL_CALENDAR_IDS]
                 for att in attendees:
                      email = att.get('email')
                      if email and email.lower() not in calendar_emails:
                           guest_email = email
                           print(f"    - Primeiro email de convidado externo encontrado na lista attendees: {guest_email}")
                           break

            event_data['attendees_emails_string'] = guest_email if guest_email else ""


            # --- Extrair Telefone ---
            telefone = None
            if description and isinstance(description, str):
                 telefone_match_desc = re.search(r"Telefone:\s*(.*?)\n", description)
                 if telefone_match_desc:
                      telefone = telefone_match_desc.group(1).strip()
                      print(f"    - Telefone extraído da descrição.")
            event_data['telefone'] = telefone


            # --- Extrair Número CRF ---
            numero_crf = None
            if description and isinstance(description, str):
                 crf_match_desc = re.search(r"Inscrição \(Nº CRF\):\s*(.*?)\n", description)
                 if crf_match_desc:
                      numero_crf = crf_match_desc.group(1).strip()
                      print(f"    - Número CRF extraído da descrição.")
            event_data['numero_crf'] = numero_crf
            print(f"    - Número CRF {'encontrado' if event_data['numero_crf'] else 'NÃO encontrado ou ausente'} na descrição.")


        # --- Pós-processamento COMUM ---
        # Define valores padrão, lida com limpeza/validação e define local_evento.

        # 1. Limpar caracteres especiais e espaços do telefone
        telefone = event_data.get('telefone')
        if telefone is not None and isinstance(telefone, str):
            cleaned_telefone = re.sub(r'[^\d\+]', '', telefone)
            event_data['telefone'] = cleaned_telefone
            if telefone != cleaned_telefone:
                 print(f"  Telefone limpo para ID {event_data.get('id_google_calendar', 'N/A')}: '{telefone}' -> '{cleaned_telefone}'")

        # 2. Validar tamanho e valor específico da Inscrição (Nº CRF)
        numero_crf = event_data.get('numero_crf')
        if numero_crf is not None and isinstance(numero_crf, str):
            cleaned_numero_crf_strip = numero_crf.strip()

            if cleaned_numero_crf_strip in ["0", "00", "000", "0000", "00000"]:
                 print(f"  AVISO: Inscrição (CRF) '{numero_crf}' para ID {event_data.get('id_google_calendar', 'N/A')} é uma string de zeros ('{cleaned_numero_crf_strip}'). Definindo como None.")
                 event_data['numero_crf'] = None
            elif len(cleaned_numero_crf_strip) > 5:
                print(f"  AVISO: Inscrição (CRF) '{numero_crf}' para ID {event_data.get('id_google_calendar', 'N/A')} tem mais de 5 caracteres após strip. Definindo como None.")
                event_data['numero_crf'] = None
            else:
                 event_data['numero_crf'] = cleaned_numero_crf_strip


        # 3. Definir local_evento baseado no calendar_id
        location_map = {
            MAIN_CALENDAR_ID: 'Goiânia',
            'anapolis@crfgo.org.br': 'Anápolis',
            'luziania@crfgo.org.br': 'Luziânia',
            'rioverde@crfgo.org.br': 'Rio Verde',
            'uruacu@crfgo.org.br': 'Uruaçu',
        }
        calendar_id_for_location = event_data.get('calendar_id') # Obtém o ID do calendário do evento
        determined_location = location_map.get(calendar_id_for_location)

        event_data['local_evento'] = determined_location

        if determined_location:
             print(f"  Local definido por Calendar ID {calendar_id_for_location}: {determined_location}")
        else:
             print(f"  AVISO: Calendar ID {calendar_id_for_location} não encontrado no mapa de localização. Local_evento será None.")


        # 4. Definir padrão para campos de string vazios no DICIONARIO
        string_fields_to_check = [
            'summary', 'description', 'location', 'html_link', 'status',
            'servico_agendado', 'attendees_emails_string', 'nome_convidado',
            'telefone', 'numero_crf', 'status_evento'
        ]
        for field in string_fields_to_check:
             current_value = event_data.get(field)
             if current_value is None or (isinstance(current_value, str) and not current_value.strip()):
                  # Exceções para campos que podem ser None intencionalmente
                  if field == 'numero_crf' and event_data.get('numero_crf') is None:
                       pass
                  elif field == 'telefone' and event_data.get('telefone') is None and current_value is not None and not current_value.strip():
                       pass
                  elif field == 'status_evento': # status_evento deve ser 'A' ou 'C', não vazio
                       event_data[field] = 'A' # Default para 'A' se algo der errado
                  else:
                       event_data[field] = "Não Informado" if field == 'servico_agendado' else ""

        # 5. Truncamento de campos de texto
        MAX_LEN_VARCHAR_255 = 255
        MAX_LEN_VARCHAR_500 = 500

        field_limits = {
            'id_google_calendar': MAX_LEN_VARCHAR_255,
            'servico_agendado': None,
            'attendees_emails_string': None,
            'telefone': MAX_LEN_VARCHAR_255,
            'numero_crf': MAX_LEN_VARCHAR_255,
            'nome_convidado': None,
            'summary': None,
            'location': None,
            'html_link': None,
            'status': 50, # Google status field
            'status_evento': 1, # 'A' or 'C'
            'description': None,
            'calendar_id': MAX_LEN_VARCHAR_255,
            'local_evento': None
        }

        for field, max_len in field_limits.items():
             if max_len is not None and event_data.get(field) is not None and isinstance(event_data[field], str) and len(event_data[field]) > max_len:
                  print(f"  AVISO: Campo interno '{field}' muito longo para a coluna correspondente no BD. Truncando para {max_len}...")
                  event_data[field] = event_data[field][:max_len]


        processed_data.append(event_data) # Adiciona o evento processado à lista

        # >>> SEÇÃO DE DEBUG: DESCOMENTE PARA IMPRIMIR O EVENTO COMPLETO NO LOG <<<
        print(f"\n--- Dados Processados para BD (ID {event_data.get('id_google_calendar', 'N/A')}, Calendar: {calendar_id}): ---")
        printable_event_data = event_data.copy()
        datetime_fields_to_print = ['start_time', 'end_time', 'created', 'updated']
        for field in datetime_fields_to_print: # Corrigido o nome da variável aqui
            if field in printable_event_data and isinstance(printable_event_data[field], (datetime.datetime, datetime.date)):
                printable_event_data[field] = printable_event_data[field].isoformat()
        print(json.dumps(printable_event_data, indent=2, ensure_ascii=False))
        print("-" * 30)
        # >>> FIM DEBUG PRINT <<<


    print(f"--- Processamento concluído para o calendário {calendar_id}. Total de eventos processados: {len(processed_data)} ---")
    return processed_data


# --- Lógica principal ---
if __name__ == '__main__':
    print("--- Iniciando Processo de Agenda (Buscar, Processar e Salvar no BD) ---")

    try:
        # --- 1. Calcular range de datas (semana atual) ---
        print("\n--- Calculando range de datas (semana atual) ---")

        today = datetime.date.today()
        start_of_week_date = today - datetime.timedelta(days=today.weekday())
        end_of_week_date = start_of_week_date + datetime.timedelta(days=6)

        start_of_week_local = datetime.datetime.combine(start_of_week_date, datetime.time.min)
        end_of_week_local = datetime.datetime.combine(end_of_week_date, datetime.time.max)

        local_aware_start = LOCAL_TIMEZONE.localize(start_of_week_local)
        local_aware_end = LOCAL_TIMEZONE.localize(end_of_week_local)

        utc_aware_start = local_aware_start.astimezone(UTC)
        utc_aware_end = local_aware_end.astimezone(UTC)

        time_min_rfc3339 = utc_aware_start.isoformat().replace('+00:00', 'Z')
        time_max_rfc3339 = utc_aware_end.isoformat().replace('+00:00', 'Z')


        print(f"  Timezone Local: {LOCAL_TIMEZONE_STR}")
        print(f"  Semana Local: De {start_of_week_date.strftime('%Y-%m-%d')} até {end_of_week_date.strftime('%Y-%m-%d')}")
        print(f"  Range Local: De {local_aware_start} até {local_aware_end}")
        print(f"  Range para API (UTC/RFC 3339): De {time_min_rfc3339} até {time_max_rfc3339}")


        # --- 2. Autenticar com Google Calendar API ---
        print("\n--- Autenticando com Google Calendar API ---")
        service = auth.get_calendar_service()

        if not service:
            print("Falha ao obter o serviço do Google Calendar. Saindo.")
            # sys.exit(1) # Removido para permitir que o finally feche o DB

        # --- 3. Buscar e processar eventos (coletando dados para BD) ---
        all_processed_events_for_db = []

        if service:
            print("\n--- Buscando e processando eventos dos calendários (no range da semana atual)... ---")

            for calendar_id in CALENDAR_IDS:
                events = fetch_events_from_calendar(service, calendar_id, time_min_rfc3339, time_max_rfc3339)
                if events:
                    # process_events_for_db agora filtra eventos com "Cancelar:" no summary e define status_evento
                    processed_events = process_events_for_db(events, calendar_id)
                    all_processed_events_for_db.extend(processed_events)
                else:
                    print(f"\n--- Nenhum evento encontrado para o calendário {calendar_id} no range especificado. ---")

            print(f"\n--- Busca e processamento de todos os calendários concluído. Total de eventos processados para BD: {len(all_processed_events_for_db)} ---")

        else:
             print("\nAutenticação com Google Calendar falhou. Pulando busca e processamento de eventos.")


        # DEBUG PRINT
        print(f"\nDebug: Total de eventos processados e prontos para UPSERT: {len(all_processed_events_for_db)}")


        # --- 4. Conectar ao Banco de Dados e realizar UPSERT ---
        print("\n--- Conectando ao Banco de Dados ---")
        db_conn = None
        db_cursor = None

        try:
            db_conn, db_cursor = database.connect_db()

            if db_conn is None or db_cursor is None:
               print("Falha ao obter conexão com o banco de dados. O processo continuará, mas os dados NÃO serão salvos no BD.")
            else:
               print("Conexão com o banco de dados estabelecida com sucesso.")

               # --- 5. Realizar UPSERT no Banco de Dados ---
               print(f"\nRealizando UPSERT de {len(all_processed_events_for_db)} eventos no Banco de Dados...")

               if not all_processed_events_for_db:
                   print("Nenhum evento processado para realizar o UPSERT.")
               else:
                   # Definição do upsert_sql para 10 colunas e 10 placeholders (Adicionado status_evento)
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

                   # Construção da lista data_to_upsert com 10 elementos por tupla
                   current_utc_time = datetime.datetime.now(UTC)

                   data_to_upsert = [
                       (
                           event_data.get('id_google_calendar'), # 1
                           (event_data.get('servico_agendado').strip() if isinstance(event_data.get('servico_agendado'), str) else event_data.get('servico_agendado')) or None, # 2
                           (event_data.get('attendees_emails_string').strip() if isinstance(event_data.get('attendees_emails_string'), str) else event_data.get('attendees_emails_string')) or None, # 3
                           event_data.get('start_time'), # 4
                           (event_data.get('telefone').strip() if isinstance(event_data.get('telefone'), str) else event_data.get('telefone')) or None, # 5
                           (event_data.get('numero_crf').strip() if isinstance(event_data.get('numero_crf'), str) else event_data.get('numero_crf')) or None, # 6
                           (event_data.get('nome_convidado').strip() if isinstance(event_data.get('nome_convidado'), str) else event_data.get('nome_convidado')) or None, # 7
                           event_data.get('local_evento'), # 8
                           current_utc_time, # 9 (fetched_at)
                           event_data.get('status_evento') # 10 (status_evento - 'A' ou 'C')
                       )
                       for event_data in all_processed_events_for_db
                   ]

                   # LINHAS DE DEBUG DO UPSERT
                   print("\n--- Informações de Debug para UPSERT ---")
                   print(f"SQL da UPSERT:\n{upsert_sql}")
                   print(f"Número de placeholders %s no SQL: {upsert_sql.count('%s')}")
                   print(f"Número total de eventos para UPSERT após processamento: {len(data_to_upsert)}")
                   if data_to_upsert:
                       print(f"Número de elementos na PRIMEIRA tupla: {len(data_to_upsert[0])}")
                       # print(f"Primeira tupla para UPSERT: {data_to_upsert[0]}")
                   print("--- Fim das Informações de Debug ---")

                   # Execução do UPSERT
                   if data_to_upsert: # Só executa se houver dados para UPSERT
                       db_cursor.executemany(upsert_sql, data_to_upsert)
                       db_conn.commit()
                       print(f"UPSERT de {len(data_to_upsert)} eventos concluído com sucesso.")
                   else:
                       print("Nenhum dado para realizar UPSERT no banco de dados.")


        except OperationalError as e:
           if db_conn: db_conn.rollback()
           print(f"\n--- ERRO OPERACIONAL durante o UPSERT no BD ---")
           print(f"Detalhes do Erro: {e}")
           print("Ocorreram erros operacionais durante o UPSERT no BD. Transaction rolled back.")
        except Error as e:
           if db_conn: db_conn.rollback()
           print(f"\n--- ERRO GERAL durante o UPSERT no BD ---")
           print(f"Detalhes do Erro: {e}")
           print("Ocorreram erros gerais durante o BD. Transaction rolled back.")
        except Exception as e:
           if db_conn: db_conn.rollback()
           print(f"\n--- ERRO INESPERADO durante o UPSERT no BD ---")
           print(f"Detalhes do Erro: {e}")
           print("Ocorreu um erro inesperado durante o UPSERT no BD. Transaction rolled back.")

    except Exception as e:
        print(f"\n--- ERRO durante o Processamento Inicial (Antes ou durante a Conexão ao BD) ---")
        print(f"Detalhes do Erro: {e}")

    finally:
        if db_cursor is not None:
            try:
                db_cursor.close()
                print("Cursor do BD fechado.")
            except Error as e:
                print(f"AVISO: Erro ao fechar cursor do BD: {e}", file=sys.stderr)

        if db_conn is not None:
            try:
                db_conn.close()
                print("Conexão com o PostgreSQL fechada.")
            except Error as e:
                 print(f"AVISO: Erro ao fechar conexão com o BD: {e}", file=sys.stderr)


        print("\n--- Processo Concluído ---")
