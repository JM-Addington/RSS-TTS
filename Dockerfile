# Use official Python runtime as a parent image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    DJANGO_SECRET_KEY=dev-secret-key \
    DJANGO_DEBUG=True

# Set work directory
WORKDIR /app

# Install dependencies
COPY requirements.txt requirements-test.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir celery

# Copy project files
COPY . .

# Expose port for Django
EXPOSE 8000

# Default command to run the Django development server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
