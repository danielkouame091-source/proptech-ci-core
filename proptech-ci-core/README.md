# proptech-ci-core

API de gestion immobilière pour la Côte d'Ivoire : biens, locataires, baux et loyers (FCFA).

## Lancer

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Documentation interactive : http://127.0.0.1:8000/docs

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -v
```
