#!/bin/bash

# Build the frontend
echo "Building frontend..."
cd frontend
npm install
npm run build
cd ..

# Start the Flask server
echo "Starting Flask server..."
python app.py 