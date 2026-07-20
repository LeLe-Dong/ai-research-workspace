"use client";
import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Loader2, Server, Trash2, Check, X, Plus, Eye, EyeOff } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

interface K8sCluster {
  id: number;
  name: string;
  api_server: string;
  default_namespace: string;
  skip_tls_verify: boolean;
  has_token: boolean;
  has_ca_cert: boolean;
  last_tested_at: string | null;
  last_test_status: string | null;
  last_test_message: string | null;
  created_at: string;
}

export function K8sSettingsCard() {
  const [clusters, setClusters] = useState<K8sCluster[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState<K8sCluster | null>(null);
  const [showToken, setShowToken] = useState(false);

  // Form fields
  const [name, setName] = useState("");
  const [apiServer, setApiServer] = useState("");
  const [bearerToken, setBearerToken] = useState("");
  const [caCert, setCaCert] = useState("");
  const [namespace, setNamespace] = useState("airw-research");
  const [skipTls, setSkipTls] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get<{ clusters: K8sCluster[] }>("/api/v1/config/k8s/clusters");
      setClusters(r.clusters);
    } catch (e) {
      toast.error("加载 k8s 集群失败", { description: (e as Error).message });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const add = async () => {
    if (!name || !apiServer) {
      toast.error("请填写名称和 API Server URL");
      return;
    }
    setSaving(true);
    try {
      const payload: any = { name, api_server: apiServer, default_namespace: namespace, skip_tls_verify: skipTls };
      if (bearerToken) payload.bearer_token = bearerToken;
      if (caCert) payload.ca_cert_pem = caCert;
      await api.post("/api/v1/config/k8s/clusters", payload);
      toast.success("集群已添加");
      setShowAdd(false);
      resetForm();
      await load();
    } catch (e) {
      toast.error("添加失败", { description: (e as Error).message });
    } finally {
      setSaving(false);
    }
  };

  const test = async (id: number) => {
    setTestingId(id);
    try {
      const r = await api.post<{ ok: boolean; version_output: string; namespace_accessible: boolean }>(
        `/api/v1/config/k8s/clusters/${id}/test`
      );
      if (r.ok) {
        toast.success("连接成功", { description: r.version_output.split("\n").slice(0, 2).join(" · ") });
      } else {
        toast.error("连接失败", { description: r.version_output, duration: 8000 });
      }
      await load();
    } catch (e) {
      toast.error("测试失败", { description: (e as Error).message });
    } finally {
      setTestingId(null);
    }
  };

  const remove = async (id: number, name: string) => {
    if (!confirm(`删除集群 "${name}"？`)) return;
    try {
      await api.delete(`/api/v1/config/k8s/clusters/${id}`);
      toast.success("已删除");
      await load();
    } catch (e) {
      toast.error("删除失败", { description: (e as Error).message });
    }
  };

  const resetForm = () => {
    setName(""); setApiServer(""); setBearerToken(""); setCaCert("");
    setNamespace("airw-research"); setSkipTls(false);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Server className="h-4 w-4 text-blue-500" />
          Kubernetes 集群
          {clusters.length > 0 && (
            <Badge variant="success" className="ml-auto h-4 px-1.5 text-[10px]">
              {clusters.length} 个
            </Badge>
          )}
        </CardTitle>
        <CardDescription>
          配置 k8s 集群用于「环境验证」阶段。Token 和 CA 证书加密存储。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {/* Existing clusters list */}
        {loading ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" /> 加载中...
          </div>
        ) : clusters.length === 0 && !showAdd ? (
          <div className="rounded-md border border-dashed p-4 text-center text-xs text-muted-foreground">
            尚未配置集群。点击下方"添加集群"开始。
          </div>
        ) : (
          <div className="space-y-2">
            {clusters.map((c) => (
              <div key={c.id} className="rounded-md border p-3 space-y-1.5">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="font-medium text-sm">{c.name}</div>
                    <div className="text-[10px] text-muted-foreground font-mono break-all">
                      {c.api_server}
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-1">
                      命名空间: <span className="font-mono">{c.default_namespace}</span>
                      {" · "}Token: {c.has_token ? "✓" : "✗"} · CA: {c.has_ca_cert ? "✓" : "✗"}
                      {" · "}TLS verify: {c.skip_tls_verify ? "跳过" : "验证"}
                    </div>
                    {c.last_tested_at && (
                      <div className="text-[10px] text-muted-foreground mt-0.5">
                        上次测试: {c.last_tested_at.slice(0, 19)} · {c.last_test_status === "ok" ? "✓" : "✗ " + (c.last_test_message || "").slice(0, 60)}
                      </div>
                    )}
                  </div>
                  <div className="flex gap-1">
                    <Button
                      size="icon"
                      variant="outline"
                      className="h-7 w-7"
                      onClick={() => test(c.id)}
                      disabled={testingId === c.id}
                      title="测试连接"
                    >
                      {testingId === c.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                    </Button>
                    <Button
                      size="icon"
                      variant="outline"
                      className="h-7 w-7"
                      onClick={() => remove(c.id, c.name)}
                      title="删除"
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Add new cluster form */}
        {showAdd ? (
          <div className="space-y-3 rounded-md border bg-muted/30 p-3">
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label htmlFor="k8s-name" className="text-xs">名称</Label>
                <Input
                  id="k8s-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="dev-cluster"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="k8s-ns" className="text-xs">默认命名空间</Label>
                <Input
                  id="k8s-ns"
                  value={namespace}
                  onChange={(e) => setNamespace(e.target.value)}
                  placeholder="airw-research"
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="k8s-url" className="text-xs">API Server URL</Label>
              <Input
                id="k8s-url"
                value={apiServer}
                onChange={(e) => setApiServer(e.target.value)}
                placeholder="https://k8s-api.example.com:6443"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="k8s-token" className="text-xs">Bearer Token</Label>
              <div className="flex gap-1.5">
                <Input
                  id="k8s-token"
                  type={showToken ? "text" : "password"}
                  value={bearerToken}
                  onChange={(e) => setBearerToken(e.target.value)}
                  placeholder="eyJhbGc..."
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={() => setShowToken(!showToken)}
                >
                  {showToken ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </Button>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="k8s-ca" className="text-xs">CA 证书 (PEM, 可选)</Label>
              <textarea
                id="k8s-ca"
                value={caCert}
                onChange={(e) => setCaCert(e.target.value)}
                placeholder="-----BEGIN CERTIFICATE-----&#10;MIIC...&#10;-----END CERTIFICATE-----"
                rows={3}
                className="flex w-full rounded-md border border-input bg-background px-3 py-1.5 text-xs font-mono shadow-sm"
              />
            </div>
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={skipTls}
                onChange={(e) => setSkipTls(e.target.checked)}
                className="h-3 w-3"
              />
              <span className="text-muted-foreground">跳过 TLS 验证 (仅测试用)</span>
            </label>
            <div className="flex gap-2 pt-1">
              <Button onClick={add} disabled={saving} size="sm">
                {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : "保存"}
              </Button>
              <Button
                onClick={() => { setShowAdd(false); resetForm(); }}
                size="sm"
                variant="outline"
              >
                取消
              </Button>
            </div>
          </div>
        ) : (
          <Button
            onClick={() => setShowAdd(true)}
            size="sm"
            variant="outline"
            className="w-full"
          >
            <Plus className="mr-1 h-3 w-3" />
            添加集群
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
