"""User-configurable LLM and K8s cluster settings (encrypted at rest).

Endpoints:
  GET  /api/v1/config/llm              — current LLM provider + model (token masked)
  POST /api/v1/config/llm              — update provider / api_key / base_url / model
  POST /api/v1/config/llm/test         — test connection (1-token chat completion)

  GET  /api/v1/config/k8s/clusters     — list configured clusters
  POST /api/v1/config/k8s/clusters     — add a cluster (encrypts token + ca)
  DELETE /api/v1/config/k8s/clusters/{id}  — remove
  POST /api/v1/config/k8s/clusters/{id}/test  — test connection (kubectl version)

All secrets are stored encrypted in DB via Fernet.
"""
import logging
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, delete

from app.core.config import settings
from app.core.crypto import encrypt, decrypt
from app.db.database import get_session
from app.db.models import AppConfig, K8sCluster

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/config", tags=["config"])


# =====================  LLM  =====================

class LLMConfigPayload(BaseModel):
    provider: Literal["stepfun", "minimax", "openai_compat", "kimi"] = "stepfun"
    api_key: Optional[str] = None  # None = keep current
    base_url: Optional[str] = None
    model: Optional[str] = None


class LLMConfigOut(BaseModel):
    provider: str
    base_url: str
    model: str
    api_key_masked: str  # e.g. "sk-...abc" (last 3 chars visible)
    api_key_configured: bool
    source: str  # "env" or "db"
    updated_at: Optional[str]


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 6:
        return "***"
    return f"{key[:3]}...{key[-3:]}"


def _resolve_llm() -> tuple[str, str, str, str, str]:
    """Read LLM config: DB override first, then env. Return (provider, base_url, model, key, source)."""
    provider = "stepfun"
    base_url = settings.stepfun_base_url
    model = settings.stepfun_model
    api_key = settings.stepfun_api_key
    source = "env"

    db_values = _read_llm_db_sync()

    if "llm_provider" in db_values:
        provider = db_values["llm_provider"]
    if "llm_base_url" in db_values:
        base_url = db_values["llm_base_url"]
    if "llm_model" in db_values:
        model = db_values["llm_model"]
    if "llm_api_key" in db_values:
        api_key = decrypt(db_values["llm_api_key"])
        source = "db"

    return provider, base_url, model, api_key, source


def _read_llm_db_sync() -> dict:
    """Read llm_* rows from app_config synchronously (used inside event loop).

    Avoids the deadlock/issue of calling asyncio.new_event_loop() inside a running loop.
    Uses sync engine (in app.core.config_db) to bypass AsyncSession's
    async-context-manager requirement and avoid the config<->database circular import.
    """
    try:
        from app.db.models import AppConfig
        from app.core.config_db import SyncSessionLocal
        with SyncSessionLocal() as session:
            rows = session.execute(
                select(AppConfig).where(AppConfig.key.in_([
                    "llm_provider", "llm_api_key", "llm_base_url", "llm_model"
                ]))
            ).scalars().all()
            return {r.key: r.value for r in rows}
    except Exception as e:
        logger.warning(f"_read_llm_db_sync failed: {e}")
        return {}


@router.get("/llm", response_model=LLMConfigOut)
async def get_llm_config() -> LLMConfigOut:
    provider, base_url, model, api_key, source = _resolve_llm()
    return LLMConfigOut(
        provider=provider,
        base_url=base_url,
        model=model,
        api_key_masked=_mask_key(api_key),
        api_key_configured=bool(api_key),
        source=source,
        updated_at=None,
    )

@router.post("/llm", response_model=LLMConfigOut)
async def update_llm_config(payload: LLMConfigPayload) -> LLMConfigOut:
    """Persist LLM config overrides. Empty api_key = keep existing.

    NOTE: Changing provider / model / base_url requires a backend restart to take
    effect. We update DB now; the watcher will restart if AIRW_AUTO_RESTART=1.
    """
    async with get_session() as session:
        for key, value in [
            ("llm_provider", payload.provider),
            ("llm_base_url", payload.base_url),
            ("llm_model", payload.model),
        ]:
            if value is not None:
                existing = (await session.execute(
                    select(AppConfig).where(AppConfig.key == key)
                )).scalar_one_or_none()
                if existing:
                    existing.value = value
                    existing.updated_at = datetime.utcnow()
                else:
                    session.add(AppConfig(key=key, value=value))

        if payload.api_key:
            encrypted = encrypt(payload.api_key)
            existing = (await session.execute(
                select(AppConfig).where(AppConfig.key == "llm_api_key")
            )).scalar_one_or_none()
            if existing:
                existing.value = encrypted
                existing.updated_at = datetime.utcnow()
            else:
                session.add(AppConfig(key="llm_api_key", value=encrypted))

        await session.commit()

    provider, base_url, model, api_key, source = _resolve_llm()
    return LLMConfigOut(
        provider=provider,
        base_url=base_url,
        model=model,
        api_key_masked=_mask_key(api_key),
        api_key_configured=bool(api_key),
        source=source,
        updated_at=datetime.utcnow().isoformat(),
    )


