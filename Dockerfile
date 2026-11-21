FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# La clé n'est utile qu'à la compilation des fichiers statiques ; la vraie clé vient de l'environnement.
RUN DJANGO_SECRET_KEY=build-only-key-build-only-key-build-only-key-0000 SUPABASE_URL=http://x SUPABASE_KEY=x \
    python manage.py collectstatic --noinput
RUN useradd -m app && chown -R app /app
USER app
EXPOSE 8000
CMD ["sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3 --timeout 60"]
