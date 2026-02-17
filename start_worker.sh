#!/bin/bash

# Ensure we are in the script's directory
cd "$(dirname "$0")"

# UBERreal Worker Startup Script
# Robust installation with retries for unstable networks

echo "=== UBERreal Worker Startup ==="

# Function to install with retries
install_critical() {
    PACKAGE=$1
    echo "Installing critical package: $PACKAGE..."
    for i in {1..5}; do
        pip install $PACKAGE --upgrade --no-cache-dir --timeout 120 --retries 10 && return 0
        echo "Failed to install $PACKAGE, retrying in 5s... (Attempt $i/5)"
        sleep 5
    done
    echo "ERROR: Could not install $PACKAGE after 5 attempts."
    return 1
}

# Update pip
pip install --upgrade pip --no-cache-dir

# Install Critical Dependencies first
install_critical "runpod" || exit 1
install_critical "scikit-image" || exit 1
install_critical "requests" || exit 1

# Install other requirements (non-critical failure allowed)
echo "Installing other requirements from requirements.txt..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt --no-cache-dir --timeout 120 --retries 10 || echo "Warning: requirements.txt installation had issues, but continuing..."
else
    echo "requirements.txt not found, skipping..."
fi

# Explicitly install InsightFace (Critical for Face Swap)
if [ -f "scripts/install_insightface.sh" ]; then
    echo "Running scripts/install_insightface.sh..."
    bash scripts/install_insightface.sh || echo "Warning: InsightFace installation script failed."
fi

echo "Starting Serverless Handler..."
python3 -u engine/serverless_handler.py
