# Publicar o sistema grátis (PythonAnywhere)

Guia passo a passo para colocar o Gestão de Frota na internet **de graça**, com
endereço próprio e HTTPS (cadeado), para usar como app no celular de qualquer lugar.

> Por que PythonAnywhere e não Vercel/Netlify? Este sistema é Python (Flask) com
> banco SQLite, que precisa **guardar os dados**. Vercel/Netlify apagam o banco a
> cada atualização. O PythonAnywhere mantém tudo e é grátis.

---

## 1. Criar a conta

1. Acesse **https://www.pythonanywhere.com** e clique em **Pricing & signup** → **Create a Beginner account** (o plano gratuito).
2. Confirme o e-mail e faça login.

## 2. Baixar o projeto

1. No painel, abra **Consoles** → **Bash** (um terminal preto).
2. Rode, uma linha de cada vez:

   ```bash
   git clone https://github.com/GusttavoMedeiros/gestao-frota.git
   cd gestao-frota
   python3.10 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Gere uma chave secreta e **copie o resultado** (vai usar no passo 4):

   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

## 3. Criar o app web

1. Vá na aba **Web** → **Add a new web app** → **Next**.
2. Escolha **Manual configuration** (não escolha "Flask") → **Python 3.10** → **Next**.

   > ⚠️ A versão de Python escolhida aqui deve ser a **mesma** usada no comando
   > `python3.10 -m venv venv` do passo 2. Se o site oferecer outra versão
   > (ex.: 3.11), use-a nos dois lugares.
3. Na tela do app, ajuste:
   - **Source code:** `/home/SEU_USUARIO/gestao-frota`
   - **Virtualenv:** `/home/SEU_USUARIO/gestao-frota/venv`

   (troque `SEU_USUARIO` pelo seu nome de usuário do PythonAnywhere)

## 4. Configurar o arquivo WSGI

1. Ainda na aba **Web**, clique no link do **WSGI configuration file**.
2. Apague tudo e cole isto (trocando `SEU_USUARIO` e colando a chave do passo 2):

   ```python
   import os
   import sys

   caminho = '/home/SEU_USUARIO/gestao-frota'
   if caminho not in sys.path:
       sys.path.insert(0, caminho)

   os.environ['SECRET_KEY'] = 'COLE_A_CHAVE_GERADA_AQUI'
   os.environ['FLASK_DEBUG'] = '0'
   os.environ['ALLOWED_ORIGINS'] = 'https://kg-frota.vercel.app'

   from app import app as application
   ```

3. Salve (**Save**, canto superior direito).

## 5. Servir os arquivos visuais (CSS, ícones)

Na aba **Web**, seção **Static files**, clique em **Enter URL / Directory** e adicione:

| URL        | Directory                                   |
|------------|---------------------------------------------|
| `/static/` | `/home/SEU_USUARIO/gestao-frota/static`     |

## 6. Ligar

1. No topo da aba **Web**, clique no botão verde **Reload**.
2. Abra **https://SEU_USUARIO.pythonanywhere.com**.
3. Vai aparecer a tela de **Primeiro acesso** — crie seu usuário e senha. Pronto! 🎉

## 7. Instalar como app no celular

1. Abra a mesma URL (`https://SEU_USUARIO.pythonanywhere.com`) no navegador do celular.
2. Faça login.
3. No menu do navegador, toque em **Adicionar à tela inicial** (Android) ou
   **Compartilhar → Adicionar à Tela de Início** (iPhone).
4. O ícone do caminhão aparece na tela inicial e abre em tela cheia, como um app.

---

## Atualizar depois (quando mudarmos algo)

No **Bash console** do PythonAnywhere:

```bash
cd gestao-frota
git pull
```

Depois, na aba **Web**, clique em **Reload**. Seus dados (banco `frota.db`) **não são
apagados** — ele fica de fora do Git de propósito.

O frontend novo usa a API em `/api`. Depois de atualizar, confirme que
`https://SEU_USUARIO.pythonanywhere.com/api/dados` responde `401` sem login;
isso indica que a API está ativa e protegida.

## Observações

- O plano grátis dá o endereço `seu-usuario.pythonanywhere.com` com HTTPS incluso.
- Contas grátis pedem um login no site a cada 3 meses para continuarem ativas.
- Faça uma cópia do banco de vez em quando: na aba **Files**, baixe o `frota.db`.
