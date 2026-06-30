# auth.py
# Gerencia a autenticação com a Google Calendar API

import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Define o escopo necessário para a API (apenas leitura de eventos)
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

# Define os nomes padrão para os arquivos de credenciais e token
# Estes arquivos devem estar na mesma pasta onde você executa o script principal (main.py)
DEFAULT_CREDENTIALS_FILE = 'credentials.json'
DEFAULT_TOKEN_FILE = 'token.json' # Arquivo onde o token de refresh será salvo/lido

def get_calendar_service(credentials_file=DEFAULT_CREDENTIALS_FILE, token_file=DEFAULT_TOKEN_FILE, scopes=SCOPES):
    """Autentica com a Google Calendar API e retorna o objeto de serviço."""
    creds = None
    # Tenta carregar credenciais de um token salvo anteriormente
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, scopes)

    # Se não há credenciais válidas ou elas precisam ser atualizadas
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Se o token expirou mas tem um refresh token, tenta atualizar
            print("Token expirado, tentando atualizar credenciais...")
            try:
                 creds.refresh(Request())
                 print("Credenciais atualizadas com sucesso.")
            except Exception as e:
                 print(f"Erro ao tentar atualizar o token: {e}")
                 print("Forçando novo fluxo de autenticação completo...")
                 # Se a atualização falhar, força um novo fluxo
                 try:
                     flow = InstalledAppFlow.from_client_secrets_file(
                         credentials_file, scopes)
                     creds = flow.run_local_server(port=0)
                 except FileNotFoundError:
                     print(f"Erro: Arquivo de credenciais '{credentials_file}' não encontrado durante o refresh.")
                     return None

        else:
            # Se não tem credenciais salvas ou refresh token, inicia o fluxo completo (abre navegador)
            print("Iniciando novo fluxo de autenticação completo...")
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_file, scopes)
                print(f"Por favor, verifique seu navegador para completar a autenticação.")
                creds = flow.run_local_server(port=0)
            except FileNotFoundError:
                print(f"Erro: Arquivo de credenciais '{credentials_file}' não encontrado.")
                print("Certifique-se de ter baixado o JSON do Google Cloud Console,")
                print(f"renomeado para '{credentials_file}' e colocado na mesma pasta do script principal.")
                return None # Retorna None se o arquivo credentials.json não for encontrado

        # Salva as novas credenciais (ou as atualizadas) no arquivo token.json
        if creds: # Verifica se creds foram obtidas com sucesso
            with open(token_file, 'w') as token:
                token.write(creds.to_json())
            print(f"Credenciais salvas em '{token_file}' para uso futuro.")

    # Constrói e retorna o objeto de serviço da API
    if creds:
        try:
            # 'calendar' é o nome do serviço, 'v3' é a versão da API.
            service = build('calendar', 'v3', credentials=creds)
            print("Serviço do Google Calendar criado com sucesso.")
            return service
        except HttpError as error:
            print(f'Ocorreu um erro na API ao construir o serviço: {error}')
            return None
        except Exception as e:
            print(f"Ocorreu um erro inesperado ao obter o serviço: {e}")
            return None
    else:
        # Retorna None se as credenciais não puderam ser obtidas em nenhuma etapa
        return None

# Exemplo de uso (mantenha comentado ao usar com main.py)
# if __name__ == '__main__':
#     print("Testando módulo auth.py...")
#     calendar_service = get_calendar_service()
#     if calendar_service:
#         print("Autenticação bem-sucedida.")
#     else:
#         print("Falha na autenticação.")