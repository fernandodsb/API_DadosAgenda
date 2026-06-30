#GerarSenha.py
import bcrypt

# Senha que você quer hashear
senha_texto_puro = "Senha!23"

# Gerar um salt (valor aleatório) e hashear a senha
# bcrypt.gensalt() gera um salt com 12 rounds por padrão (bom para a maioria dos casos)
senha_hasheada = bcrypt.hashpw(senha_texto_puro.encode('utf-8'), bcrypt.gensalt())

# O resultado é um hash em bytes. Para armazenar no BD (VARCHAR/TEXT), converta para string.
senha_hasheada_str = senha_hasheada.decode('utf-8')

print(f"Senha original: {senha_texto_puro}")
print(f"Senha hasheada (para armazenar no BD): {senha_hasheada_str}")

# Exemplo de como você faria o UPDATE no BD (NÃO execute isso diretamente em produção sem backup!)
# UPDATE usuarios_sistema SET senha = 'SUA_SENHA_HASHEADA_AQUI' WHERE usuario = 'seu_usuario';