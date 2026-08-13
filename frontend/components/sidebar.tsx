"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, FlaskConical, BookOpen, History, Settings,
  Sparkles, ChevronDown, Layers,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

export function Sidebar() {
  const pathname = usePathname();
  const { data: dashData } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<{ stats: { running: number; kb_count?: number } }>("/api/v1/dashboard"),
    // Sidebar lives in the root layout, so it only mounts once per session.
    // A long staleTime avoids refetching on every route change in the same
    // session. The dashboard page (also reading the same query key) will
    // surface fresh data when the user actually opens it.
    staleTime: 60_000,
    gcTime: 5 * 60_000,
  });
  const runningCount = dashData?.stats.running ?? 0;
  const kbCount = dashData?.stats.kb_count ?? 0;

  const nav = [
    { href: "/dashboard", label: "工作台", icon: LayoutDashboard },
    {
      href: "/research",
      label: "研究",
      icon: FlaskConical,
      badge: runningCount > 0 ? `${runningCount}` : null,
      badgeClass: runningCount > 0 ? "bg-info text-white animate-pulse" : undefined,
    },
    {
      href: "/knowledge",
      label: "知识库",
      icon: BookOpen,
      badge: kbCount > 0 ? `${kbCount}` : null,
      badgeClass: kbCount > 0 ? "bg-muted text-foreground" : undefined,
    },
    { href: "/history", label: "历史", icon: History },
    { href: "/topics", label: "研究基线", icon: Layers },
    { href: "/settings", label: "设置", icon: Settings },
  ];
  return (
    <aside className="hidden md:flex md:w-60 md:flex-col md:border-r md:bg-card md:fixed md:inset-y-0 md:left-0 md:z-30">
      {/* Brand */}
      <div className="flex h-14 items-center gap-2 border-b px-4">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
          <Sparkles className="h-4 w-4" />
        </div>
        <div className="flex flex-col leading-tight">
          <span className="text-sm font-semibold">Research Workspace</span>
          <span className="text-[10px] text-muted-foreground">企业级 AI 研究平台</span>
        </div>
      </div>

      {/* Workspace switcher */}
      <button className="mx-3 mt-3 flex items-center justify-between rounded-md border bg-background px-3 py-2 text-sm hover:bg-accent">
        <div className="flex items-center gap-2">
          <div className="flex h-5 w-5 items-center justify-center rounded bg-gradient-to-br from-blue-500 to-purple-500 text-[10px] font-bold text-white">D</div>
          <span className="font-medium">默认工作区</span>
        </div>
        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
      </button>

      {/* Nav */}
      <nav className="flex-1 space-y-0.5 px-3 py-3">
        <p className="px-2 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">工作区</p>
        {nav.map((item) => {
          const Icon = item.icon;
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
                active ? "bg-accent text-accent-foreground font-medium" : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4" />
              <span className="flex-1">{item.label}</span>
              {item.badge && (
                <Badge
                  variant={item.badgeClass ? undefined : "info"}
                  className={"h-4 px-1 text-[10px] " + (item.badgeClass ?? "")}
                >
                  {item.badge}
                </Badge>
              )}
            </Link>
          );
        })}
      </nav>

      <Separator />

      {/* Agent status */}
      <div className="px-3 py-3">
        <p className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">智能体状态</p>
        <div className="rounded-md border bg-background p-2.5">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500 opacity-75"></span>
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
            </span>
            <span className="text-xs font-medium">Hermes Engine</span>
            <Badge variant="success" className="ml-auto h-4 px-1 text-[10px]">在线</Badge>
          </div>
          <p className="mt-1.5 text-[10px] text-muted-foreground">演示模式 · v0.1</p>
        </div>
      </div>
    </aside>
  );
}
