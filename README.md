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
