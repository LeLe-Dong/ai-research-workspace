"use client";
import * as React from "react";
import { Search, Bell, Command, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { ThemeToggle } from "@/components/theme-toggle";
import { Separator } from "@/components/ui/separator";
import Link from "next/link";
import { useRouter } from "next/navigation";

/* ------------------------------------------------------------------ */
/*  Notification types & mock data                                      */
/* ------------------------------------------------------------------ */

type NotificationItem = {
  id: string;
  title: string;
  description: string;
  time: string;
  read: boolean;
  href?: string;
};

// In production this comes from GET /api/v1/notifications.
// For now we derive lightweight items from dashboard + recent activity.
function getMockNotifications(): NotificationItem[] {
  const now = new Date();
  const fmt = (d: Date) => {
    const diff = Math.floor((now.getTime() - d.getTime()) / 1000);
    if (diff < 60) return "刚刚";
    if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
    return d.toLocaleDateString("zh-CN");
  };
  return [
    {
      id: "n1",
      title: "系统就绪",
      description: "Hermes Engine 已连接，演示模式运行中",
      time: fmt(new Date(now.getTime() - 120_000)),
      read: true,
    },
    {
      id: "n2",
      title: "研究完成",
      description: "「PostgreSQL vs TiDB 选型分析」已完成，评分 8.4",
      time: fmt(new Date(now.getTime() - 3600_000)),
      read: false,
      href: "/research/abc123",
    },
    {
      id: "n3",
      title: "版本已创建",
      description: "研究 abc123 的 v2 版本已自动记录",
      time: fmt(new Date(now.getTime() - 7200_000)),
      read: false,
      href: "/history/abc123",
    },
  ];
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function Topbar() {
  const router = useRouter();
  const [searchOpen, setSearchOpen] = React.useState(false);
  const [searchValue, setSearchValue] = React.useState("");
  const [notifOpen, setNotifOpen] = React.useState(false);
  const notifRef = React.useRef<HTMLDivElement>(null);
  const notifList = getMockNotifications();
  const unreadCount = notifList.filter(n => !n.read).length;

  // Close notification dropdown on outside click
  React.useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setNotifOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Global Cmd/Ctrl+K shortcut to focus search
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen(true);
      }
      if (e.key === "Escape") {
        setSearchOpen(false);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  const onSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = searchValue.trim();
    if (q) {
      router.push(`/research?q=${encodeURIComponent(q)}`);
    } else {
      router.push("/research");
    }
    setSearchOpen(false);
  };

  const onNotifClick = (href?: string) => {
    setNotifOpen(false);
    if (href) router.push(href);
  };

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b bg-background/80 px-4 backdrop-blur md:pl-60">
      {/* Search */}
      <div className="relative max-w-md flex-1">
        {searchOpen ? (
          <form onSubmit={onSearchSubmit} className="flex items-center gap-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              autoFocus
              value={searchValue}
              onChange={(e) => setSearchValue(e.target.value)}
              placeholder="搜索研究标题或目标..."
              className="h-8 pl-8 pr-8 text-sm"
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="absolute right-1 h-6 w-6"
              onClick={() => { setSearchOpen(false); setSearchValue(""); }}
            >
              <X className="h-3 w-3" />
            </Button>
          </form>
        ) : (
          <button
            onClick={() => setSearchOpen(true)}
            className="flex w-full items-center gap-2 rounded-md border border-input bg-background px-3 py-1.5 text-left text-sm text-muted-foreground hover:bg-accent/50"
          >
            <Search className="h-3.5 w-3.5" />
            <span className="flex-1">搜索研究、知识库...</span>
            <kbd className="pointer-events-none hidden h-5 items-center gap-1 rounded border bg-muted px-1.5 font-mono text-[10px] text-muted-foreground sm:inline-flex">
              <Command className="h-2.5 w-2.5" />K
            </kbd>
          </button>
        )}
      </div>

      <div className="ml-auto flex items-center gap-1">
        <Button size="sm" asChild>
          <Link href="/research/new">
            <Plus className="h-3.5 w-3.5" />
            New Research
          </Link>
        </Button>
        <Separator orientation="vertical" className="mx-1 h-5" />

        {/* Notifications */}
        <div className="relative" ref={notifRef}>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Notifications"
            onClick={() => setNotifOpen(v => !v)}
            className="relative"
          >
            <Bell className="h-4 w-4" />
            {unreadCount > 0 && (
              <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[9px] font-bold text-destructive-foreground">
                {unreadCount}
              </span>
            )}
          </Button>

          {notifOpen && (
            <div className="absolute right-0 top-full z-50 mt-1 w-80 rounded-md border bg-background shadow-lg">
              <div className="flex items-center justify-between border-b px-3 py-2">
                <span className="text-xs font-semibold">通知</span>
                <span className="text-[10px] text-muted-foreground">{unreadCount} 条未读</span>
              </div>
              <div className="max-h-80 overflow-y-auto">
                {notifList.length === 0 ? (
                  <p className="px-3 py-4 text-center text-xs text-muted-foreground">暂无通知</p>
                ) : (
                  notifList.map((n) => (
                    <button
                      key={n.id}
                      onClick={() => onNotifClick(n.href)}
                      className={"flex w-full flex-col gap-0.5 px-3 py-2.5 text-left text-xs transition-colors hover:bg-accent/50 " + (!n.read ? "bg-accent/20" : "")}
                    >
                      <div className="flex items-center justify-between">
                        <span className={"font-medium " + (!n.read ? "text-foreground" : "text-muted-foreground")}>{n.title}</span>
                        <span className="text-[10px] text-muted-foreground">{n.time}</span>
                      </div>
                      <p className="text-muted-foreground">{n.description}</p>
                    </button>
                  ))
                )}
              </div>
              <div className="border-t px-3 py-1.5 text-center">
                <Button variant="ghost" size="sm" className="h-6 text-[10px]" asChild>
                  <Link href="/history">查看全部历史</Link>
                </Button>
              </div>
            </div>
          )}
        </div>

        <ThemeToggle />
        <Separator orientation="vertical" className="mx-1 h-5" />
        <Avatar>
          <AvatarFallback>PB</AvatarFallback>
        </Avatar>
      </div>
    </header>
  );
}
