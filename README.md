# Skills Marketplace

CS162 final project. A Flask app where people post what they want to learn or teach.

## Run locally

Use Python 3.12. On macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

On Windows (PowerShell), you can run the virtual environment's Python directly:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

Then open http://127.0.0.1:5001.

### Command shortcuts

The Makefile supports macOS, Linux, and Windows with GNU Make installed. On macOS,
`make` is available through the Xcode Command Line Tools; Windows needs a separate
GNU Make installation available as `make` in your terminal. If `make` is unavailable,
use the manual commands above.

Run these from the project root. They use `.venv` directly, so activation isn't needed.
The Makefile selects `.venv/bin/python` on macOS/Linux and
`.venv/Scripts/python.exe` on Windows.

```bash
make setup  # create the virtual environment and install dependencies
make dev    # start the app on port 5001 with hot reload
make test   # run tests
```

Running `make` without a target also starts the app.

## Run tests

```bash
pytest
```

Or run `make test` from the project root. On Windows without Make, use
`.\.venv\Scripts\python.exe -m pytest`.

### Writing tests

Create a file named `test_*.py` inside `tests/`, and name each test function
`test_*` so pytest discovers it. Shared fixtures are defined in `tests/conftest.py`;
request them as function arguments without importing them.

Use `client` for a normal, initially signed-out client. It's suitable for public
pages, testing login/signup, and checking that protected pages redirect visitors:

```python
def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200


def test_profile_requires_login(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login?")
```

Use `authenticated_client` when a test needs a signed-in user. This fixture creates
a test user and signs in through `/login` before returning the client:

```python
def test_profile_page(authenticated_client):
    response = authenticated_client.get("/profile")
    assert response.status_code == 200
```

The client keeps cookies between requests within a test, so `client` also becomes
signed in if the test successfully posts to `/login` or `/signup`. Tests use a fresh
in-memory database for each test, separate from your local development database.

To run just one test file:

```bash
python -m pytest tests/test_screens.py
```

This command assumes your virtual environment is activated. On Windows without
activation, use `.\.venv\Scripts\python.exe -m pytest tests/test_screens.py`.

## Run with Docker

```bash
docker build -t skills-marketplace .
docker run -p 5001:5001 skills-marketplace
```

## Layout

```
run.py              starts the app
Makefile            setup, dev and test shortcuts
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
