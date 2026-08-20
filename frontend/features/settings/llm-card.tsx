"use client";
import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Loader2, Check, X, Sparkles, Eye, EyeOff } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

interface LLMConfig {
  provider: string;
  base_url: string;
  model: string;
  api_key_masked: string;
  api_key_configured: boolean;
  source: string;
  updated_at: string | null;
}

// α 完全自定义：provider 切换不强制覆盖 base_url/model。
// PROVIDER_PRESETS 只作为初始 placeholder / 文档示例，不用于 onProviderChange。
const PROVIDER_PRESETS: Record<string, { base_url: string; default_model: string }> = {
  stepfun: { base_url: "https://api.stepfun.com/step_plan/v1", default_model: "step-3.7-flash" },
  minimax: { base_url: "https://api.minimaxi.com/v1", default_model: "MiniMax-Text-01" },
  openai_compat: { base_url: "https://api.openai.com/v1", default_model: "gpt-4o-mini" },
  kimi: { base_url: "https://api.moonshot.cn/v1", default_model: "moonshot-v1-8k" },
};

export function LLMSettingsCard() {
  const [cfg, setCfg] = useState<LLMConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [showKey, setShowKey] = useState(false);

  // Editable fields
  const [provider, setProvider] = useState("stepfun");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get<LLMConfig>("/api/v1/config/llm");
      setCfg(r);
      setProvider(r.provider);
      setBaseUrl(r.base_url);
      setModel(r.model);
      setApiKey("");
    } catch (e) {
      toast.error("加载 LLM 配置失败", { description: (e as Error).message });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const onProviderChange = (p: string) => {
    // α 完全自定义：只更新 provider 字段，base_url/model 由用户自行填写。
    // provider 仅作为路由标签，backend 决定是否走 stepfun_* override 路径。
    setProvider(p);
  };

  const save = async () => {
    setSaving(true);
    try {
      const payload: any = { provider };
      if (baseUrl) payload.base_url = baseUrl;
      if (model) payload.model = model;
      if (apiKey) payload.api_key = apiKey;
      const r = await api.post<LLMConfig>("/api/v1/config/llm", payload);
      setCfg(r);
      setApiKey("");
      toast.success("LLM 配置已保存", {
        description: r.source === "db" ? "DB 已覆盖" : "请重启后端使新配置生效",
      });
    } catch (e) {
      toast.error("保存失败", { description: (e as Error).message });
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setTesting(true);
    try {
      const payload: any = {};
      if (baseUrl) payload.base_url = baseUrl;
      if (model) payload.model = model;
      if (apiKey) payload.api_key = apiKey;
      const r = await api.post<{ ok: boolean; model: string; tokens: number }>("/api/v1/config/llm/test", payload);
      toast.success("LLM 连接成功", { description: `${r.model} · ${r.tokens} tokens` });
    } catch (e) {
      toast.error("LLM 连接失败", { description: (e as Error).message, duration: 6000 });
    } finally {
      setTesting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="h-4 w-4 text-amber-500" />
          LLM 模型
        </CardTitle>
        <CardDescription>
          配置 AI 研究用的语言模型。兼容 OpenAI API 协议的任何 provider。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {loading || !cfg ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" /> 加载中...
          </div>
        ) : (
          <>
            <div className="space-y-2">
              <Label htmlFor="llm-provider">Provider</Label>
              <select
                id="llm-provider"
                value={provider}
                onChange={(e) => onProviderChange(e.target.value)}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
              >
                <option value="stepfun">Stepfun (step-3.7-flash)</option>
                <option value="minimax">MiniMax (国产)</option>
                <option value="openai_compat">OpenAI 兼容 (vLLM / Ollama / 自建)</option>
                <option value="kimi">Kimi (月之暗面 Moonshot)</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="llm-baseurl">API Base URL</Label>
              <Input
                id="llm-baseurl"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.stepfun.com/step_plan/v1"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="llm-model">模型名</Label>
              <Input
                id="llm-model"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="step-3.7-flash"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="llm-key">API Key (留空保留现有)</Label>
              <div className="flex gap-1.5">
                <Input
                  id="llm-key"
                  type={showKey ? "text" : "password"}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={cfg.api_key_masked || "未配置"}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={() => setShowKey(!showKey)}
                >
                  {showKey ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                </Button>
              </div>
              <p className="text-[10px] text-muted-foreground">
                当前: {cfg.api_key_configured ? cfg.api_key_masked : "(未配置)"} · 来源: {cfg.source}
              </p>
            </div>
            <div className="flex gap-2 pt-1">
              <Button onClick={test} disabled={testing} size="sm" variant="outline">
                {testing ? <Loader2 className="h-3 w-3 animate-spin" /> : "测试连接"}
              </Button>
              <Button onClick={save} disabled={saving} size="sm">
                {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : "保存配置"}
              </Button>
            </div>
            <p className="text-[10px] text-amber-600">
              ⚠ 修改后需重启后端 (uvicorn) 才会生效
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
