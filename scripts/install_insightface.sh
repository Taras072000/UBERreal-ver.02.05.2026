#!/bin/bash
set -e

# Install InsightFace from pre-built wheel to avoid compilation issues
# Using a compatible version for Python 3.10 and CUDA 12.x
# Note: The wheel link might need update if Python version changes

echo "Installing InsightFace..."

# Option 1: Try pip install with --no-build-isolation (sometimes helps)
# pip install insightface==0.7.3 --no-build-isolation

# Option 2: Download pre-built wheel (Recommended for speed)
# We will use standard pip install but ensure all system dependencies are present first
# The Dockerfile already installs build-essential and python3-dev

pip install insightface==0.7.3
pip install onnxruntime-gpu==1.16.3

echo "InsightFace installed successfully."
