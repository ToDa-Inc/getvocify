#!/bin/bash

# Start script for Vocify - runs both frontend and backend

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Starting Vocify...${NC}\n"

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  Warning: .env file not found in root directory${NC}"
fi

# Copy .env to backend if it doesn't exist there
if [ ! -f "backend/.env" ] && [ -f ".env" ]; then
    echo -e "${BLUE}📋 Copying .env to backend directory...${NC}"
    cp .env backend/.env
fi

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}🛑 Shutting down servers...${NC}"
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    exit
}

trap cleanup SIGINT SIGTERM

# Start backend
echo -e "${GREEN}🔧 Starting backend server (port 8888)...${NC}"
cd backend
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8888 > ../logs/backend.log 2>&1 &
BACKEND_PID=$!
cd ..

# Wait a bit for backend to start
sleep 2

# Start frontend
echo -e "${GREEN}🎨 Starting frontend server (port 8080)...${NC}"
npm run dev > logs/frontend.log 2>&1 &
FRONTEND_PID=$!

# Wait a bit for frontend to start
sleep 2

echo -e "\n${GREEN}✅ Both servers are starting!${NC}"
echo -e "${BLUE}📊 Backend:  http://localhost:8888${NC}"
echo -e "${BLUE}📊 Frontend: http://localhost:8080${NC}"
echo -e "${BLUE}📋 Logs:     logs/backend.log and logs/frontend.log${NC}"
echo -e "\n${YELLOW}Press Ctrl+C to stop both servers${NC}\n"

# Create logs directory if it doesn't exist
mkdir -p logs

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID

