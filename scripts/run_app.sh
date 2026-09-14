#!/usr/bin/env bash
# Start the PFAL digital-twin web dashboard (local): http://localhost:8501
cd "$(dirname "$0")/.." && exec .venv/bin/streamlit run app/streamlit_app.py "$@"
