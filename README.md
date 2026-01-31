# CheckCraft Preview Site

This repo includes a lightweight web experience that showcases the check PDF generator
and provides an interactive preview of check details, plus a backend endpoint that
generates the same PDF output as the CLI.

## Run with Docker Compose

Use the provided `docker-compose.yml` to build and start the web app:

```bash
docker compose up --build
```

Then visit `http://localhost:8888`.

Docker Compose already mounts a dedicated volume for settings at `/data`, so presets
and global settings are persisted between runs.

## Blank check runs

Open `http://localhost:8080/blank_checks.html` to print blank checks. Save an account profile,
enter the first check number and total checks, then confirm whether the print was successful
to advance the stored check number.

## Configuration

The app supports environment variables to integrate with DSQL and to control how it
stores settings and cached credentials. You can also set DSQL values in the
**Global settings** screen at `http://localhost:8080/settings.html`, which persists
the same values in the user config file.

### DSQL settings (SSO-backed)

These values are required to use DSQL-backed accounts. Set them in the Global settings
page or as environment variables before starting the app:

```bash
export START_URL="https://example.awsapps.com/start"
export SSO_REGION="us-west-2"
export ACCOUNT_ID="123456789012"
export ROLE_NAME="MyRole"
export AWS_REGION="us-west-2"
export DB_NAME="postgres"
export DB_USER="dbuser"
export TAG_KEY="environment"
export TAG_VALUE="production"
```

Optional overrides:

- `DB_HOST` / `DB_ID`: bypass tag-based discovery with a known host or DSQL cluster ID.
- `SSO_OPEN_BROWSER=false`: disable opening the browser during SSO login.

For Docker, pass the same variables with `-e` flags (or use an `.env` file) so the
container has access to them.

### Cache storage

SSO and DSQL tokens can be cached in a file or the system keyring. In the web app,
the defaults are set to file-backed caches.

- `SSO_CACHE_BACKEND` / `DSQL_CACHE_BACKEND`: `file`, `keyring`, or `auto`.
- `SSO_CACHE_PATH` / `DSQL_CACHE_PATH`: explicit cache file paths.
- `SSO_CACHE_FILENAME` / `DSQL_CACHE_FILENAME`: override cache filenames.

### Fonts

If you want to use MICR or Avenir fonts, add `fonts/AvenirBook.ttf` and
`fonts/MICR.ttf` under the project root. The default CLI and web flow work
without them, but advanced templates rely on those files.

### Settings storage

The app stores presets, saved accounts, and global settings in `settings.json` under
`SETTINGS_DIR` (default: `./data`). It also writes a separate user config file for
DSQL settings under the OS user config directory (or `SETTINGS_DIR` if
`platformdirs` is unavailable). Set `SETTINGS_DIR` to override the base location
(for example, to persist data in a container volume).

## Run locally without Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## CLI usage

Use the existing CLI to generate a printable PDF (matches the web flow):

```bash
python cli_print_check.py
```

The CLI produces `check.pdf` in the project root.
