# copia_dados.py - Adicionando filtro WHERE tpcli = 'F'

import pyodbc
import sys
import database
from psycopg2 import OperationalError, Error
from collections import defaultdict

# --- Configurações do SQL Server ---
SQLSERVER_CONN_STR = """DRIVER={ODBC Driver 17 for SQL Server};Server=regionalgo.cisantec.com.br,6060;Database=DBCRF_GO;Uid=regional;Pwd=@c3$$0027152024_go;"""
# >>> MODIFICAÇÃO AQUI: Adicionando a cláusula WHERE tpcli = 'F'
SQLSERVER_QUERY = "SELECT regcli, nome, EMres, fone FROM frt WHERE tpcli = 'F'"

# --- Configurações do PostgreSQL ---
PG_TABLE_NAME = "farmaceuticos_frt"
PG_COLUMNS = ["regcli", "nome", "emres", "fone"]

# --- SQL para UPSERT ---
UPSERT_SQL = f"""
INSERT INTO {PG_TABLE_NAME} ({", ".join(PG_COLUMNS)})
VALUES ({", ".join(["%s"] * len(PG_COLUMNS))})
ON CONFLICT (regcli) DO UPDATE
SET
    nome = EXCLUDED.nome,
    emres = EXCLUDED.emres,
    fone = EXCLUDED.fone;
"""

# --- Função para copiar os dados ---
# (O restante do código da função copy_frt_data() e do bloco if __name__ == '__main__':
#  continua sendo o mesmo da versão anterior com UPSERT e verificação de duplicados)

