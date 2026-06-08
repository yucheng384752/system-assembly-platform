# Form System - Client Deploy Package

| Field   | Value |
|---------|-------|
| Recipe  | `gui-selected-form-system` |
| Built   | 2026-06-08 15:12 |
| DB      | postgresql |
| Kits    | platform-core-kit, tenant-auth-kit, station-data-link-kit, upload-validation-kit, import-pipeline-kit, query-traceability-kit, analytics-kit, station-admin-kit, audit-edit-kit, logs-ops-kit, mod-subscription-kit |

## Package contents

```
client-deploy-gui-selected-form-system/
|-- system/              <- Assembled system (backend + pre-built frontend + scripts)
|-- docker/              <- Dockerfiles + nginx config (Docker mode)
|   |-- backend.Dockerfile
|   |-- frontend.Dockerfile
|   +-- nginx.conf
|-- docker-compose.yml  <- Docker Compose (one-command deploy)
|-- .env.docker         <- Environment template for Docker
|-- nginx.conf          <- nginx config for direct nginx setup (no Docker)
|-- deploy.sh           <- Traditional deploy script (Linux / macOS)
|-- recipe.json         <- Assembly recipe
```

## Deployment (Ubuntu 22.04 / macOS)

### 1. Extract ZIP

```bash
unzip client-deploy-gui-selected-form-system.zip
cd client-deploy-gui-selected-form-system
```

### 2. Install

#### Option A ??Web Install Wizard (recommended)

Interactive browser-based wizard. No extra dependencies ??only Python 3 required.

```bash
python3 install-wizard.py
```

Opens `http://localhost:9981/` automatically. Guides you through database, manager account, security keys, and runs the install pipeline with live progress.

Windows:

```powershell
python install-wizard.py
```

#### Option B ??CLI Wizard (SSH / headless servers)

Step-by-step text prompts for database, manager account, and secret key.

```bash
bash deploy.sh --wizard
```

To start the backend in the background after install:

```bash
bash deploy.sh --wizard --background
```

#### Option C ??Manual config (advanced)

```bash
cp system/.env.example system/.env
nano system/.env
```

Required fields:

```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/form_system
SECRET_KEY=<random-64-char-string>
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
BOOTSTRAP_MANAGER_ENABLED=true
BOOTSTRAP_MANAGER_USERNAME=manager
BOOTSTRAP_MANAGER_PASSWORD=<min-8-chars>
```

Generate a strong SECRET_KEY:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

```bash
bash deploy.sh
```

The script automatically:

1. Configures or validates `.env` (interactive mode can create/update it)
2. Checks prerequisites (python3, pip3, node, npm)
3. Creates an isolated Python virtual environment at `system/.venv`
4. Installs backend dependencies via `pip` into the venv
5. Builds the frontend (`npm install` + `npm run build`)
6. Runs database migrations (`alembic upgrade head` or `generated_db_bootstrap.py`)

### 4. Start the backend

**Option A - foreground (for testing):**

```bash
cd system/backend
../.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Option B - background (recommended for servers):**

```bash
bash deploy.sh --background
# Log : system/logs/backend.log
# Stop: kill $(cat system/logs/backend.pid)
```

### 5. Serve the frontend

Frontend static files are **pre-built** and included at `system/frontend/dist/`. Node.js is not required on the server.

A ready-to-use nginx config is provided at `nginx.conf`. Edit the `root` path, then:

```bash
sudo cp nginx.conf /etc/nginx/sites-available/form-system
sudo ln -s /etc/nginx/sites-available/form-system /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Or configure manually to serve via nginx as a reverse proxy:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    root /path/to/client-deploy-gui-selected-form-system/system/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

> Dev only (not for production): `cd system/frontend && npm run dev`

## License management

A signed `license.lic` is included in this package.

### Get machine fingerprint (for machine-bound license)

```bash
bash deploy.sh --get-machine-id
```

Share the printed Fingerprint with your vendor. They will re-sign the license for your machine.

### Apply a new license (without reinstalling)

```bash
bash deploy.sh --update-license=/path/to/new-license.lic
```

The script copies the file to `system/license.lic` and prints restart instructions if the backend is running.

## Production security checklist

- [ ] Do NOT run as root: `sudo useradd -r -s /bin/false form-system`
- [ ] Set up nginx + TLS (Let's Encrypt / Caddy)
- [ ] `AUTH_MODE=api_key` is set (required in production)
- [ ] `SECRET_KEY` is a strong random value (not the default)
- [ ] `DATABASE_URL` uses a strong password (not the default)
- [ ] `ENVIRONMENT=production` is set (disables /docs)
- [ ] Run `pip-audit` and `npm audit`
- [ ] Rotate SECRET_KEY and API keys periodically

## Docker Compose (quick start)

No manual PostgreSQL or Python installation required.

```bash
# 1. Configure environment
cp .env.docker .env
nano .env   # set DB_PASSWORD, SECRET_KEY, ADMIN_API_KEYS

# 2. Start all services (db + backend + frontend/nginx)
docker compose up -d

# 3. Open in browser
# http://localhost        (frontend via nginx)
# http://localhost:8000   (backend API)
```

Stop services:

```bash
docker compose down          # stop (keep database volume)
docker compose down -v       # stop and delete database
docker compose logs -f       # stream live logs
```