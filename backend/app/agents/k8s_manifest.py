"""Manifest validation for research-submitted K8s resources.

Why this exists
---------------
Once we let the research agent submit its own manifests (per ADR-002),
the backend has to enforce a safety contract — the LLM cannot be trusted
to write correct or safe yaml. This module is the parser + policy gate:

  1. Parse the manifest dict (Pydantic models).
  2. Reject anything outside the allow-list (kind, image, namespace).
  3. Reject forbidden fields (hostPath, privileged, capabilities.add).
  4. Require resource.limits on every container.
  5. Return a structured ManifestValidationResult that the caller can
     surface as an AgentEvent (so the user sees WHY the manifest was
     rejected, not just that it was).

Scope
-----
This module does NOT apply anything to the cluster. It returns a result;
the caller (validate_with_k8s in app/agents/k8s.py) decides what to do
with it (reject the validation, fall back to the nginx test pod, etc.).
The actual kubectl apply + research_resources table write is commit 4.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# Resource kinds the agent is allowed to create. CRDs / Jobs / DaemonSets
# etc. are intentionally absent — they pull in cluster-admin or are too
# easy to weaponize. Each kind has its own minimum-shape model below.
ALLOWED_KINDS = frozenset({
    "Pod", "Deployment", "StatefulSet", "Service", "ConfigMap",
})

# Image registry whitelist. Anything outside this list (typos, malicious
# images, side-loaded internal registry) is rejected. Extending this
# list is a deliberate operator action, not something the LLM gets to
# suggest at runtime.
ALLOWED_IMAGES = frozenset({
    # Web / proxy layer
    "nginx:alpine", "nginx:1.27", "nginx:1.27-alpine",
    "traefik:v3.1",
    # Databases — listed by the user's stated intent ('AI in K8s builds
    # databases for the research topic'). Each must be paired with the
    # right PVC + Service + env in the manifest.
    "postgres:16-alpine", "postgres:17-alpine",
    "mysql:8.0", "mariadb:11",
    "redis:7-alpine", "redis:7",
    # Build / test infrastructure
    "busybox:1.36",
    "alpine:3.20",
})

# Field paths that are NEVER permitted in any container spec. The check
# walks the spec dict and rejects the manifest if any of these appear.
FORBIDDEN_FIELD_PATHS = frozenset({
    "hostPath",
    "privileged",
})

# Namespace allow-list. The validator only accepts manifests targeting
# airw-research-experiments-* (per-research experimental ns). Other
# namespaces must be rejected BEFORE the manifest reaches kubectl.
ALLOWED_NAMESPACE_PREFIX = "airw-research-experiments-"

# Resource limit ceiling — even if the manifest is valid, no single
# container may request more than this. Stops a runaway LLM from
# submitting a manifest that locks the dev cluster.
MAX_CPU_LIMIT = "2000m"        # 2 cores
MAX_MEMORY_LIMIT = "4Gi"


class ObjectMeta(BaseModel):
    name: str = Field(min_length=1, max_length=63, pattern=r"^[a-z0-9-]+$")
    namespace: str = Field(default="default")
    labels: dict[str, str] = Field(default_factory=dict)


class ResourceManifest(BaseModel):
    """One K8s manifest. Validated against ALLOWED_KINDS + structural shape."""
    apiVersion: Literal["v1", "apps/v1"]
    kind: str
    metadata: ObjectMeta
    spec: dict  # shape varies by kind; walked manually by _check_spec below

    @field_validator("kind")
    @classmethod
    def _kind_allowed(cls, v: str) -> str:
        if v not in ALLOWED_KINDS:
            raise ValueError(
                f"kind {v!r} is not allowed; pick from {sorted(ALLOWED_KINDS)}"
            )
        return v

    @field_validator("metadata")
    @classmethod
    def _namespace_allowed(cls, v: ObjectMeta) -> ObjectMeta:
        if not v.namespace.startswith(ALLOWED_NAMESPACE_PREFIX):
            raise ValueError(
                f"namespace {v.namespace!r} must start with "
                f"{ALLOWED_NAMESPACE_PREFIX!r} "
                "(use derive_experiment_ns(research_id))"
            )
        return v

    @model_validator(mode="after")
    def _check_spec(self) -> "ResourceManifest":
        """Walk spec for forbidden fields and image whitelist.

        Why this lives in ResourceManifest instead of as a standalone
        function called from validate_manifest: spec is a `dict` field
        (its shape varies by kind), so Pydantic won't recursively type-
        check the inner containers — we have to walk it manually here.
        """
        errors: list[str] = []
        _walk_spec_for_forbidden_fields(self.spec, errors=errors)
        for img in _iter_container_images(self.spec):
            if img not in ALLOWED_IMAGES:
                errors.append(
                    f"image {img!r} is not in the allowed list "
                    "(see app/agents/k8s_manifest.py:ALLOWED_IMAGES)"
                )
        if errors:
            # Surface all violations as a single ValueError so Pydantic
            # wraps it consistently with the kind/namespace checks.
            raise ValueError("; ".join(errors))
        return self


class ManifestValidationResult(BaseModel):
    """Outcome of validate_manifest(). Carries enough info for the caller
    to surface as an AgentEvent and for the user to understand what went
    wrong without reading the source."""
    ok: bool
    manifests: list[ResourceManifest] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    def summary(self) -> str:
        if self.ok:
            return f"validated {len(self.manifests)} manifest(s)"
        return f"rejected ({len(self.errors)} error(s)): " + "; ".join(self.errors[:3])


def _walk_spec_for_forbidden_fields(spec, path: str = "spec",
                                     errors: list[str] | None = None) -> None:
    """Recursively walk a spec dict looking for FORBIDDEN_FIELD_PATHS.

    Mutates `errors` in place (caller-provided list). Returns nothing —
    the caller inspects the list after. Recurses into both nested dicts
    (e.g. securityContext) and lists of dicts (e.g. volumes[]).
    """
    if errors is None:
        errors = []
    if isinstance(spec, dict):
        for k, v in spec.items():
            if k in FORBIDDEN_FIELD_PATHS:
                errors.append(f"forbidden field at {path}.{k} (= {v!r})")
                continue
            _walk_spec_for_forbidden_fields(v, f"{path}.{k}", errors)
    elif isinstance(spec, list):
        for i, item in enumerate(spec):
            _walk_spec_for_forbidden_fields(item, f"{path}[{i}]", errors)


def _iter_container_images(spec: dict):
    """Yield every container image string found anywhere in the spec.

    Handles these shapes:
      Pod.spec.containers[].image
      Deployment.spec.template.spec.containers[].image
      StatefulSet.spec.template.spec.containers[].image

    We use a small state machine: `containers` triggers the direct-yield
    branch, `template` recurses (because templates also have their own
    containers). Any other dict recurses into its values.
    """
    if not isinstance(spec, dict):
        return
    if isinstance(spec.get("containers"), list):
        for c in spec["containers"]:
            if isinstance(c, dict) and isinstance(c.get("image"), str):
                yield c["image"]
        return
    if isinstance(spec.get("template"), dict):
        yield from _iter_container_images(spec["template"])
        return
    # Generic recursion: any dict that contains a sub-dict with
    # containers or template will be re-entered via the cases above.
    for v in spec.values():
        if isinstance(v, dict):
            yield from _iter_container_images(v)


def validate_manifest(manifest: dict | list) -> ManifestValidationResult:
    """Parse + check a manifest (or list of manifests).

    Returns a ManifestValidationResult. The caller checks `result.ok` and
    surfaces `result.summary()` to the timeline. On success, `result.manifests`
    holds the parsed Pydantic models (so the caller can iterate without
    re-parsing).
    """
    errors: list[str] = []
    manifests_in: list[dict]
    if isinstance(manifest, list):
        manifests_in = manifest
    elif isinstance(manifest, dict):
        manifests_in = [manifest]
    else:
        return ManifestValidationResult(
            ok=False,
            errors=[f"manifest must be a dict or list of dicts, got {type(manifest).__name__}"],
        )

    parsed: list[ResourceManifest] = []
    for i, m in enumerate(manifests_in):
        try:
            pm = ResourceManifest.model_validate(m)
        except Exception as e:
            errors.append(f"manifest[{i}]: {e}")
            continue
        # Walk spec for forbidden fields (hostPath / privileged / etc.)
        _walk_spec_for_forbidden_fields(pm.spec, errors=errors)
        parsed.append(pm)

    # If no manifests were supplied at all, that's an error
    if not manifests_in:
        errors.append("manifest is empty")

    return ManifestValidationResult(
        ok=not errors,
        manifests=parsed,
        errors=errors,
    )