# K8s RBAC for the AI Research Workspace validator

This directory holds RBAC yaml for the cluster-side counterpart of the
backend's `validate_with_k8s` flow. The backend cannot apply these
manifests itself — per ADR-002 / Q3=3a, an operator (or cluster-admin)
applies them.

## What's here

- `airw-bot-role.yaml` — ServiceAccount + Role + RoleBinding for the
  `airw-bot` SA in both `airw-research` (legacy dev/scratch ns) and
  `airw-research-experiments-*` (per-research experimental ns).

## What's granted

The Role widens `airw-bot` from the pre-ADR-002 baseline (read pods
+ apply the test pod) to the full set needed by ADR-002 commit 4's
table-driven cleanup path:

| API group | Resources | Verbs |
|---|---|---|
| `""` (core) | pods, pods/log, pods/exec, services, configmaps, persistentvolumeclaims, events | get, list, watch, create, update, patch, delete |
| `apps` | deployments, statefulsets, replicasets | get, list, watch, create, update, patch, delete |

What's **deliberately** not in this Role:
- `nodes`, `namespaces`, `persistentvolumes` — cluster-scoped; the
  agent must never reach these.
- `*` (wildcard) — the role is explicit.
- CRDs of any kind — even if the validator allows custom resources
  in the future, the operator must explicitly opt in.

## Apply

```bash
# from the repo root
kubectl apply -f infra/k8s/rbac/airw-bot-role.yaml
```

Verify the binding took:

```bash
kubectl auth can-i list pods -n airw-research --as=system:serviceaccount:airw-research:airw-bot
# expected: yes
kubectl auth can-i create deployments -n airw-research-experiments-test1 --as=system:serviceaccount:airw-research:airw-bot
# expected: yes
kubectl auth can-i list nodes --as=system:serviceaccount:airw-research:airw-bot
# expected: no
```

## When to rotate

- The Role is wide enough for ADR-002 commit 4 + the existing
  validate_with_k8s path. **Do not extend it casually** — every
  additional verb is one more thing a hallucinating LLM could
  weaponize if the backend validator ever has a bug.
- If a new resource kind is needed (e.g. `batch/jobs` for one-off
  test workloads), update `ALLOWED_KINDS` in
  `app/agents/k8s_manifest.py` AND the RBAC yaml in the same commit
  so the two stay in lockstep.

## When NOT to apply

If you're running in a multi-tenant cluster and another team owns
`airw-research`, **talk to them first**. The Role grants
namespace-scoped writes; an `airw-bot` SA compromised by a
bug-or-bug-like condition could affect shared workloads in that ns.
