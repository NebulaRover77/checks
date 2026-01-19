# CheckCraft Preview Site

This repo includes a lightweight web experience that showcases the check PDF generator
and provides an interactive preview of check details, plus a backend endpoint that
generates the same PDF output as the CLI.

## Run with Docker

```bash
docker build -t checkcraft .
docker run --rm -p 8080:8080 checkcraft
```

Then visit `http://localhost:8080`.

To persist saved presets, mount a dedicated volume for settings:

```bash
docker run --rm -p 8080:8080 -v checkcraft_settings:/data -e SETTINGS_DIR=/data checkcraft
```

## Blank check runs

Open `http://localhost:8080/blank_checks.html` to print blank checks. Save an account profile,
enter the first check number and total checks, then confirm whether the print was successful
to advance the stored check number.

## DSQL credentials

If you need to connect to a DSQL instance, provide credentials via environment variables
before starting the app:

```bash
export DSQL_HOST="your-dsql-host"
export DSQL_DATABASE="your-database"
export DSQL_USER="your-username"
export DSQL_PASSWORD="your-password"
```

For Docker, pass the same variables with `-e` flags (or use an `.env` file) so the
container has access to them.

> Note: If you want to use MICR or Avenir fonts, add `fonts/AvenirBook.ttf` and
> `fonts/MICR.ttf` under the project root. The default CLI and web flow work
> without them, but advanced templates rely on those files.

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
