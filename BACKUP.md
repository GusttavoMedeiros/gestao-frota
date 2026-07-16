# Backup automático diário (GitHub Actions)

Todo dia à meia-noite, um robô gratuito do próprio GitHub baixa o banco
(`frota.db`) do site e guarda no repositório **privado** `frota-backups`.
Cada dia vira um ponto de restauração: dá para recuperar o banco de
qualquer data pelo histórico de commits.

> Por que assim? O plano grátis do PythonAnywhere não tem mais tarefas
> agendadas (mudança de jan/2026) e também bloqueia e-mail. Então quem
> agenda é o GitHub: ele **busca** o backup no site, em vez de o site enviar.

Como funciona a segurança: o site tem uma rota especial de backup protegida
por uma **chave secreta longa** (não usa login). A chave existe em só dois
lugares: um arquivo no servidor e o cofre de segredos do GitHub. Sem a chave,
a rota responde "página não encontrada", como se não existisse.

A configuração é feita uma única vez, em 4 passos.

---

## Passo 1 — Criar a chave secreta no servidor

No PythonAnywhere, abra **Consoles → Bash** e rode:

```bash
python3.10 -c "import secrets; print(secrets.token_urlsafe(48))" > ~/gestao-frota/chave_backup.txt
cat ~/gestao-frota/chave_backup.txt
```

A segunda linha mostra a chave (um texto longo aleatório). **Copie-a** —
vamos usá-la no passo 2. Depois vá na aba **Web** e clique em **Reload**.

> O arquivo `chave_backup.txt` fica só no servidor. Ele está no `.gitignore`,
> então nunca sobe para o GitHub junto com o código.

## Passo 2 — Guardar a chave no cofre do GitHub

1. Abra o repositório **frota-backups** no GitHub.
2. **Settings** (do repositório) → **Secrets and variables** → **Actions**.
3. Botão **New repository secret**:
   - Name: `CHAVE_BACKUP`
   - Secret: cole a chave copiada no passo 1
4. **Add secret**.

## Passo 3 — Criar o robô (workflow)

1. Ainda no repositório **frota-backups**: **Add file → Create new file**.
2. No campo do nome, digite exatamente (as barras criam as pastas):

   ```
   .github/workflows/backup.yml
   ```

3. Cole dentro o conteúdo do arquivo `workflow-backup.yml` que está no
   repositório `gestao-frota` (abra-o lá, clique no botão de copiar).
4. **Commit changes**.

## Passo 4 — Testar sem esperar a meia-noite

1. No repositório **frota-backups**, abra a aba **Actions**.
2. Clique em **Backup diário do frota.db** (menu à esquerda) →
   botão **Run workflow** → **Run workflow** (verde).
3. Aguarde ~30 segundos e recarregue a página. Bolinha **verde** = funcionou:
   o arquivo `frota.db` aparece/atualiza na página inicial do repositório.
   Bolinha vermelha = clique nela e me mande o texto do erro.

---

## Como restaurar um backup

1. No repositório `frota-backups` → arquivo `frota.db` → **History**.
2. Clique no commit do dia desejado → no arquivo → **Download raw file**.
3. No PythonAnywhere, aba **Files**, entre em `gestao-frota/` e suba o
   arquivo baixado no lugar do `frota.db` atual (guarde uma cópia do atual).
4. Aba **Web** → **Reload**.

## Backup manual (extra)

No menu lateral do sistema há o link **Baixar backup** — baixa uma cópia
segura do banco na hora, no computador ou no celular.

## Avisos importantes

- **Confira 1x por mês** se o repositório `frota-backups` tem commits
  recentes. Se o robô falhar, o GitHub também te avisa por e-mail.
- O GitHub pode desativar robôs de repositórios parados há 60 dias — como o
  banco muda todo dia, isso não deve acontecer; se um dia ele avisar por
  e-mail, é só clicar no botão de reativar.
- O plano grátis do PythonAnywhere continua exigindo **login no site deles
  periodicamente** para o web app não hibernar — eles avisam por e-mail;
  entre e clique no botão de renovar quando pedir.
- Se um dia a chave vazar, gere outra (passo 1) e atualize o segredo
  (passo 2). Nada mais muda.
