#!/usr/bin/env bash
set -e

echo "==> Ensuring host directories exist..."
mkdir -p .logs

echo "==> Building and starting containers..."
docker compose up --build -d

echo "==> Waiting for web service to be healthy..."
until [ "$(docker inspect --format='{{.State.Health.Status}}' \
  $(docker compose ps -q web))" = "healthy" ]; do
  sleep 2
done

echo "==> Running migrations..."
docker compose exec web python manage.py migrate

echo "==> Loading initial data..."
docker compose exec web python manage.py load_initial_data

echo "==> Done. Services running:"
docker compose ps