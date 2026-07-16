"""Backup automático diário do banco (frota.db) para um repositório PRIVADO no GitHub.

Como funciona:
1. Faz uma cópia segura do frota.db (mesmo com o site no ar, sem corromper).
2. Salva a cópia dentro da pasta ~/frota-backups (que é um clone do repositório privado).
3. Faz commit e push. Cada dia vira um "ponto de restauração" no GitHub —
   dá para voltar o banco de QUALQUER dia, pelo histórico de commits.

Configuração completa no arquivo BACKUP.md.
Este script é executado pela aba "Tasks" do PythonAnywhere, uma vez por dia.
"""

import os
import sqlite3
import subprocess
import sys
from datetime import date

# Onde está o banco (mesma pasta deste script)
BASE = os.path.abspath(os.path.dirname(__file__))
ORIGEM = os.path.join(BASE, "frota.db")

# Clone do repositório privado de backups (criado uma única vez, ver BACKUP.md)
PASTA_BACKUP = os.path.expanduser("~/frota-backups")
DESTINO = os.path.join(PASTA_BACKUP, "frota.db")


def erro(mensagem):
    print("ERRO:", mensagem)
    sys.exit(1)


if not os.path.exists(ORIGEM):
    erro(f"Banco não encontrado em {ORIGEM}. O site já rodou pelo menos uma vez?")
if not os.path.isdir(os.path.join(PASTA_BACKUP, ".git")):
    erro(f"A pasta {PASTA_BACKUP} não existe ou não é um repositório git. "
         "Siga o passo a passo do BACKUP.md.")

# 1) Cópia consistente do banco (API de backup do SQLite — não corrompe
#    mesmo se alguém estiver salvando um registro neste exato momento).
conexao_origem = sqlite3.connect(ORIGEM)
conexao_destino = sqlite3.connect(DESTINO)
with conexao_destino:
    conexao_origem.backup(conexao_destino)
conexao_origem.close()
conexao_destino.close()
print(f"Cópia feita: {DESTINO}")


def git(*argumentos):
    return subprocess.run(["git", "-C", PASTA_BACKUP, *argumentos],
                          capture_output=True, text=True)


# 2) Commit e push
git("add", "frota.db")
resultado = git("commit", "-m", f"Backup automático de {date.today().strftime('%d/%m/%Y')}")
saida = resultado.stdout + resultado.stderr
if "nothing to commit" in saida:
    print("Nenhuma mudança no banco desde o último backup. Nada a enviar.")
    sys.exit(0)
if resultado.returncode != 0:
    erro("Falha no commit:\n" + saida)

envio = git("push")
if envio.returncode != 0:
    erro("Falha ao enviar para o GitHub (o token expirou?):\n"
         + envio.stdout + envio.stderr)

print("Backup enviado para o GitHub com sucesso.")
