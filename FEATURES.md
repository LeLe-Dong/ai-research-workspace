# AI Research Workspace — Features Overview

## Tagging & Categorization (新增)

### 用途
用标签给研究分类，方便后续查找和聚合。

### 用法
1. **在研究详情页添加标签**：
   - 进入 `/research/{id}`
   - 点击 "添加标签" 按钮
   - 选择已有标签 或 创建新标签（5 种颜色可选）
2. **API**：
   - `GET /api/v1/tags` - 列出所有标签 + 使用次数
   - `POST /api/v1/tags` - 创建标签
   - `POST /api/v1/tags/researches/{id}/attach` - 附加到研究（id 或 name）
   - `POST /api/v1/tags/researches/{id}/detach?tag_id=` - 移除
   - `GET /api/v1/tags/researches/{id}` - 查询某研究的标签
3. **创建研究时附加**：
   ```json
   POST /api/v1/researches
   {
     "title": "...",
     "goal": "...",
     "tag_names": ["langchain", "agent", "urgent"]
   }
   ```

### 标签表
| 字段 | 类型 | 描述 |
|---|---|---|
| id | string (12) | 内部 ID |
| name | string (50, unique) | 标签名（小写、trim） |
| color | string (20) | 5 色之一：blue/green/red/amber/purple |
| created_at | datetime | 创建时间 |

### 测试
6 个 pytest 用例覆盖 CRUD + 校验 + 幂等 + 多对多。

---

## Report Visualization (增强)

### 新增组件
1. **ReportStats 卡**：报告页头下方
   - 词数（word count）
   - 阅读时长估算（中文 400 字/分钟）
   - 已完成章节数
2. **ReviewRadar 雷达图**：6 维评分可视化
   - 纯 SVG，无额外依赖
   - 6 维轴 + 评分多边形 + 阈值虚线
   - 自动适配 6-7 维（无论是 technical_feasibility + 6 维还是 7 维）
3. **TableOfContents 侧边栏**：sticky 大纲
   - 桌面端固定右侧
   - 点击切换 tab
   - 不可用项灰色禁用
4. **逐 tab 下载按钮**：每个 section 独立的 .md 下载
5. **未达阈值 banner**：从 header 移到独立 Card，更醒目

### 文件
- `frontend/features/research/components/report-view.tsx`（约 400 行重写）

### a11y 改进
- 移除 `<a href="#summary">` → 改用 `<button onClick>` 切换 tab（更可靠）
- 加 `cursor-pointer` / `cursor-not-allowed` 视觉反馈
- 雷达图 SVG 加 `<text>` 标签

---

## Migration Notes

### DB Schema
新增 2 张表（自动建表，不需要迁移）：
- `tags` (id, name, color, created_at)
- `research_tags` (research_id, tag_id, created_at) - M:N

### 兼容性
- 现有研究报告 `tags=[]`（默认空列表）
- 不需要回填脚本
