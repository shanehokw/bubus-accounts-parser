#!/bin/zsh
# Double-click to start the app. It opens in your browser; close this window to stop it.
cd "$(dirname "$0")"
.venv/bin/streamlit run app.py
