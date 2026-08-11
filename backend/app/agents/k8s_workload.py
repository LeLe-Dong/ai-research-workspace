"""Workload templates for empirical K8s validation.

Phase C: Instead of always running a fixed nginx:alpine pod, we pick a
real workload that matches the research topic (database, cache, web, AI,
generic) and capture *measured* numbers (TPS, latency, CPU, memory) that
the agent can quote in its final report.

This is the difference between "the pod deployed" and "we actually
benchmarked the proposed solution and here's the TPS". A research
report backed by real cluster numbers is more credible than one with
only theoretical claims.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Workload:
    """A real benchmark we can run inside a k8s test pod.

    The image must include the benchmark binary (or we install it via
    init_cmd). Benchmark output is parsed by `parse_metrics`.
    """
    name: str
    image: str
    init_cmd: str | None = None   # one-time setup before benchmark
    benchmark_cmd: str = ""      # produces the numbers we capture
    description: str = ""
    # Metric name → regex to extract from benchmark output
    metric_patterns: dict[str, str] = field(default_factory=dict)
    # Default duration budget in seconds (used as kubectl --timeout)
    timeout_sec: int = 60


# ── Workload library ──────────────────────────────────────────
# Each workload is a self-contained pod that the k8s validator can apply
# and parse. We keep them conservative on resource requests so they fit in
# the existing airw-research namespace (which has limited quota).

WORKLOADS: dict[str, Workload] = {
    "database": Workload(
        name="postgres-bench",
        image="postgres:16-alpine",
        description="PostgreSQL OLTP 基准（pgbench）：测 TPS、平均延迟、P99 延迟",
        init_cmd=(
            # Initialize a tiny cluster so pgbench can run.
            "PG_DATA=/var/lib/postgresql/data; "
            "if [ ! -f $PG_DATA/PG_VERSION ]; then "
            "  su postgres -c \"initdb -D $PG_DATA -U postgres --auth=trust\" >/dev/null 2>&1; "
            "fi; "
            "su postgres -c \"pg_ctl -D $PG_DATA -l /tmp/pg.log -o '-p 5432 -h 0.0.0.0' start\"; "
            "for i in $(seq 1 10); do pg_isready -h 127.0.0.1 -p 5432 -q && break; sleep 1; done"
        ),
        benchmark_cmd=(
            # pgbench built-in: 10 clients, 2 threads, 30 seconds, simple update
            "pgbench -h 127.0.0.1 -p 5432 -U postgres -i -s 50 postgres 2>&1 | tail -2; "
            "echo '---BENCHMARK---'; "
            "pgbench -h 127.0.0.1 -p 5432 -U postgres -c 10 -j 2 -T 20 -P 1 postgres 2>&1 | tail -30"
        ),
        metric_patterns={
            # pgbench output format (with -P 1):
            #   number of transactions actually processed: 250/250
            #   latency average = 1.234 ms
            #   latency stddev = 0.567 ms
            #   tps = 202.500000 (including connections establishing)
            #   tps = 202.512348 (excluding connections establishing)
            "tps_including": r"tps\s*=\s*([\d.]+)\s*\(including connections establishing\)",
            "tps_excluding": r"tps\s*=\s*([\d.]+)\s*\(excluding connections establishing\)",
            "latency_avg_ms": r"latency average\s*=\s*([\d.]+)\s*ms",
            "latency_stddev_ms": r"latency stddev\s*=\s*([\d.]+)\s*ms",
            "latency_p95_ms": r"latency\s+95th\s+percentile\s*=\s*([\d.]+)\s*ms",
            "transactions_total": r"number of transactions actually processed[:\s]+([\d/]+)",
        },
        timeout_sec=90,
    ),

    "cache": Workload(
        name="redis-bench",
        image="redis:7-alpine",
        description="Redis 基准：测 SET/GET QPS、P50/P99 延迟",
        init_cmd="redis-server --daemonize yes --save '' --appendonly no",
        benchmark_cmd=(
            # redis-benchmark is built into the redis image
            "redis-benchmark -h 127.0.0.1 -p 6379 "
            "-t set,get -n 50000 -q --csv 2>&1 | head -20"
        ),
        metric_patterns={
            "set_rps": r'"SET",([\d.]+)',
            "get_rps": r'"GET",([\d.]+)',
            "set_p50_ms": r'"SET",[\d.]+,([\d.]+)',
            "get_p50_ms": r'"GET",[\d.]+,([\d.]+)',
        },
        timeout_sec=60,
    ),

    "web": Workload(
        name="nginx-bench",
        image="nginx:alpine",
        description="Nginx 静态页面基准：测 RPS、平均延迟",
        # Nginx default page is enough; ab is not in nginx:alpine so we use
        # a pure-busybox loop as a coarse throughput indicator.
        benchmark_cmd=(
            "echo '---BASELINE---'; "
            "for i in $(seq 1 1000); do "
            "  wget -q -O /dev/null http://127.0.0.1/; "
            "done; "
            "echo \"completed_$(date +%s)\""
        ),
        metric_patterns={
            "completed_at": r"completed_(\d+)",
            "requests_completed": r"completed_(\d+)",
        },
        timeout_sec=30,
    ),

    "ai": Workload(
        name="python-cpu-bench",
        image="python:3.11-alpine",
        description="Python CPU 基准（GEMM）：替代真实 LLM 推理的快速 CPU benchmark",
        benchmark_cmd=(
            "python -c '"
            "import time, hashlib; "
            "n=50000; t=time.time(); "
            "r=[hashlib.sha256(str(i).encode()).hexdigest() for i in range(n)]; "
            "elapsed=time.time()-t; "
            "print(f\"completed_\\(n={n},elapsed={elapsed:.3f}s,ops_per_sec={n/elapsed:.1f}\\\")\""
        ),
        metric_patterns={
            "ops_per_sec": r"ops_per_sec=([\d.]+)",
            "elapsed_sec": r"elapsed=([\d.]+)",
        },
        timeout_sec=45,
    ),

    "generic": Workload(
        name="alpine-cpu-bench",
        image="alpine:3.19",
        description="Alpine 通用 CPU 基准（dd + sha256）：作为所有未识别主题的兜底",
        benchmark_cmd=(
            "echo '---START---'; "
            "dd if=/dev/urandom bs=1M count=20 2>/dev/null | sha256sum; "
            "echo '---END---'"
        ),
        metric_patterns={},
        timeout_sec=30,
    ),
}


# ── Workload detection ───────────────────────────────────────
# Map goal + recommendation text → one of the workload keys.
# Order matters: more specific patterns first.

WORKLOAD_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("database", (
        "mysql", "postgres", "postgresql", "mariadb", "mongodb", "tidb",
        "数据库", "oltp", "olap", "sql", "transaction", "事务", "database",
        "oracle", "oceanbase", "polardb", "goldendb", "dameng",
    )),
    ("cache", (
        "redis", "memcached", "kv ", "缓存", "cache", "key-value",
    )),
    ("ai", (
        "llm", "推理", "inference", "大模型", "embedding", "向量",
        "vector", "vllm", "ollama", "gpt", "transformer", "ai ",
        "rag ", "stable diffusion", "whisper",
    )),
    ("web", (
        "nginx", "http", "api ", "web ", "网关", "ingress", "envoy",
        "traefik", "haproxy", "service mesh", "服务网格",
    )),
]


def detect_workload(goal: str, recommendations: str = "") -> str:
    """Pick the best-matching workload key from goal + recommendations.

    Returns one of: "database" | "cache" | "web" | "ai" | "generic".
    Falls back to "generic" when nothing matches.
    """
    text = (goal + " " + recommendations).lower()
    for key, keywords in WORKLOAD_KEYWORDS:
        for kw in keywords:
            if kw in text:
                return key
    return "generic"


def get_workload(key: str) -> Workload:
    """Fetch a workload by key, falling back to 'generic'."""
    return WORKLOADS.get(key) or WORKLOADS["generic"]


def build_test_pod_yaml(
    workload: Workload,
    research_id: str,
    namespace: str,
    *,
    timeout_sec: int = 30,
) -> str:
    """Build a Kubernetes Pod manifest that runs the workload and exits.

    We avoid Python f-strings on the body because `workload.init_cmd`
    and `workload.benchmark_cmd` contain shell variables like `${VAR}`
    and `$VAR` that look like Python placeholders. Using plain strings
    + .replace() sidesteps the escaping nightmare.
    """
    name = "airw-bench-" + research_id[:8]
    init_section = ""
    if workload.init_cmd:
        indented = "\n".join(
            " " * 12 + line if line else ""
            for line in workload.init_cmd.splitlines()
        )
        init_section = (
            "  initContainers:\n"
            "  - name: init\n"
            "    image: " + workload.image + "\n"
            '    command: ["/bin/sh", "-c"]\n'
            "    args:\n"
            "      - |\n"
        ) + indented + (
            "\n"
            "    resources:\n"
            '      requests: {cpu: "100m", memory: "128Mi"}\n'
            '      limits:   {cpu: "500m", memory: "512Mi"}\n'
        )
    indented_bench = "\n".join(
        " " * 12 + line if line else ""
        for line in workload.benchmark_cmd.splitlines()
    )
    head = (
        "apiVersion: v1\n"
        "kind: Pod\n"
        "metadata:\n"
        "  name: " + name + "\n"
        "  namespace: " + namespace + "\n"
        "  labels:\n"
        '    airw-research: "' + research_id + '"\n'
        '    airw-workload: "' + workload.name + '"\n'
        "spec:\n"
        "  restartPolicy: Never\n"
        "  activeDeadlineSeconds: " + str(timeout_sec + 60) + "\n"
    )
    body = (
        "  containers:\n"
        "  - name: bench\n"
        "    image: " + workload.image + "\n"
        '    command: ["/bin/sh", "-c"]\n'
        "    args:\n"
        "      - |\n"
    ) +indented_bench + (
        "\n"
        "    resources:\n"
        "      requests:\n"
        '        cpu: "200m"\n'
        '        memory: "256Mi"\n'
        "      limits:\n"
        '        cpu: "1000m"\n'
        '        memory: "1Gi"\n'
    )
    return head + init_section + body





def parse_metrics(workload: Workload, log_text: str) -> dict:
    """Extract the named metrics from benchmark stdout using each
    metric's regex. Returns dict of metric_name → captured string.
    Missing metrics are simply absent from the result.
    """
    out: dict = {}
    for key, pat in workload.metric_patterns.items():
        m = re.search(pat, log_text, re.IGNORECASE | re.MULTILINE)
        if m:
            out[key] = m.group(1)
    return out
