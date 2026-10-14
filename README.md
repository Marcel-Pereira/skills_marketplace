# Skills Marketplace

CS162 final project. A Flask app where people post what they want to learn or teach.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Then open http://127.0.0.1:5001.

## Run tests

```bash
pytest
```

## Run with Docker

```bash
docker build -t skills-marketplace .
docker run -p 5001:5001 skills-marketplace
```

## Layout

```
run.py              starts the app
app/__init__.py     create_app(): config, database, blueprints
app/config.py       secret key and database URL
app/routes.py       pages
app/templates/      Jinja pages, all extend base.html
app/static/         style.css
tests/              pytest tests
.github/            CI and the PR template
```

## How we work

- One branch per issue, e.g. `feature/login`. Never push to `main` directly.
- Open a PR, fill in the template, get one approval and green CI, then merge.
- MVPs are tagged `mvp-1`, `mvp-2`, `mvp-3`.
