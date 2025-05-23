# Use official Python runtime as a parent image
FROM python:3.12-slim

# Set build arguments with defaults
ARG DJANGO_DEBUG=False
ARG DJANGO_SECRET_KEY=placeholder-replaced-at-runtime

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY} \
    DJANGO_DEBUG=${DJANGO_DEBUG}

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt ./
COPY requirements-test.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends redis-server ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-test.txt
# Celery is included in requirements.txt and installed above

# Copy project files
COPY . .
RUN chmod +x /app/start-with-redis.sh /app/start-web.sh

# Expose port for Django
EXPOSE 8000

ENTRYPOINT ["/app/start-with-redis.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
