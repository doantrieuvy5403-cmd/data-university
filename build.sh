#!/usr/bin/env bash
set -e

# Install dependencies
pip install -r requirements.txt

# NOTE: Database seeding is handled by app.py (_auto_seed) on startup, and ONLY
# when the database is empty or data.xlsx changes. Do NOT wipe data on deploy.
