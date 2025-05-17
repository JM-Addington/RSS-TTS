# RSS-TTS

This project converts web articles and text into audio files using Django and Django REST Framework.

## Setup

Install dependencies in a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install Django~=5.0 djangorestframework~=3.14
```

Run the development server:

```bash
python manage.py runserver
```

## Tests

Activate the virtual environment and run:

```bash
python -m unittest discover -s tests
```
