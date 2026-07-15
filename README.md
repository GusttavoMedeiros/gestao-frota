# KG Frota

Aplicativo PWA para gestão de veículos, motoristas, abastecimentos,
manutenções, despesas e documentos.

## Estrutura

- `app.py`, `api.py` e `models.py`: Flask, API autenticada e banco SQLite.
- `web/`: código-fonte React/Vite da interface.
- `frontend/`: build pronto servido pelo Flask em `/`.
- `templates/` e `static/`: interface anterior, disponível em `/legacy`.

## Executar

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Acesse `http://127.0.0.1:5000`.

## Atualizar a interface

```bash
cd web
npm ci
npm test
npm run build
```

O build é gravado em `frontend/`. Ele deve ser versionado para que o
PythonAnywhere não precise instalar Node.js durante a publicação.