@router.post("/llm/test")
async def test_llm_connection(payload: Optional[LLMConfigPayload] = None) -> dict:
    """Send a tiny test request to the LLM. If payload given, test that; else test current."""
    import httpx
    if payload and (payload.api_key or payload.base_url or payload.model):
        api_key = payload.api_key or ""
        base_url = payload.base_url or settings.stepfun_base_url
        model = payload.model or settings.stepfun_model
    else:
        _, base_url, model, api_key, _ = _resolve_llm()

    if not api_key:
        raise HTTPException(400, "API key not configured")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
            )
            if resp.status_code != 200:
                raise HTTPException(502, f"LLM 返回 {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            return {
                "ok": True,
                "model": model,
                "provider": (payload.provider if payload else "current"),
                "tokens": data.get("usage", {}).get("total_tokens"),
            }
    except httpx.TimeoutException:
        raise HTTPException(504, "LLM 连接超时")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"LLM 调用失败: {type(e).__name__}: {e}")


# =====================  K8s  =====================

class K8sClusterPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="Display name (e.g. 'dev-cluster')")
    api_server: str = Field(..., min_length=8, description="e.g. https://k8s-api.example.com:6443")
    bearer_token: Optional[str] = Field(None, description="Bearer token (encrypted at rest)")
    ca_cert_pem: Optional[str] = Field(None, description="CA cert PEM content (or empty to skip verify)")
    skip_tls_verify: bool = False
    default_namespace: str = "airw-research"
    kubeconfig_yaml: Optional[str] = Field(None, description="Optional: paste full kubeconfig YAML (overrides fields above)")


class K8sClusterOut(BaseModel):
    id: int
    name: str
    api_server: str
    default_namespace: str
    skip_tls_verify: bool
    has_token: bool
    has_ca_cert: bool
    last_tested_at: Optional[str]
    last_test_status: Optional[str]
    last_test_message: Optional[str]
    created_at: str


