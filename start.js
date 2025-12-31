#!/usr/bin/env node

/**
 * Start script for Vocify - runs both frontend and backend concurrently
 * 
 * Usage: node start.js
 * Or: npm run start (if added to package.json)
 */

import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Colors for terminal output
const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  blue: '\x1b[34m',
  yellow: '\x1b[33m',
  red: '\x1b[31m',
};

function log(color, message) {
  console.log(`${colors[color]}${message}${colors.reset}`);
}

// Check if .env exists
if (!fs.existsSync('.env')) {
  log('yellow', '⚠️  Warning: .env file not found in root directory');
}

// Copy .env to backend if needed
if (!fs.existsSync('backend/.env') && fs.existsSync('.env')) {
  log('blue', '📋 Copying .env to backend directory...');
  fs.copyFileSync('.env', 'backend/.env');
}

// Create logs directory
if (!fs.existsSync('logs')) {
  fs.mkdirSync('logs');
}

log('blue', '🚀 Starting Vocify...\n');

// Start backend
log('green', '🔧 Starting backend server (port 8888)...');
const backend = spawn('python3', [
  '-m', 'uvicorn',
  'app.main:app',
  '--reload',
  '--host', '0.0.0.0',
  '--port', '8888'
], {
  cwd: path.join(__dirname, 'backend'),
  stdio: ['ignore', 'pipe', 'pipe'],
});

backend.stdout.on('data', (data) => {
  process.stdout.write(`${colors.blue}[BACKEND]${colors.reset} ${data}`);
});

backend.stderr.on('data', (data) => {
  process.stderr.write(`${colors.red}[BACKEND ERROR]${colors.reset} ${data}`);
});

// Start frontend
log('green', '🎨 Starting frontend server (port 5173)...');
const frontend = spawn('npm', ['run', 'dev'], {
  cwd: __dirname,
  stdio: ['ignore', 'pipe', 'pipe'],
});

frontend.stdout.on('data', (data) => {
  process.stdout.write(`${colors.green}[FRONTEND]${colors.reset} ${data}`);
});

frontend.stderr.on('data', (data) => {
  process.stderr.write(`${colors.red}[FRONTEND ERROR]${colors.reset} ${data}`);
});

// Handle exit
function cleanup() {
  log('yellow', '\n🛑 Shutting down servers...');
  backend.kill();
  frontend.kill();
  process.exit();
}

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);

// Log startup info
setTimeout(() => {
  log('green', '\n✅ Both servers are starting!');
  log('blue', '📊 Backend:  http://localhost:8888');
  log('blue', '📊 Frontend: http://localhost:5173');
  log('yellow', '\nPress Ctrl+C to stop both servers\n');
}, 2000);

// Wait for processes
backend.on('exit', (code) => {
  if (code !== null && code !== 0) {
    log('red', `Backend exited with code ${code}`);
  }
});

frontend.on('exit', (code) => {
  if (code !== null && code !== 0) {
    log('red', `Frontend exited with code ${code}`);
  }
});

