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
RUN pip install --no-cache-dir -r requirements.txt
# Install Celery (pulled from requirements.txt)

# Copy project files
COPY . .

# Expose port for Django
EXPOSE 8000

# Default command to run the Django development server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