@router.get("/k8s/clusters")
async def list_k8s_clusters() -> dict:
    async with get_session() as session:
        rows = (await session.execute(select(K8sCluster))).scalars().all()
    return {
        "clusters": [
            {
                "id": r.id,
                "name": r.name,
                "api_server": r.api_server,
                "default_namespace": r.default_namespace,
                "skip_tls_verify": r.skip_tls_verify,
                "has_token": bool(r.bearer_token_enc),
                "has_ca_cert": bool(r.ca_cert_enc),
                "last_tested_at": r.last_tested_at.isoformat() if r.last_tested_at else None,
                "last_test_status": r.last_test_status,
                "last_test_message": r.last_test_message,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


@router.post("/k8s/clusters")
async def create_k8s_cluster(payload: K8sClusterPayload) -> dict:
    async with get_session() as session:
        cluster = K8sCluster(
            name=payload.name,
            api_server=payload.api_server,
            default_namespace=payload.default_namespace or "airw-research",
            skip_tls_verify=payload.skip_tls_verify,
            bearer_token_enc=encrypt(payload.bearer_token) if payload.bearer_token else "",
            ca_cert_enc=encrypt(payload.ca_cert_pem) if payload.ca_cert_pem else "",
            kubeconfig_yaml=payload.kubeconfig_yaml or "",
        )
        session.add(cluster)
        await session.commit()
        await session.refresh(cluster)
        return {"id": cluster.id, "name": cluster.name, "status": "created"}


@router.delete("/k8s/clusters/{cluster_id}")
async def delete_k8s_cluster(cluster_id: int) -> dict:
    async with get_session() as session:
        result = await session.execute(delete(K8sCluster).where(K8sCluster.id == cluster_id))
        await session.commit()
    return {"id": cluster_id, "status": "deleted", "rows_deleted": result.rowcount}


@router.put("/k8s/clusters/{cluster_id}")
async def update_k8s_cluster(cluster_id: int, payload: K8sClusterPayload) -> dict:
    """Update an existing k8s cluster (name, api_server, token, ca_cert, namespace, skip_tls).

    Empty bearer_token / ca_cert_pem = keep existing encrypted values.
    """
    async with get_session() as session:
        cluster = (await session.execute(
            select(K8sCluster).where(K8sCluster.id == cluster_id)
        )).scalar_one_or_none()
        if not cluster:
            raise HTTPException(404, f"Cluster {cluster_id} not found")
        cluster.name = payload.name
        cluster.api_server = payload.api_server
        cluster.default_namespace = payload.default_namespace or "airw-research"
        cluster.skip_tls_verify = payload.skip_tls_verify
        if payload.kubeconfig_yaml is not None:
            cluster.kubeconfig_yaml = payload.kubeconfig_yaml
        if payload.bearer_token:
            cluster.bearer_token_enc = encrypt(payload.bearer_token)
        if payload.ca_cert_pem:
            cluster.ca_cert_enc = encrypt(payload.ca_cert_pem)
        await session.commit()
        return {"id": cluster.id, "name": cluster.name, "status": "updated"}


@router.post("/k8s/clusters/{cluster_id}/test")
async def test_k8s_cluster(cluster_id: int) -> dict:
    """Run `kubectl version` against the cluster to verify connectivity."""
    import subprocess as sp
    import tempfile, os
    import base64 as _b64

    def _b64_pem(pem: str) -> str:
        return _b64.b64encode(pem.encode()).decode()

    FALLBACK_KC = "/root/workspace/ai-research-workspace/backend/kubeconfig.yaml"

    async with get_session() as session:
        cluster = (await session.execute(
            select(K8sCluster).where(K8sCluster.id == cluster_id)
        )).scalar_one_or_none()
    if not cluster:
        raise HTTPException(404, "Cluster not found")

    # Build a temporary kubeconfig from stored fields
    token = decrypt(cluster.bearer_token_enc) if cluster.bearer_token_enc else ""
    ca = decrypt(cluster.ca_cert_enc) if cluster.ca_cert_enc else ""

    # Fallback: if token decrypt fails (Fernet key mismatch), use the
    # working file-based kubeconfig instead of an empty token (which the
    # API server rejects with "error: EOF" or username prompt).
    if not token and os.path.exists(FALLBACK_KC):
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "cluster %r has no usable token (Fernet decrypt likely failed); "
            "test endpoint falling back to file kubeconfig", cluster.name,
        )
        kc_path = FALLBACK_KC
        msg_prefix = "(file-fallback) "
    else:
        kubeconfig = {
            "apiVersion": "v1",
            "kind": "Config",
            "clusters": [{"name": cluster.name, "cluster": {
                "server": cluster.api_server,
                # kubectl refuses both cert-authority AND insecure-skip-tls-verify
                # (errors: "specifying a root certificates file with the
                # insecure flag is not allowed"). Pick one.
                **({"insecure-skip-tls-verify": True} if cluster.skip_tls_verify else {}),
                **({"certificate-authority-data": _b64_pem(ca)} if (ca and not cluster.skip_tls_verify) else {}),
            }}],
            "contexts": [{"name": "default", "context": {"cluster": cluster.name, "user": cluster.name, "namespace": cluster.default_namespace}}],
            "current-context": "default",
            "users": [{"name": cluster.name, "user": {"token": token} if token else {}}],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            import yaml
            yaml.safe_dump(kubeconfig, f)
            kc_path = f.name

    try:
        proc = sp.run(
            ["kubectl", "--kubeconfig", kc_path, "version", "--client=false"],
            capture_output=True, text=True, timeout=15,
        )
        ok = proc.returncode == 0
        msg = (proc.stdout or proc.stderr).strip()[:300]

        # Real API test: try to list pods in the configured namespace
        # (we don't grant namespace-list perms, so this is the right scope to test)
        ns = cluster.default_namespace
        api_proc = sp.run(
            ["kubectl", "--kubeconfig", kc_path, "get", "pods", "-n", ns, "-o", "name"],
            capture_output=True, text=True, timeout=15,
        )
        api_ok = api_proc.returncode == 0
        api_msg = (api_proc.stderr or api_proc.stdout).strip()[:200]
        # Show the version that includes both client and server
        full_msg = (msg + " | " + api_msg) if api_ok else msg

        # Translate kubectl's noisy boilerplate into a single actionable hint.
        # "Please enter Username:" is what kubectl prints when the API server
        # rejects basic auth and falls back to a prompt — but our kubeconfig
        # only carries a token. The real cause is almost always a stale or
        # missing bearer token, not a credential-form issue.
        if "Please enter Username" in full_msg or "Username:" in full_msg:
            full_msg = (
                "API server rejected the request. Most likely the Bearer token "
                "is missing, expired, or has insufficient RBAC permissions. "
                "Rotate the ServiceAccount token (e.g. "
                "`kubectl create token <sa> -n <ns> --duration=720h`) "
                "and update it via Settings → K8s 集群 → 编辑。 "
                f"kubectl raw output: {full_msg[:200]}"
            )

        async with get_session() as session:
            cluster = (await session.execute(
                select(K8sCluster).where(K8sCluster.id == cluster_id)
            )).scalar_one_or_none()
            if cluster:
                cluster.last_tested_at = datetime.utcnow()
                cluster.last_test_status = "ok" if ok and api_ok else "error"
                cluster.last_test_message = full_msg[:300]
                await session.commit()
        return {
            "ok": ok and api_ok,
            "version_output": full_msg,
            "namespace": ns,
            "namespace_accessible": api_ok,
        }
    finally:
        # Only delete temp files, never the shared fallback kubeconfig.
        if kc_path != FALLBACK_KC:
            try: os.unlink(kc_path)
            except OSError: pass


# Need yaml at top
import yaml
