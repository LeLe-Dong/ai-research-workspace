"use client";
import * as React from "react";
import { useRouter } from "next/navigation";
import {
  CommandDialog, CommandEmpty, CommandGroup, CommandInput,
  CommandItem, CommandList, CommandShortcut,
} from "@/components/ui/command";
import {
  LayoutDashboard, FlaskConical, BookOpen, History, Settings, Plus, Sun, Moon,
} from "lucide-react";
import { useTheme } from "next-themes";

import { useCommandPalette } from "./command-palette-context";

export function CommandPalette() {
  const { open, setOpen } = useCommandPalette();
  const onOpenChange = setOpen;
  const router = useRouter();
  const { theme, setTheme } = useTheme();

  const navigate = (path: string) => {
    onOpenChange(false);
    router.push(path);
  };

  const toggleTheme = () => {
    setTheme(theme === "dark" ? "light" : "dark");
    onOpenChange(false);
  };

  React.useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, [open, onOpenChange]);

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="搜索页面、操作或研究..." />
      <CommandList>
        <CommandEmpty>未找到结果。</CommandEmpty>

        <CommandGroup heading="导航">
          <CommandItem onSelect={() => navigate("/dashboard")}>
            <LayoutDashboard className="mr-2 h-4 w-4" />
            <span>工作台</span>
            <CommandShortcut>G D</CommandShortcut>
          </CommandItem>
          <CommandItem onSelect={() => navigate("/research")}>
            <FlaskConical className="mr-2 h-4 w-4" />
            <span>研究列表</span>
            <CommandShortcut>G R</CommandShortcut>
          </CommandItem>
          <CommandItem onSelect={() => navigate("/research/new")}>
            <Plus className="mr-2 h-4 w-4" />
            <span>新建研究</span>
            <CommandShortcut>G N</CommandShortcut>
          </CommandItem>
          <CommandItem onSelect={() => navigate("/knowledge")}>
            <BookOpen className="mr-2 h-4 w-4" />
            <span>知识库</span>
            <CommandShortcut>G K</CommandShortcut>
          </CommandItem>
          <CommandItem onSelect={() => navigate("/history")}>
            <History className="mr-2 h-4 w-4" />
            <span>历史</span>
            <CommandShortcut>G H</CommandShortcut>
          </CommandItem>
          <CommandItem onSelect={() => navigate("/settings")}>
            <Settings className="mr-2 h-4 w-4" />
            <span>设置</span>
            <CommandShortcut>G S</CommandShortcut>
          </CommandItem>
        </CommandGroup>

        <CommandGroup heading="操作">
          <CommandItem onSelect={toggleTheme}>
            {theme === "dark" ? (
              <Sun className="mr-2 h-4 w-4" />
            ) : (
              <Moon className="mr-2 h-4 w-4" />
            )}
            <span>切换主题</span>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