def copy_frt_data():
    # ... (código da função copy_frt_data do script anterior) ...
    # O código de conexão, fetchall, verificação de duplicados,
    # conexão PG e executemany com UPSERT permanecem os mesmos.
    # A única diferença é que 'frt_data' conterá apenas os registros filtrados.
    # ... (resto da função, incluindo try/finally e fechamento de conexões) ...
    sqlserver_conn = None
    sqlserver_cursor = None
    pg_conn = None
    pg_cursor = None
    frt_data = []

    print("--- Iniciando processo de cópia/atualização de dados da tabela frt (Filtro: tpcli='F') ---") # Atualizado a mensagem inicial

    try:
        print(f"\n--- Conectando ao SQL Server via ODBC ---")
        try:
            sqlserver_conn = pyodbc.connect(SQLSERVER_CONN_STR)
            sqlserver_cursor = sqlserver_conn.cursor()
            print("Conexão com o SQL Server estabelecida com sucesso.")
        except pyodbc.Error as ex:
            sqlstate = ex.args[0]
            print(f"Erro ao conectar ao SQL Server ou executar consulta ODBC. SQLSTATE: {sqlstate}")
            print(f"Detalhes do Erro: {ex}")
            if len(ex.args) > 1:
                 print(f"Erro ODBC: {ex.args[1]}")
            return False

        print(f"\n--- Consultando dados na tabela frt do SQL Server (Filtro: tpcli='F') ---") # Atualizado a mensagem da consulta
        try:
            sqlserver_cursor.execute(SQLSERVER_QUERY)
            frt_data = sqlserver_cursor.fetchall()
            print(f"Consulta SQL Server concluída. Encontrados {len(frt_data)} registros.")
        except pyodbc.Error as ex:
             sqlstate = ex.args[0]
             print(f"Erro ao executar a consulta no SQL Server. SQLSTATE: {sqlstate}")
             print(f"Detalhes do Erro: {ex}")
             if len(ex.args) > 1:
                  print(f"Erro ODBC: {ex.args[1]}")
             return False


        if not frt_data:
            print("Nenhum dado encontrado na tabela frt com tpcli='F' para copiar.") # Atualizado mensagem
            return True

        print(f"\n--- Verificando duplicados no lote de {len(frt_data)} registros obtidos ---")
        regcli_counts = defaultdict(int)
        duplicate_regclis = []

        for row in frt_data:
            regcli_value = str(row[0])
            regcli_counts[regcli_value] += 1

        for regcli_value, count in regcli_counts.items():
            if count > 1:
                duplicate_regclis.append(f"{regcli_value} (aparece {count} vezes)")

        if duplicate_regclis:
            print(f"\n--- ATENÇÃO: Duplicados encontrados no lote de dados de origem (tpcli='F')! ---") # Atualizado mensagem
            print("Os seguintes valores de 'regcli' aparecem mais de uma vez:")
            for dup in duplicate_regclis[:20]:
                 print(f"- {dup}")
            if len(duplicate_regclis) > 20:
                print(f"... e mais {len(duplicate_regclis) - 20} outros regclis duplicados.")
            print("Estes duplicados significam que a última ocorrência no lote para um 'regcli' específico será a usada para inserir/atualizar no destino.")
            print("Continuando o processo de cópia/atualização...")
        else:
            print("Nenhum duplicado encontrado no lote de dados de origem.")


        print(f"\n--- Conectando ao PostgreSQL usando database.py ---")
        pg_conn, pg_cursor = database.connect_db()
        if pg_conn is None or pg_cursor is None:
            print("Falha ao conectar ao banco de dados PostgreSQL.")
            return False

        print("Conexão com o PostgreSQL estabelecida com sucesso.")

        print(f"\n--- Preparando e executando UPSERT na tabela '{PG_TABLE_NAME}' do PostgreSQL ---")

        try:
            print(f"Iniciando UPSERT de {len(frt_data)} registros no PostgreSQL...")
            data_to_insert = [(str(row[0]), row[1], row[2], row[3]) for row in frt_data]

            pg_cursor.executemany(UPSERT_SQL, data_to_insert)
            print("Execução de UPSERT em lote concluída.")

            pg_conn.commit()
            print(f"Transação confirmada. Registros na tabela '{PG_TABLE_NAME}' foram inseridos/atualizados com sucesso.")
            return True

        except OperationalError as e:
           print(f"\n--- ERRO OPERACIONAL durante o UPSERT no BD PostgreSQL ---")
           print(f"Detalhes do Erro: {e}")
           print("Ocorreu um erro operacional durante o UPSERT.")
           pg_conn.rollback()
           return False
        except Error as e:
           print(f"\n--- ERRO GERAL durante o UPSERT no BD PostgreSQL ---")
           print(f"Detalhes do Erro: {e}")
           print("Ocorreu um erro geral durante o UPSERT.")
           pg_conn.rollback()
           return False
        except Exception as e:
           print(f"\n--- ERRO INESPERADO durante o UPSERT no BD PostgreSQL ---")
           print(f"Detalhes do Erro: {e}")
           print("Ocorreu um erro inesperado durante o UPSERT.")
           pg_conn.rollback()
           return False

    except Exception as e:
        print(f"\n--- ERRO INESPERADO durante o processo de cópia/atualização ---")
        print(f"Detalhes do Erro: {e}")
        return False

    finally:
        print("\n--- Fechando conexões ---")
        if sqlserver_cursor:
            try:
                sqlserver_cursor.close()
                print("Cursor SQL Server fechado.")
            except Exception as e:
                 print(f"AVISO: Erro ao fechar cursor SQL Server: {e}", file=sys.stderr)
        if sqlserver_conn:
            try:
                sqlserver_conn.close()
                print("Conexão SQL Server fechada.")
            except Exception as e:
                 print(f"AVISO: Erro ao fechar conexão SQL Server: {e}", file=sys.stderr)

        if pg_cursor:
            try:
                pg_cursor.close()
                print("Cursor PostgreSQL fechado.")
            except Error as e:
                print(f"AVISO: Erro ao fechar cursor PostgreSQL: {e}", file=sys.stderr)

        if pg_conn:
            try:
                pg_conn.close()
                print("Conexão PostgreSQL fechada.")
            except Error as e:
                 print(f"AVISO: Erro ao fechar conexão PostgreSQL: {e}", file=sys.stderr)
        print("--- Fim do fechamento de conexões ---")


if __name__ == '__main__':
    success = copy_frt_data()
    if success:
        print("\n--- Processo de cópia/atualização de dados concluído com SUCESSO (Filtro: tpcli='F'). ---") # Atualizado mensagem final
        sys.exit(0)
    else:
        print("\n--- Processo de cópia/atualização de dados concluído com FALHA (Filtro: tpcli='F'). ---") # Atualizado mensagem final
        sys.exit(1)