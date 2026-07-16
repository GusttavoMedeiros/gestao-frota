# Backup automático diário (GitHub)

Todo dia, uma cópia do banco (`frota.db`) é enviada automaticamente para um
repositório **privado** no GitHub. Cada dia vira um ponto de restauração:
dá para recuperar o banco de qualquer data pelo histórico de commits.

> Por que GitHub e não e-mail? O plano grátis do PythonAnywhere **bloqueia
> envio de e-mail** (SMTP). O GitHub funciona normalmente e ainda guarda o
> histórico de versões de graça.

A configuração é feita **uma única vez**, em 4 passos (uns 10 minutos).

---

## Passo 1 — Criar o repositório privado

1. No GitHub, clique em **New repository**.
2. Nome: `frota-backups`.
3. Marque **Private** (importante: o banco tem dados da empresa).
4. Marque **Add a README file** (só para o repositório não nascer vazio).
5. Clique em **Create repository**.

## Passo 2 — Criar o token de acesso

O token é a "senha" que o servidor usa para enviar o backup. Ele só terá
permissão nesse repositório de backups — em nenhum outro.

1. No GitHub: foto de perfil → **Settings** → **Developer settings** →
   **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
2. Preencha:
   - **Token name:** `backup-frota`
   - **Expiration:** `Custom` → escolha a data mais distante possível
     (anote no calendário: quando vencer, é só gerar outro e repetir o passo 3).
   - **Repository access:** `Only select repositories` → selecione `frota-backups`.
   - **Permissions** → **Repository permissions** → **Contents:** `Read and write`.
3. Clique em **Generate token** e **copie o token** (começa com `github_pat_`).
   Ele só aparece uma vez.

## Passo 3 — Preparar a pasta no PythonAnywhere

No PythonAnywhere, abra **Consoles → Bash** e rode, uma linha por vez
(troque `SEU_USUARIO_GITHUB` e `SEU_TOKEN` pelos seus):

```bash
git clone https://SEU_TOKEN@github.com/SEU_USUARIO_GITHUB/frota-backups.git ~/frota-backups
cd ~/frota-backups
git config user.name "Backup automatico"
git config user.email "backup@frota.local"
```

Teste o script manualmente:

```bash
python3.10 ~/gestao-frota/backup_para_github.py
```

Deve aparecer `Backup enviado para o GitHub com sucesso.` — confira no site do
GitHub se o arquivo `frota.db` apareceu no repositório `frota-backups`.

## Passo 4 — Agendar para rodar todo dia

1. No PythonAnywhere, abra a aba **Tasks**.
2. Em **Scheduled tasks**, escolha um horário (ex.: `03:00` — o horário é UTC,
   que dá meia-noite no Brasil) e cole o comando:

   ```
   python3.10 /home/SEU_USUARIO_PYTHONANYWHERE/gestao-frota/backup_para_github.py
   ```

3. Clique em **Create**. Pronto — backup diário automático.

---

## Como restaurar um backup

1. No GitHub, abra o repositório `frota-backups` → arquivo `frota.db` →
   **History** (histórico de commits).
2. Clique no commit do dia desejado → clique no arquivo → **Download raw file**.
3. No PythonAnywhere, aba **Files**, entre em `gestao-frota/` e envie o arquivo
   baixado no lugar do `frota.db` atual (faça uma cópia do atual antes).
4. Na aba **Web**, clique em **Reload**.

## Backup manual (extra)

Dentro do próprio sistema, no menu lateral, há o link **Baixar backup** — ele
baixa uma cópia segura do banco na hora, direto no seu computador ou celular.

## Avisos importantes

- **O token expira.** Quando vencer, o backup para de funcionar em silêncio.
  Anote a data no calendário. Para renovar: gere um novo token (passo 2) e rode
  no Bash do PythonAnywhere:
  ```bash
  cd ~/frota-backups
  git remote set-url origin https://NOVO_TOKEN@github.com/SEU_USUARIO_GITHUB/frota-backups.git
  ```
- **Confira de vez em quando** (1x por mês) se o repositório `frota-backups`
  tem commits recentes. A aba **Tasks** do PythonAnywhere também mostra o log
  da última execução.
- O plano grátis do PythonAnywhere exige que você faça login no site deles a
  cada 3 meses — senão a conta (e o backup) param.
