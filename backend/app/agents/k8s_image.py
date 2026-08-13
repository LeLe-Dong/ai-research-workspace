"""Self-service mirror provisioning for the experiment engine.

The cluster nodes can only pull images through the internal Harbor registry
(`registry.adms.io:31542`, project `library`). Public docker.io is NOT
reachable from the nodes. When the LLM-designed experiment needs an image
that isn't mirrored in Harbor yet, the experiment would otherwise die with
ImagePullBackOff.

This module closes that gap: the *control plane* (this box) can reach
public registries (via a docker mirror), so we pull the missing image
locally, re-tag it to the Harbor address, and push it. The cluster can then
pull it from Harbor like any other image.

Flow for each image the experiment references:
  has_image(harbor) -> (no-op) if already present
  else ensure_mirrored(image): docker pull <upstream> -> tag registry.adms.io:31542/library/<img> -> docker push

Authentication: Harbor credentials come from the cluster's
`kube-system/adms-harbor-secret` dockerconfigjson (admin account), so no
password is stored in config files.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os

logger = logging.getLogger(__name__)

HARBOR_HOST = "registry.adms.io:31542"
HARBOR_PROJECT = "library"
HARBOR_IP = "10.6.68.70"  # resolvable host for Harbor (hosts entry added)
HARBOR_BASE = f"https://{HARBOR_HOST}"
DOCKER_REGISTRY_DIR = f"/etc/docker/certs.d/{HARBOR_HOST}"


async def _kubectl_async_safe(args: list[str]) -> tuple[int, str, str]:
    """Run kubectl asynchronously (mirrors app.agents.k8s._kubectl_async)."""
    import subprocess
    proc = await asyncio.create_subprocess_exec(
        "kubectl", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=20)
        return proc.returncode, out_b.decode(), err_b.decode()
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -2, "", "kubectl timed out"


async def _harbor_credentials(kc_path: str) -> tuple[str, str] | None:
    """Return (username, password) from the cluster's harbor secret."""
    rc, out, err = await _kubectl_async_safe(
        ["--kubeconfig", kc_path, "get", "secret", "adms-harbor-secret",
         "-n", "kube-system", "-o", "json"]
    )
    if rc != 0:
        logger.warning("could not read adms-harbor-secret: %s", err[:120])
        return None
    try:
        d = json.loads(out)
        dcfg = json.loads(base64.b64decode(d["data"][".dockerconfigjson"]))
        for _url, info in dcfg.get("auths", {}).items():
            auth = base64.b64decode(info["auth"]).decode()
            if ":" in auth:
                user, pwd = auth.split(":", 1)
                return user, pwd
    except Exception as e:
        logger.warning("harbor secret parse failed: %s", e)
    return None


async def _harbor_has_image(kc_path: str, image_tag: str) -> bool:
    """Check whether `<image>:<tag>` already exists in the Harbor project.

    image_tag is the short form, e.g. "redis:7.0.4" or "nginx:1.26.2-alpine".
    Uses the Harbor REST API (registry v2 /v2/<project>/<name>/tags/list).
    """
    if "/" in image_tag:
        repo, tag = image_tag.rsplit("/", 1)
    else:
        repo, tag = image_tag, ""
    # Harbor repo path: library/<image path> (colons removed, slashes preserved)
    # We check via docker manifest inspect for simplicity and auth reuse.
    return await _docker_manifest_exists(kc_path, f"{HARBOR_HOST}/{HARBOR_PROJECT}/{repo}:{tag}")


