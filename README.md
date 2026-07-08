# Gestão de Frota

Sistema interno para gestão de frota de veículos: cadastro de veículos, motoristas,
controle de manutenções e abastecimentos.

## Tecnologia

- Python 3 + Flask
- Flask-SQLAlchemy (banco de dados SQLite, arquivo `frota.db`)
- Bootstrap 5 (via CDN) para a interface

## Como rodar o projeto

1. Crie um ambiente virtual (recomendado):

   ```
   python -m venv venv
   venv\Scripts\activate
   ```

2. Instale as dependências:

   ```
   pip install -r requirements.txt
   ```

3. Rode o servidor:

   ```
   python app.py
   ```

4. Acesse no navegador: http://127.0.0.1:5000

O banco de dados (`frota.db`) é criado automaticamente na primeira execução.
