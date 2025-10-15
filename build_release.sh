#!/bin/bash
set -e

echo "=== Building embedding-atlas wheel with static files ==="

# Step 1: Build the frontend
echo "Building frontend packages..."
npm install
npm run build -w @embedding-atlas/density-clustering
npm run build -w @embedding-atlas/umap-wasm
npm run build -w @embedding-atlas/component
npm run build -w @embedding-atlas/table
npm run build -w @embedding-atlas/viewer

# Step 2: Copy static files to backend
echo "Copying static files to backend..."
cd packages/backend
rm -rf embedding_atlas/static embedding_atlas/widget_static
cp -r ../viewer/dist embedding_atlas/static

# Step 3: Build the Python wheel
echo "Building Python wheel..."
python -m pip install --upgrade build
python -m build --wheel

echo "=== Build complete! ==="
echo "Wheel location: packages/backend/dist/"
ls -lh dist/*.whl