async def _docker_manifest_exists(kc_path: str, image: str) -> bool:
    """docker manifest inspect — non-zero exit means not present."""
    creds = await _harbor_credentials(kc_path)
    env = dict(os.environ)
    if creds:
        env["HARBOR_USER"] = creds[0]
        env["HARBOR_PASS"] = creds[1]
    # docker manifest inspect uses the daemon's configured auth
    proc = await asyncio.create_subprocess_exec(
        "docker", "manifest", "inspect", image,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
    return proc.returncode == 0


async def _run_shell(cmd: str, timeout: float = 240.0) -> tuple[int, str, str]:
    """Run a shell command in a subprocess (for docker CLI)."""
    proc = await asyncio.create_subprocess_exec(
        "/bin/bash", "-lc", cmd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode, out_b.decode(), err_b.decode()
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -2, "", f"command timed out after {timeout}s"


async def ensure_harbor_configured() -> bool:
    """Make sure docker can reach Harbor (hosts + CA + login).

    Idempotent. Returns True if ready.
    """
    import os
    # 1. hosts entry
    try:
        with open("/etc/hosts") as f:
            if f"{HARBOR_IP} {HARBOR_HOST}" not in f.read():
                with open("/etc/hosts", "a") as f2:
                    f2.write(f"\n{HARBOR_IP} {HARBOR_HOST}\n")
    except Exception:
        pass
    # 2. CA cert for docker
    if not os.path.exists(f"{DOCKER_REGISTRY_DIR}/ca.crt"):
        rc, out, err = await _run_shell(
            f"mkdir -p {DOCKER_REGISTRY_DIR} && "
            f"timeout 15 openssl s_client -connect {HARBOR_IP}:31542 -showcerts </dev/null 2>/dev/null | "
            f"openssl x509 -outform PEM > {DOCKER_REGISTRY_DIR}/ca.crt",
            timeout=40,
        )
        if rc != 0:
            logger.warning("harbor CA fetch failed")
    return os.path.exists(f"{DOCKER_REGISTRY_DIR}/ca.crt")


async def ensure_image_mirrored(kc_path: str, image: str, upstream_registry: str | None = None) -> tuple[bool, str]:
    """Ensure `image` is available in Harbor for the cluster.

    `image` is the full reference the experiment manifest uses — we normalize
    it to `registry.adms.io:31542/library/<path>:<tag>` and, if missing, pull
    from the upstream mirror and push.

    Returns (ok, message).
    """
    # Normalize: whatever the manifest says, we want the harbor short name.
    short = _to_short_name(image)
    target = f"{HARBOR_HOST}/{HARBOR_PROJECT}/{short}"
    if await _docker_manifest_exists(kc_path, target):
        return True, f"镜像已在 Harbor: {target}"

    # Pull from upstream (daocloud mirror or the docker.io default).
    upstream = upstream_registry or "docker.m.daocloud.io/library"
    src = f"{upstream}/{short}" if not upstream.endswith("/library") else f"{upstream}/{short}"
    # Handle plain short refs: prepend library
    if not image.startswith(("registry.", "docker.io", "docker.m.")):
        pass

    rc, out, err = await _run_shell(f"docker pull {src}", timeout=400)
    if rc != 0:
        # retry with the plain docker.io source
        src2 = f"docker.io/library/{short}"
        rc, out, err = await _run_shell(f"docker pull {src2}", timeout=400)
        if rc != 0:
            return False, f"无法从公网拉取 {short}: {err[:200]}"
    logger.info("pulled upstream %s", src)

    rc, out, err = await _run_shell(f"docker tag {src} {target} && docker push {target}", timeout=600)
    if rc != 0:
        return False, f"推送到 Harbor 失败: {err[:200]}"
    return True, f"已镜像到 Harbor: {target}"


def _to_short_name(image: str) -> str:
    """Reduce any image reference to `<name>:<tag>` for the Harbor library project.

    registry.adms.io:31542/library/redis:7.0.4 -> redis:7.0.4
    docker.io/library/postgres:15          -> postgres:15
    redis:7.0.4                            -> redis:7.0.4
    docker.m.daocloud.io/library/nginx:1.26.2-alpine -> nginx:1.26.2-alpine
    """
    s = image
    # strip scheme
    if "://" in s:
        s = s.split("://", 1)[1]
    # strip host
    if "/" in s:
        parts = s.split("/")
        # docker.io/library/<name>:<tag>  → last two meaningful
        while len(parts) > 1 and parts[0] in (
            "docker.io", "registry.adms.io:31542", "docker.m.daocloud.io", "registry-1.docker.io"
        ):
            parts = parts[1:]
        s = "/".join(parts)
    # The Harbor library project is flat: drop a leading `library/` if the
    # ref already carried the project name (e.g. registry.../library/redis).
    if s.startswith("library/"):
        s = s[len("library/"):]
    # ensure a tag
    if ":" not in s:
        s += ":latest"
    return s
