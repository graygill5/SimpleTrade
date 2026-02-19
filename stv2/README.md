# SimpleTrade (Web Demo)

- **Backend (Python + FastAPI)** runs the paper-trading logic and stores trades in SQLite
- **Frontend (React + Vite)** shows the dashboard and calls the backend API

You run it with **two terminals**: one for the API and one for the website.

Terminal 1:

- stv2/ppv2:
  - python -m venv .venv
  - source .venv/bin/activate
  - pip install -r requirements.txt
  - uvicorn server.main:app --reload --port 8000

Terminal 2:

- stv2/ppv2/web
  - npm install
  - npm run dev
  - open the url
