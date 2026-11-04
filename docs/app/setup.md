# Setup

Prerequisites, database configuration, and steps to run the backend and frontend.

---

## 1. Prerequisites

### 1.1 Homebrew (macOS)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 1.2 Python 3.10+

```bash
brew install python@3.13
python3 --version
```

### 1.3 Node.js + npm

```bash
brew install node
node --version
npm --version
```

### 1.4 MySQL

Choose one of the following:

#### Option A: Docker MySQL (recommended)

Install Docker Desktop from https://www.docker.com/products/docker-desktop/

```bash
docker --version
docker compose version
```

#### Option B: Homebrew MySQL (alternative)

```bash
brew install mysql
brew services start mysql
```

Then create the database and user:

```bash
mysql -u root
```

```sql
CREATE DATABASE stock_manager CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'stock_user'@'localhost' IDENTIFIED BY 'stock_password';
GRANT ALL PRIVILEGES ON stock_manager.* TO 'stock_user'@'localhost';
FLUSH PRIVILEGES;
```

### 1.5 Expo Go

Install from App Store / Google Play.

---

## 2. Project Setup

### 2.1 Clone

```bash
git clone <your-repo-url>
cd stock_manager
```

### 2.2 Environment Variables

Create `.env` in the project root:

```env
DATABASE_URL=mysql+pymysql://stock_user:stock_password@127.0.0.1:3306/stock_manager
API_HOST=0.0.0.0
API_PORT=8000

# AI recipe recommendations (optional, for Explore Recipes)
# AI_RECIPE_ENABLED=false
# AI_BASE_URL=https://api.deepseek.com
# AI_API_KEY=
# AI_MODEL=deepseek-chat
# AI_TIMEOUT_SECONDS=60
# AI_TEMPERATURE=0.2
```

### 2.3 Start MySQL

**Docker**:

```bash
docker compose up -d
```

**Homebrew**:

```bash
brew services start mysql
```

---

## 3. Backend (FastAPI)

### 3.1 Install Python Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3.2 Start the API Server

```bash
uvicorn stock_manager.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 3.3 Verify

```bash
curl http://localhost:8000/api/health
```

Expected: `{"status":"ok","version":"0.9.0"}`

### 3.4 API Documentation

Open http://localhost:8000/docs in your browser.

### 3.5 Rebuilding the Database After a Schema Change

The backend creates missing tables on startup (`Base.metadata.create_all`) and seeds the
default inventory categories. It does **not** alter existing tables, and the project has
no migration tool yet.

The structured category change (issue #33) replaced the free-text `items.category` /
`restock_items.category` columns with `category_id`. **Existing databases are not
upgraded. You have to drop and rebuild them. All existing stock, restock, settings,
recipe, and favorite data is lost.**

Docker MySQL — drop and recreate only the app database:

```bash
docker exec -it stock_manager_mysql mysql -u root -p \
  -e "DROP DATABASE stock_manager; CREATE DATABASE stock_manager CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

Or remove the whole Docker volume. This also resets MySQL users to the values in `docker-compose.yml`:

```bash
docker compose down -v
docker compose up -d
```

Homebrew MySQL:

```bash
mysql -u root -e "DROP DATABASE stock_manager; CREATE DATABASE stock_manager CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

Then restart the backend. It recreates all tables and seeds the default categories.
Re-import HowToCook recipes if you need them:

```bash
python scripts/import_howtocook.py /path/to/HowToCook
```

---

## 4. Frontend (Expo + React Native)

### 4.1 Install Dependencies

```bash
cd frontend
npm install --legacy-peer-deps
```

### 4.2 Configure API URL

Edit `frontend/app.json` → `expo.extra.apiBaseUrl`:

| Environment | Value |
|---|---|
| iOS Simulator | `http://localhost:8000/api` |
| Real device | `http://YOUR_MAC_IP:8000/api` |

Find your Mac IP:

```bash
ipconfig getifaddr en0
```

### 4.3 Start Expo

```bash
npx expo start -c
```

### 4.4 Open in Expo Go

- iOS Simulator: Press `i` in the terminal
- Real device: Scan the QR code

---

## 5. Daily Startup

```bash
# Terminal 1: MySQL
docker compose up -d

# Terminal 2: Backend
cd /path/to/stock_manager
source .venv/bin/activate
uvicorn stock_manager.api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 3: Frontend
cd /path/to/stock_manager/frontend
npx expo start -c
```
