import subprocess
import sys
import os

# Lista dos scripts a serem executados na ordem desejada
scripts_para_executar = [
    "busca_eventos_dia.py", # Primeiro, busca/atualiza os eventos na tabela principal
    "atualizar_cache_agenda_diaria.py"  # Depois, reconstrói o cache diário
]

print("Iniciando a execução da sequência de scripts...")

# Itera sobre a lista e executa cada script
for script in scripts_para_executar:
    print(f"\nExecutando: {script}...")

    # Verifica se o arquivo existe antes de tentar executar
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), script)
    if not os.path.exists(script_path):
        print(f"ERRO: O script '{script}' não foi encontrado em '{script_path}'.")
        print("Por favor, verifique se o arquivo existe no mesmo diretório ou ajuste o caminho.")
        print("\nParando a execução da sequência.")
        sys.exit(1) # Sai com um código de erro

    try:
        # Executa o script usando o interpretador Python atual
        # check=True fará com que uma CalledProcessError seja levantada
        # se o script retornar um código de saída diferente de zero (indicando erro)
        # capture_output=True e text=True capturam a saída e erros como texto
        # Adicionamos encoding='utf-8' para lidar com caracteres especiais na saída
        resultado = subprocess.run(
            [sys.executable, script_path], # Usa o caminho absoluto do script
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            cwd=os.path.dirname(os.path.abspath(__file__)) # Garante que o diretório de trabalho seja onde este script está
        )

        print(f"'{script}' executado com sucesso (baseado no código de saída).")

        # Opcional: Imprimir a saída e erros dos scripts executados
        if resultado.stdout:
            print("--- Saída do script ---")
            print(resultado.stdout.strip())
            print("-----------------------")
        if resultado.stderr:
             print("--- Erros/Warnings do script (stderr) ---")
             print(resultado.stderr.strip()) # stderr pode conter warnings mesmo em sucesso
             print("-----------------------------------------")


    except subprocess.CalledProcessError as e:
        # Captura erros que ocorrem se o script retornar um status de falha (non-zero exit code)
        print(f"ERRO: O script '{script}' falhou com código de saída {e.returncode}.")
        print(f"Detalhes do erro (stderr):\n{e.stderr}")
        print(f"Saída padrão (stdout):\n{e.stdout}") # Imprime stdout também em caso de erro para depuração
        print("\nParando a execução da sequência devido a um erro reportado pelo script.")
        sys.exit(1) # Sai com um código de erro

    except FileNotFoundError:
        # Este catch é mais para o sys.executable, o script_path já é verificado acima.
        print(f"ERRO: O interpretador Python ('{sys.executable}') ou o script '{script_path}' não foi encontrado.")
        print("Certifique-se de que o Python está no PATH e o script existe.")
        print("\nParando a execução da sequência.")
        sys.exit(1)

    except Exception as e:
        # Captura outros erros inesperados que possam ocorrer
        print(f"Ocorreu um erro inesperado ao executar '{script}': {e}")
        import traceback
        traceback.print_exc()
        print("\nParando a execução da sequência devido a um erro inesperado.")
        sys.exit(1)


print("\nTodos os scripts da rotina foram executados com sucesso!")
