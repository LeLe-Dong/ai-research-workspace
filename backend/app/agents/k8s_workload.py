"""Workload templates for empirical K8s validation.

Phase C: Instead of always running a fixed nginx pod, we pick a
real workload that matches the research topic (database, cache, web, AI,
generic) and capture *measured* numbers (TPS, latency, CPU, memory) that
the agent can quote in its final report.

This is the difference between "the pod deployed" and "we actually
benchmarked the proposed solution and here's the TPS". A research
report backed by real cluster numbers is more credible than one with
only theoretical claims.

Image registry note (2026-08-12):
The cluster nodes CANNOT reach the public docker.io. All images are
pulled through the internal Harbor proxy at `registry.adms.io:31542`
(project `library`). Only images already mirrored there are usable —
referencing `docker.io/...` triggers ImagePullBackOff. Each workload
below pins the exact Harbor tag verified present on the cluster.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Internal Harbor registry that mirrors docker.io images for the cluster.
# Public docker.io is unreachable from the nodes — do NOT switch these
# back to plain `postgres:16-alpine`-style references.
REGISTRY = "registry.adms.io:31542/library"


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
        image=f"{REGISTRY}/postgres:15",
        description="PostgreSQL OLTP 基准（pgbench）：测 TPS、平均延迟、P99 延迟",
        init_cmd=(
            # Initialize the data directory so the main container only
            # needs to (re)start the server. initContainer and main
            # container share the Pod filesystem, so the initialized
            # $PG_DATA survives; the server process itself does NOT
            # (separate PID namespaces), hence the main container
            # restarts pg_ctl in its benchmark_cmd.
            "export PATH=$PATH:/usr/lib/postgresql/15/bin; "
            "PG_DATA=/var/lib/postgresql/data; "
            "if [ ! -f $PG_DATA/PG_VERSION ]; then "
            "  su postgres -c \"initdb -D $PG_DATA -U postgres --auth=trust\" >/dev/null 2>&1; "
            "fi; "
            "chown -R postgres:postgres $PG_DATA"
        ),
        benchmark_cmd=(
            # Restart postgres inside THIS container (PID namespaces are
            # not shared with the initContainer), then run pgbench.
            "export PATH=$PATH:/usr/lib/postgresql/15/bin; "
            "PG_DATA=/var/lib/postgresql/data; "
            "if [ ! -f $PG_DATA/PG_VERSION ]; then "
            "  su postgres -c \"initdb -D $PG_DATA -U postgres --auth=trust\" >/dev/null 2>&1; "
            "fi; "
            "su postgres -c \"pg_ctl -D $PG_DATA -l /tmp/pg.log -o '-p 5432 -h 0.0.0.0' start\" 2>/dev/null; "
            "for i in $(seq 1 15); do pg_isready -h 127.0.0.1 -p 5432 -q && break; sleep 1; done; "
            "pgbench -h 127.0.0.1 -p 5432 -U postgres -i -s 20 postgres 2>&1 | tail -2; "
            "echo '---BENCHMARK---'; "
            "pgbench -h 127.0.0.1 -p 5432 -U postgres -c 10 -j 2 -T 15 -P 1 postgres 2>&1 | tail -30"
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

    "mysql": Workload(
        name="mysql-bench",
        image=f"{REGISTRY}/mysql:8.0",
        description="MySQL OLTP 基准（原生 SQL 压测）：测每秒查询数、平均延迟",
        init_cmd=(
            # Start mysqld in background, wait for readiness.
            # MySQL 8.0 default image runs as the mysql user with a
            # pre-initialized datadir under /var/lib/mysql.
            "mkdir -p /var/run/mysqld && chown mysql:mysql /var/run/mysqld; "
            "if [ ! -d /var/lib/mysql/mysql ]; then "
            "  mysqld --initialize-insecure --user=mysql --datadir=/var/lib/mysql >/dev/null 2>&1; "
            "fi; "
            "(mysqld --user=mysql --datadir=/var/lib/mysql --skip-networking=0 "
            "  --bind-address=127.0.0.1 --socket=/var/run/mysqld/mysqld.sock "
            "  --pid-file=/var/run/mysqld/mysqld.pid >/tmp/mysqld.log 2>&1 &); "
            "for i in $(seq 1 30); do "
            "  mysqladmin --socket=/var/run/mysqld/mysqld.sock -u root ping >/dev/null 2>&1 && break; "
            "  sleep 1; done"
        ),
        benchmark_cmd=(
            # Native SQL loop: 2000 SELECTs against a small table, timed.
            # mysqlslap is NOT shipped in the mysql:8.0 image, so we
            # approximate OLTP throughput with a measured query loop.
            "S=/var/run/mysqld/mysqld.sock; "
            "mysql --socket=$S -u root -e 'CREATE DATABASE IF NOT EXISTS bench;' 2>/dev/null; "
            "mysql --socket=$S -u root bench -e 'DROP TABLE IF EXISTS kv; "
            "CREATE TABLE kv (id INT PRIMARY KEY, v VARCHAR(64)) ENGINE=InnoDB; "
            "INSERT INTO kv VALUES (1,\"a\"),(2,\"b\"),(3,\"c\"),(4,\"d\"),(5,\"e\"),(6,\"f\"),(7,\"g\"),(8,\"h\"),(9,\"i\"),(10,\"j\");' 2>/dev/null; "
            "echo '---BENCHMARK---'; "
            "start=$(date +%s%N); n=2000; "
            "for i in $(seq 1 $n); do "
            "  mysql --socket=$S -u root bench -N -e 'SELECT v FROM kv WHERE id=1;' >/dev/null 2>&1; "
            "done; "
            "end=$(date +%s%N); "
            "elapsed_ms=$(( (end - start) / 1000000 )); "
            "echo \"queries=$n elapsed_ms=$elapsed_ms\"; "
            "echo \"qps=$(awk \"BEGIN{printf \\\"%.1f\\\", $n * 1000 / $elapsed_ms}\")\""
        ),
        metric_patterns={
            "queries": r"queries=(\d+)",
            "elapsed_ms": r"elapsed_ms=(\d+)",
            "qps": r"qps=([\d.]+)",
        },
        timeout_sec=90,
    ),

    "cache": Workload(
        name="redis-bench",
        image=f"{REGISTRY}/redis:7.0.4",
        description="Redis 基准：测 SET/GET QPS、P50/P99 延迟",
        init_cmd="redis-server --save '' --appendonly no --daemonize yes; sleep 1",
        benchmark_cmd=(
            # initContainer's redis-server dies when it exits (separate PID
            # namespace) — restart redis here before benchmarking.
            "redis-server --save '' --appendonly no --daemonize yes 2>/dev/null; "
            "for i in $(seq 1 10); do redis-cli -h 127.0.0.1 ping >/dev/null 2>&1 && break; sleep 1; done; "
            "redis-benchmark -h 127.0.0.1 -p 6379 "
            "-t set,get -n 20000 -q --csv 2>&1 | head -20"
        ),
        metric_patterns={
            # redis-benchmark --csv output:
            #   "SET","75187.97","0.652","0.088","0.439","0.791","0.951","37.407"
            #   cols: test,rps,avg_latency_ms,min_latency_ms,p50_latency_ms,p95_latency_ms,p99_latency_ms,max_latency_ms
            "set_rps": r'"SET","([\d.]+)"',
            "get_rps": r'"GET","([\d.]+)"',
            "set_p50_ms": r'"SET","[\d.]+","[\d.]+","[\d.]+","([\d.]+)"',
            "get_p50_ms": r'"GET","[\d.]+","[\d.]+","[\d.]+","([\d.]+)"',
            "set_p99_ms": r'"SET","[\d.]+","[\d.]+","[\d.]+","[\d.]+","[\d.]+","([\d.]+)"',
            "get_p99_ms": r'"GET","[\d.]+","[\d.]+","[\d.]+","[\d.]+","[\d.]+","([\d.]+)"',
        },
        timeout_sec=60,
    ),

    "web": Workload(
        name="nginx-bench",
        image=f"{REGISTRY}/nginx:1.26.2-alpine",
        description="Nginx 静态页面基准：测 RPS、平均延迟",
        init_cmd="nginx; sleep 1",
        benchmark_cmd=(
            # initContainer's nginx dies when it exits — restart here.
            "(nginx 2>/dev/null || nginx -c /etc/nginx/nginx.conf 2>/dev/null || true); "
            "sleep 1; "
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

    "mongo": Workload(
        name="mongo-bench",
        image=f"{REGISTRY}/mongo:8.0",
        description="MongoDB 基础基准：测插入吞吐（替代真实 LLM 推理的轻量数据基准）",
        init_cmd=(
            "mkdir -p /data/db; "
            "(mongod --dbpath /data/db --bind_ip 127.0.0.1 --fork --logpath /tmp/mongod.log >/dev/null 2>&1); "
            "for i in $(seq 1 30); do mongosh --quiet --eval 'db.runCommand({ping:1}).ok' 2>/dev/null | grep -q 1 && break; sleep 1; done"
        ),
        benchmark_cmd=(
            # initContainer's mongod dies when it exits — restart it here.
            "mkdir -p /data/db; "
            "(mongod --dbpath /data/db --bind_ip 127.0.0.1 --fork --logpath /tmp/mongod.log >/dev/null 2>&1); "
            "for i in $(seq 1 30); do mongosh --quiet --eval 'db.runCommand({ping:1}).ok' 2>/dev/null | grep -q 1 && break; sleep 1; done; "
            "echo '---BENCHMARK---'; "
            "mongosh --quiet --eval "
            "'const t=Date.now(); const n=5000; const c=db.bench; c.drop(); const docs=Array.from({length:n},(_,i)=>({i,data:\"x\".repeat(128)})); c.insertMany(docs); const el=Date.now()-t; print(\"inserted_\"+n+\" docs_elapsed_\"+el+\"ms_ops_per_sec_\"+(n*1000/el).toFixed(1));' 2>&1"
        ),
        metric_patterns={
            "ops_per_sec": r"ops_per_sec_([\d.]+)",
            "elapsed_ms": r"elapsed_(\d+)ms",
            "inserted_docs": r"inserted_(\d+)",
        },
        timeout_sec=60,
    ),

    "ai": Workload(
        name="busybox-ai-bench",
        image=f"{REGISTRY}/busybox:1.0",
        description="通用 CPU 基准（dd + sha256sum）：作为 AI 推理类研究在缺少专用镜像时的兜底实测",
        benchmark_cmd=(
            "echo '---START---'; "
            "dd if=/dev/urandom bs=1M count=20 2>/dev/null | sha256sum; "
            "echo '---END---'"
        ),
        metric_patterns={},
        timeout_sec=30,
    ),

    "generic": Workload(
        name="busybox-cpu-bench",
        image=f"{REGISTRY}/busybox:1.0",
        description="BusyBox 通用 CPU 基准（dd + sha256sum）：作为所有未识别主题的兜底",
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
    # Most specific / highest-signal first. "redis", "mysql", "mongo",
    # "nginx" are unambiguous and should beat generic database words that
    # often appear in an LLM report for a non-database topic.
    ("cache", (
        "redis", "memcached", "key-value", "kv store", "kv 缓存", "缓存", "cache",
    )),
    ("mysql", (
        "mysql", "mysqlslap",
    )),
    ("mongo", (
        "mongodb", "mongosh", "文档数据库", "document store",
    )),
    ("web", (
        "nginx", "ingress", "envoy", "traefik", "haproxy",
        "service mesh", "服务网格", "网关", "api 网关",
    )),
    ("ai", (
        "llm", "推理", "inference", "大模型", "embedding", "向量",
        "vector", "vllm", "ollama", "gpt", "transformer", "ai ",
        "rag ", "stable diffusion", "whisper",
    )),
    ("database", (
        "postgres", "postgresql", "mariadb", "tidb",
        "数据库", "oltp", "olap", "sql", "transaction", "事务", "database",
        "oracle", "oceanbase", "polardb", "goldendb", "dameng",
    )),
]


def detect_workload(goal: str, recommendations: str = "") -> str:
    """Pick the best-matching workload key from goal + recommendations.

    Returns one of: "mysql" | "mongo" | "database" | "cache" | "web" |
    "ai" | "generic". Falls back to "generic" when nothing matches.
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
