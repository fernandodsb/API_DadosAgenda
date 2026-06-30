# database.py
import psycopg2
from psycopg2 import OperationalError, Error
import sys

# Detalhes da conexão (substitua SUA_SENHA_AQUI pela senha correta)
db_name = "agenda_crfgo"
db_user = "postgres"
db_port = "5430" # Porta alterada
db_host = "localhost"
db_password = "Crfgo!23" # <--- SUBSTITUA PELA SUA SENHA REAL (mantenha em segredo!)

def connect_db():
    """Estabelece e retorna a conexão e o cursor do banco de dados."""
    conn = None
    cursor = None
    try:
        print(f"Tentando conectar ao banco de dados '{db_name}' em '{db_host}:{db_port}' para o usuário '{db_user}'...")
        conn = psycopg2.connect(
            database=db_name,
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port,
            client_encoding='UTF8'
        )
        cursor = conn.cursor()
        print("Conexão com o banco de dados estabelecida com sucesso.")
        # Opcional: verificar versao do BD
        # cursor.execute("SELECT version();")
        # db_version = cursor.fetchone()
        # print(f"Versão do servidor PostgreSQL: {db_version[0]}")
        return conn, cursor
    except OperationalError as e:
        print(f"Erro operacional ao conectar ao banco de dados: {e}")
        # Não saímos aqui para que o script principal possa lidar com a falha
        return None, None
    except Error as e:
        print(f"Erro geral ao conectar ao banco de dados: {e}")
        return None, None
    except Exception as e:
        print(f"Ocorreu um erro inesperado ao conectar: {e}")
        return None, None

# Exemplo de uso (mantenha COMENTADO ao usar com main.py)
# if __name__ == '__main__':
#     print("Testando módulo database.py...")
#     conn, cursor = connect_db()
#     if conn and cursor:
#         print("Teste de conexão bem-sucedido.")
#         # Lembre-se de fechar explicitamente se usar fora de um try/finally
#         cursor.close()
#         conn.close()
#         print("Conexão fechada.")
#     else:
#         print("Teste de conexão falhou.")