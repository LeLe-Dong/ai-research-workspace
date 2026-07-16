# AI Research Workspace — Production Deployment Checklist

## Pre-Deployment

### 1. Environment Variables
- [ ] `AIRW_AGENT_MODE` set to production mode (e.g., `stepfun` or `hermes-researcher`, not `mock`)
- [ ] `AIRW_STEPFUN_API_KEY` set (if using stepfun)
- [ ] `AIRW_DB_PATH` pointing to persistent storage
- [ ] `AIRW_AUTO_RESTART=0` if using external process manager (systemd/supervisor)
- [ ] `NODE_ENV=production` for frontend
- [ ] `NEXT_PUBLIC_API_BASE` pointing to backend (e.g., `https://api.example.com`)

### 2. Build Frontend
- [ ] `cd frontend && pnpm install` (or npm/yarn)
- [ ] `pnpm build` → static export in `.next/`
- [ ] Output served by nginx / CloudFront / Vercel / etc.

### 3. System Dependencies
- [ ] Python 3.11+ (3.14 recommended)
- [ ] Node 20+ (for Next.js build)
- [ ] SQLite 3.35+ (or migrate to PostgreSQL for multi-tenant)
- [ ] nginx (reverse proxy) with HTTPS
- [ ] systemd unit for backend (auto-restart on crash)

### 4. Process Management (systemd example)
- [ ] `/etc/systemd/system/airw-backend.service`:
  ```ini
  [Unit]
  Description=AIRW Backend
  After=network.target
  
  [Service]
  Type=simple
  User=airw
  WorkingDirectory=/opt/airw/backend
  EnvironmentFile=/opt/airw/.env
  ExecStart=/opt/airw/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8003
  Restart=always
  RestartSec=5
  StandardOutput=append:/var/log/airw/backend.log
  StandardError=append:/var/log/airw/backend.error.log
  
  [Install]
  WantedBy=multi-user.target
  ```
- [ ] `systemctl daemon-reload && systemctl enable --now airw-backend`
- [ ] `journalctl -u airw-backend -f` for logs

### 5. Nginx Reverse Proxy
- [ ] `/etc/nginx/sites-available/airw`:
  ```nginx
  server {
      listen 80;
      server_name example.com;
      return 301 https://$server_name$request_uri;
  }
  
  server {
      listen 443 ssl http2;
      server_name example.com;
      
      ssl_certificate /etc/letsencrypt/live/example.com/fullchain.pem;
      ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;
      
      # Frontend (Next.js static export or SSR)
      location / {
          root /opt/airw/frontend/.next/standalone;
          try_files $uri $uri/ /index.html;
      }
      
      # Backend API
      location /api/ {
          proxy_pass http://127.0.0.1:8003;
          proxy_set_header Host $host;
          proxy_set_header X-Real-IP $remote_addr;
          proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
          proxy_set_header X-Forwarded-Proto $scheme;
          
          # SSE: disable buffering
          proxy_buffering off;
          proxy_cache off;
      }
      
      # OpenAI-compatible API
      location /v1/ {
          proxy_pass http://127.0.0.1:8003;
          proxy_set_header Host $host;
      }
  }
  ```
- [ ] `certbot --nginx -d example.com` for Let's Encrypt
- [ ] `nginx -t && systemctl reload nginx`

## Post-Deployment Verification

### 6. Smoke Tests
- [ ] `curl https://example.com/health` → `{"status":"ok",...}`
- [ ] `curl https://example.com/api/v1/dashboard` → 200
- [ ] `curl https://example.com/v1/models` → 200, 3 agents
- [ ] Browser visit `https://example.com/dashboard` → loads
- [ ] Create a test research → completes within 5 min
- [ ] Reviewer shows 6-dimensional score
- [ ] `/api/v1/admin/stuck-researches` returns 0
- [ ] `/api/v1/admin/agent-mode` shows correct mode

### 7. Operational Readiness
- [ ] **Backups**: `backend/scripts/backup.sh` in cron (daily, 7-day retention)
- [ ] **Monitoring**: Alert on /health 5xx or research stuck > 10 min
- [ ] **Log rotation**: `/var/log/airw/*.log` → logrotate
- [ ] **Resource limits**: 1GB RAM per process, 2 CPU cores
- [ ] **Auto-recovery**: `/admin/reset-stuck-researches` in incident runbook
- [ ] **DB WAL**: Enable SQLite WAL mode for concurrent reads

### 8. Security Hardening
- [ ] **CORS**: Replace `["*"]` with actual frontend domain
- [ ] **Auth**: Add OAuth/SSO before exposing publicly (currently single-tenant no-auth)
- [ ] **Rate limiting**: nginx `limit_req` on /api/ and /v1/
- [ ] **HTTPS only**: HSTS header, no HTTP fallback in production
- [ ] **DB file permissions**: 600, owned by airw user
- [ ] **Secret management**: API keys in vault, not .env

### 9. Migration Path: SQLite → PostgreSQL
When scaling beyond single-tenant:
- [ ] Replace `sqlite+aiosqlite` with `postgresql+asyncpg` in `app/db/database.py`
- [ ] Update `app/db/models.py` for PG-specific types (JSONB, ARRAY)
- [ ] Add Alembic for schema migrations
- [ ] Add `pgvector` extension for KB embeddings (Phase 2)
- [ ] Connection pool tuning (pool_size=20, max_overflow=10)

## Rollback Plan

### 10. Quick Rollback
```bash
# Revert code
cd /opt/airw && git checkout v0.1.0  # or previous tag

# Restart backend
sudo systemctl restart airw-backend

# Rollback DB (if schema change)
cp /var/backups/airw/airw_$(date +%Y%m%d)_before.db /opt/airw/backend/storage/airw.db
sudo systemctl restart airw-backend
```

### 11. Post-Rollback Verification
- [ ] `/health` returns 200
- [ ] Dashboard loads
- [ ] No research stuck in running
- [ ] Re-run previous smoke tests

## Disaster Recovery

### 12. DB Recovery
- [ ] Daily backups at `/var/backups/airw/` (7-day retention)
- [ ] Monthly archive to S3/offsite
- [ ] Restore command: `cp backups/airw_20260714.db backend/storage/airw.db && systemctl restart airw-backend`
- [ ] Verify: `sqlite3 airw.db "SELECT COUNT(*) FROM researches"` matches backup time

### 13. LLM API Quota Monitoring
- [ ] Track `stepfun` token usage per day
- [ ] Alert at 80% of monthly quota
- [ ] Graceful degradation: fall back to mock mode if quota exceeded
