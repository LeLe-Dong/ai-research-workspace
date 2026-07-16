"use client";
import { useState } from "react";
import { Plus, X, Tag as TagIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useTags, useAttachTag, useCreateTag } from "../hooks";

interface TagSelectorProps {
  researchId: string;
  currentTags: { id: string; name: string; color: string }[];
  onDetach: (tagId: string) => void;
}

const TAG_COLORS: Record<string, string> = {
  blue: "bg-blue-500/15 text-blue-700 border-blue-500/30 dark:text-blue-300",
  green: "bg-emerald-500/15 text-emerald-700 border-emerald-500/30 dark:text-emerald-300",
  red: "bg-red-500/15 text-red-700 border-red-500/30 dark:text-red-300",
  amber: "bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-300",
  purple: "bg-purple-500/15 text-purple-700 border-purple-500/30 dark:text-purple-300",
};

export function TagSelector({ researchId, currentTags, onDetach }: TagSelectorProps) {
  const { data: allTags = [] } = useTags();
  const attachTag = useAttachTag();
  const createTag = useCreateTag();
  const [open, setOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newColor, setNewColor] = useState("blue");

  const currentTagIds = new Set(currentTags.map(t => t.id));
  const availableTags = allTags.filter(t => !currentTagIds.has(t.id));

  const handleAddExisting = async (tagId: string) => {
    await attachTag.mutateAsync({ researchId, tagId });
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      const tag = await createTag.mutateAsync({ name: newName.trim().toLowerCase(), color: newColor });
      await attachTag.mutateAsync({ researchId, tagId: tag.id });
      setNewName("");
      setOpen(false);
    } catch (e) {
      // error handled by mutation
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {currentTags.map(tag => (
          <Badge
            key={tag.id}
            variant="outline"
            className={TAG_COLORS[tag.color] || TAG_COLORS.blue}
          >
            <TagIcon className="mr-1 h-3 w-3" />
            {tag.name}
            <button
              onClick={() => onDetach(tag.id)}
              className="ml-1.5 rounded-full hover:bg-black/10"
              title="移除标签"
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm" className="h-6 px-2 text-xs">
              <Plus className="mr-1 h-3 w-3" />
              添加标签
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-72" align="start">
            <div className="space-y-3">
              <div>
                <h4 className="mb-2 text-sm font-medium">选择已有标签</h4>
                {availableTags.length === 0 ? (
                  <p className="text-xs text-muted-foreground">无更多标签</p>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {availableTags.map(tag => (
                      <button
                        key={tag.id}
                        onClick={() => { handleAddExisting(tag.id); setOpen(false); }}
                        className="transition-opacity hover:opacity-70"
                      >
                        <Badge variant="outline" className={TAG_COLORS[tag.color] || TAG_COLORS.blue}>
                          {tag.name}
                          {tag.count !== undefined && <span className="ml-1 text-[10px] opacity-60">{tag.count}</span>}
                        </Badge>
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="border-t pt-2">
                <h4 className="mb-2 text-sm font-medium">或新建标签</h4>
                <div className="flex gap-2">
                  <Input
                    placeholder="标签名"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                    className="h-7 text-xs"
                  />
                  <select
                    value={newColor}
                    onChange={(e) => setNewColor(e.target.value)}
                    className="h-7 rounded-md border bg-background px-2 text-xs"
                  >
                    {Object.keys(TAG_COLORS).map(c => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                  <Button size="sm" className="h-7" onClick={handleCreate}>
                    创建
                  </Button>
                </div>
              </div>
            </div>
          </PopoverContent>
        </Popover>
      </div>
    </div>
  );
}
