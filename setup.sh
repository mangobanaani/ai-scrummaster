#!/usr/bin/env bash
set -euo pipefail

MODEL="${OLLAMA_MODEL:-qwen2.5:7b}"

echo "Checking Ollama..."
if ! docker compose ps ollama | grep -q "running"; then
  echo "Starting Ollama container..."
  docker compose up -d ollama
  echo "Waiting for Ollama to be ready..."
  until curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; do sleep 2; done
fi

echo "Checking if model '$MODEL' is available..."
if ! curl -sf http://localhost:11434/api/tags | grep -q "\"$MODEL\""; then
  echo "Pulling $MODEL (this may take a while)..."
  docker compose exec ollama ollama pull "$MODEL"
  echo "Model '$MODEL' ready."
else
  echo "Model '$MODEL' already present."
fi

echo "Starting remaining services..."
docker compose up -d
echo "Done. App running at http://localhost:8000"
