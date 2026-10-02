# 🌾 Zarai Dastak — Backend API & Services

Core backend modular monolith powering **Zarai Dastak (زرعی دستک)**, an on-demand agricultural machinery, specialized vehicle rental, and hauling logistics platform.

---

## 🛠️ Tech Stack

- **Framework:** FastAPI (Python 3.11+)
- **Database:** Neo4j (Graph Database)
- **Cache & Message Broker:** Redis
- **Real-Time Services:** Socket.IO & WebRTC (Signaling for calls & real-time chat/tracking)
- **API Formats:** REST API & GraphQL (Graphene)

---

## 🚀 Quick Start

### 1. Environment Setup
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your database credentials:
```powershell
cp .env.example .env
```

### 3. Run the Backend Server
```powershell
.venv\Scripts\uvicorn.exe app.main:combined_app --reload --port 4000
```

- **Interactive API Documentation (Swagger):** [http://localhost:4000/docs](http://localhost:4000/docs)
- **Alternative API Docs (ReDoc):** [http://localhost:4000/redoc](http://localhost:4000/redoc)
- **Health Check:** [http://localhost:4000/health](http://localhost:4000/health)

---

## 📁 Architecture

The backend follows a Modular Monolith architecture:
- `app/core/` — Core infrastructure (database drivers, redis, security, sockets, config)
- `app/modules/` — Bounded domain contexts (auth, users, bookings, machinery/vehicles, reviews, payments, notifications)
- `app/graphql/` — GraphQL schema and resolvers
