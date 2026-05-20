# Form System - Client Deploy Package

| Field   | Value |
|---------|-------|
| Recipe  | `gui-selected-form-system` |
| Built   | 2026-05-21 03:57 |
| DB      | postgresql |
| Kits    | platform-core-kit, tenant-auth-kit, station-data-link-kit, upload-validation-kit, import-pipeline-kit, query-traceability-kit, analytics-kit, station-admin-kit, audit-edit-kit, logs-ops-kit, mod-subscription-kit |

## Package contents

```
client-deploy-gui-selected-form-system/
??? system/      <- Assembled system (backend + frontend + scripts)
??? deploy.sh    <- Deploy script (Linux / macOS)
??? recipe.json  <- Assembly recipe
```

## Deployment steps (Ubuntu / macOS)

### 1. Configure environment

```bash
cp system/.env.example system/.env
nano system/.env
```

Required settings:

```
DATABASE_URL=postgresql+asyncpg://user:strongpassword@localhost:5432/form_db
SECRET_KEY=<random 64-character string>
ENVIRONMENT=production
```

Generate a strong SECRET_KEY:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. Run deploy

```bash
bash deploy.sh                 # install + migrate + show start commands
bash deploy.sh --background    # install + migrate + start in background
```

## Production security checklist

- [ ] Do NOT run as root: `sudo useradd -r -s /bin/false form-system`
- [ ] Set up nginx/caddy + TLS (Let's Encrypt)
- [ ] `SECRET_KEY` is a strong random value (not the default)
- [ ] `DATABASE_URL` uses a strong password (not the default)
- [ ] `ENVIRONMENT=production` is set (disables /docs)
- [ ] Run `pip-audit` and `npm audit`
- [ ] Rotate API keys and SECRET_KEY periodically