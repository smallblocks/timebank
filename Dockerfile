FROM python:3.12-slim

# Python deps
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Backend
COPY backend/ /app/backend/

# Frontend static files (served by FastAPI)
COPY static/ /app/static/

# Entrypoint
COPY docker_entrypoint.sh /app/docker_entrypoint.sh
RUN chmod +x /app/docker_entrypoint.sh

WORKDIR /app

# Data volume
RUN mkdir -p /data

EXPOSE 80

CMD ["/app/docker_entrypoint.sh"]
