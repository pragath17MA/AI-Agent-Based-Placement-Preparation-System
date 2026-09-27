# Running & Operational Guidelines

This guide details instructions to run and deploy the upgraded **AI Interview Platform** backend and frontend applications locally or inside containers.

---

## 1. Local Environment Execution

### A. Backend Server (FastAPI)
Activate the virtual environment and start the uvicorn API worker:

```bash
cd backend
..\venv\Scripts\activate
# Set preferred environment flags
$env:PYTHONPATH="backend"
python -m uvicorn app.main:app --port 8000 --reload
```
- **Seeding**: The seeder script runs automatically on startup if the database is empty. You can trigger a manual reseed via:
  ```bash
  python seed.py
  ```

### B. Frontend Server (Next.js)
Start the Next development compilation server:

```bash
cd frontend
npm run dev
```
Open `http://localhost:3000` in the browser to access the premium dashboard.

---

## 2. Docker & Multi-Compiler Deployment
To deploy the full platform, including the Redis task broker and Postgres databases:

```bash
docker-compose up --build
```

### Docker Services
- **backend**: Spawns FastAPI server at `localhost:8000`. Installs `gcc`, `g++`, `default-jdk`, and `nodejs` for the multi-language online judge.
- **frontend**: Spawns compiled Next.js static renderer at `localhost:3000`.
- **db**: PostgreSQL database container storing profiles, problems catalog, and scorecards.
- **redis**: Redis message queue supporting async execution results caching.
- **celery_worker**: Asynchronous task daemon executing sandboxed codes.
