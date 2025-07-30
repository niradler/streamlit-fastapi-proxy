#!/bin/bash

# Publish script for streamlit-fastapi-proxy
set -e

echo "🚀 Publishing streamlit-fastapi-proxy to PyPI..."

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo "❌ Error: pyproject.toml not found. Run this script from the project root."
    exit 1
fi

# Build the package
echo "📦 Building package..."
uv run python -m build

# Check if build was successful
if [ ! -f "dist/streamlit_fastapi_proxy-*.whl" ]; then
    echo "❌ Error: Build failed. Check the output above."
    exit 1
fi

echo "✅ Build successful!"

# Ask user if they want to publish
read -p "Do you want to publish to PyPI? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "📤 Publishing to PyPI..."
    uv run twine upload dist/*
    echo "✅ Published successfully!"
else
    echo "📦 Package built successfully. Files are in dist/ directory."
    echo "To publish manually, run: uv run twine upload dist/*"
fi 