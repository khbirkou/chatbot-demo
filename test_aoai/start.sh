#!/usr/bin/env bash
set -e

# FastAPI Backend (muss im Container erreichbar sein)
uvicorn app:app --host 0.0.0.0 --port 8000 &

# Streamlit Frontend (öffentlich)
streamlit run Chatbot.py \
  --server.address 0.0.0.0 \
  --server.port ${PORT:-8501} \
  --server.headless true \
  --server.enableCORS false \
  --server.enableXsrfProtection false
