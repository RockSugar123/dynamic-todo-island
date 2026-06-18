from __future__ import annotations

import ctypes
import json
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from tkinter import Canvas, Entry, StringVar, Tk

import pystray
from PIL import Image, ImageDraw, ImageFont, ImageTk


APP_DIR = Path.home() / "AppData" / "Local" / "DynamicTodoIsland"
DATA_FILE = APP_DIR / "todos.json"

PRIORITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}
PRIORITY_DOT = {"high": "#ff5a66", "medium": "#ffb84d", "low": "#3d7cff"}
PRIORITY_DOT_SOFT = {"high": "#ff6571", "medium": "#ffc052", "low": "#4f86ff"}

TRANSPARENT = "#ff00ff"
PANEL = "#05070b"
FOCUS = "#091413"
SURFACE = "#111720"
SURFACE_SOFT = "#0c1118"
LINE = "#242b36"
TEXT = "#eef3fa"
TEXT_SOFT = "#c6ceda"
MUTED = "#8791a3"
ACCENT = "#28e4cc"
RING_MUTED = "#253142"

FONT_UI = "Microsoft YaHei UI"
FONT_LATIN = "Segoe UI"


@dataclass
class Todo:
    id: str
    title: str
    priority: str
    status: str
    created_at: str
    completed_at: str | None = None


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def create_todo(title: str, priority: str) -> Todo:
    return Todo(
        id=str(uuid.uuid4()),
        title=title,
        priority=priority,
        status="active",
        created_at=now_iso(),
    )


def short_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1] + "…"


def added_time(todo: Todo) -> str:
    try:
        created = datetime.fromisoformat(todo.created_at)
    except ValueError:
        return "今天"
    return f"今天 {created.strftime('%H:%M')}"


def added_time_short(todo: Todo) -> str:
    try:
        created = datetime.fromisoformat(todo.created_at)
    except ValueError:
        return "添加时间"
    return f"添加 {created.strftime('%H:%M')}"


def completed_time(todo: Todo) -> str:
    if not todo.completed_at:
        return ""
    try:
        completed = datetime.fromisoformat(todo.completed_at)
    except ValueError:
        return ""
    return completed.strftime("%m-%d %H:%M")


class TodoStore:
    def __init__(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        self.todos = self.load()

    def load(self) -> list[Todo]:
        if not DATA_FILE.exists():
            seeded = [
                create_todo("准备产品演示文稿", "high"),
                create_todo("回复关键邮件", "high"),
                create_todo("完成竞品分析报告", "medium"),
                create_todo("整理项目会议纪要", "medium"),
                create_todo("预订周五出差机票", "low"),
                create_todo("复盘本周任务", "low"),
            ]
            self.todos = seeded
            self.save()
            return seeded

        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            return [Todo(**item) for item in data]
        except (json.JSONDecodeError, TypeError):
            return []

    def save(self) -> None:
        DATA_FILE.write_text(
            json.dumps([asdict(todo) for todo in self.todos], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def active(self) -> list[Todo]:
        active = [todo for todo in self.todos if todo.status == "active"]
        return sorted(active, key=lambda todo: (-PRIORITY_WEIGHT[todo.priority], todo.created_at))

    def completed(self) -> list[Todo]:
        completed = [todo for todo in self.todos if todo.status == "completed"]
        return sorted(completed, key=lambda todo: todo.completed_at or "", reverse=True)

    def complete(self, todo_id: str) -> None:
        for todo in self.todos:
            if todo.id == todo_id and todo.status == "active":
                todo.status = "completed"
                todo.completed_at = now_iso()
                self.save()
                return

    def undo(self, todo_id: str) -> None:
        for todo in self.todos:
            if todo.id == todo_id and todo.status == "completed":
                todo.status = "active"
                todo.completed_at = None
                self.save()
                return

    def add(self, title: str, priority: str) -> None:
        self.todos.append(create_todo(title, priority))
        self.save()


class DynamicTodoIsland:
    def __init__(self) -> None:
        self.store = TodoStore()
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        self.root = Tk()
        self.root.title("Dynamic Todo Island")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT)
        try:
            self.root.attributes("-transparentcolor", TRANSPARENT)
        except Exception:
            self.root.configure(bg=PANEL)

        self.compact_size = (460, 84)
        self.expanded_size = (600, 470)
        self.hidden_peek = 10
        self.mode = "hidden"
        self.is_expanded = False
        self.new_priority = "high"
        self.top_scroll = 0
        self.history_scroll = 0
        self.pinned_id: str | None = None
        self.collapse_after_id: str | None = None
        self.drag_start: tuple[int, int] | None = None
        self.click_zones: list[tuple[str, str, tuple[int, int, int, int]]] = []
        self.entry_focused = False
        self.image_refs: list[ImageTk.PhotoImage] = []

        self.canvas = Canvas(self.root, bg=TRANSPARENT, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.entry_var = StringVar()
        self.entry = Entry(
            self.root,
            textvariable=self.entry_var,
            bg=SURFACE,
            fg=TEXT,
            insertbackground=ACCENT,
            relief="flat",
            bd=0,
            font=(FONT_UI, 10),
        )
        self.entry_has_placeholder = False
        self.set_placeholder()
        self.entry.bind("<Return>", lambda _event: self.add_todo())
        self.entry.bind("<FocusIn>", self.clear_placeholder)
        self.entry.bind("<FocusOut>", self.restore_placeholder)

        self.bind_events()
        self.render()
        self.watch_top_edge()

    def bind_events(self) -> None:
        self.root.bind("<Enter>", self.reveal_compact, add="+")
        self.root.bind("<Leave>", self.schedule_collapse, add="+")
        self.canvas.bind("<Enter>", self.reveal_compact, add="+")
        self.canvas.bind("<Leave>", self.schedule_collapse, add="+")
        self.canvas.bind("<Button-1>", self.handle_click)
        self.canvas.bind("<ButtonPress-3>", self.start_drag)
        self.canvas.bind("<B3-Motion>", self.drag)
        self.canvas.bind("<MouseWheel>", self.handle_scroll)

    def center_top(self, width: int, height: int, y: int = 8) -> None:
        screen_width = self.root.winfo_screenwidth()
        x = (screen_width - width) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def watch_top_edge(self) -> None:
        if self.mode == "hidden":
            pointer_x = self.root.winfo_pointerx()
            pointer_y = self.root.winfo_pointery()
            screen_width = self.root.winfo_screenwidth()
            left = (screen_width - self.compact_size[0]) // 2
            right = left + self.compact_size[0]
            if left <= pointer_x <= right and pointer_y <= self.hidden_peek + 4:
                self.reveal_compact()
        self.root.after(80, self.watch_top_edge)

    def rounded_rect(self, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs) -> None:
        points = [
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        ]
        self.canvas.create_polygon(points, smooth=True, **kwargs)

    def draw_panel(self, x1: int, y1: int, x2: int, y2: int, radius: int) -> None:
        self.rounded_rect(x1 + 3, y1 + 5, x2 - 3, y2 + 5, radius, fill="#010204", outline="")
        self.rounded_rect(x1, y1, x2, y2, radius, fill=PANEL, outline="#171e28", width=1)
        self.canvas.create_line(x1 + radius + 8, y1 + 1, x2 - radius - 8, y1 + 1, fill=ACCENT, width=1)

    def draw_ring(self, cx: int, cy: int, size: int, percent: int, label: str | None = None) -> None:
        image = self.make_ring_image(size, percent)
        self.image_refs.append(image)
        self.canvas.create_image(cx, cy, image=image)
        if label:
            self.canvas.create_text(cx, cy, text=label, fill=TEXT, font=(FONT_LATIN, 10))

    def draw_smooth_dot(self, cx: int, cy: int, size: int, color: str) -> None:
        image = self.make_dot_image(size, color)
        self.image_refs.append(image)
        self.canvas.create_image(cx, cy, image=image)

    def draw_completion_ring(self, cx: int, cy: int, size: int, color: str) -> None:
        image = self.make_ring_image(size, 100, track="#465260", accent=color, width=2, full=False)
        self.image_refs.append(image)
        self.canvas.create_image(cx, cy, image=image)

    def make_ring_image(
        self,
        size: int,
        percent: int,
        track: str = RING_MUTED,
        accent: str = ACCENT,
        width: int = 4,
        full: bool = True,
    ) -> ImageTk.PhotoImage:
        scale = 8
        canvas_size = size * scale
        stroke = width * scale
        pad = stroke // 2 + scale
        image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        box = (pad, pad, canvas_size - pad, canvas_size - pad)
        draw.ellipse(box, outline=track, width=stroke)
        if full:
            draw.arc(box, start=-10, end=-10 + int(360 * max(percent, 2) / 100), fill=accent, width=stroke)
        else:
            draw.ellipse(box, outline=accent, width=stroke)
        image = image.resize((size, size), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(image)

    def make_dot_image(self, size: int, color: str) -> ImageTk.PhotoImage:
        scale = 8
        canvas_size = size * scale
        image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        pad = scale
        draw.ellipse((pad, pad, canvas_size - pad, canvas_size - pad), fill=color)
        image = image.resize((size, size), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(image)

    def _load_font(self, family: str, size: int) -> ImageFont.FreeTypeFont:
        cache_key = (family, size)
        if not hasattr(self, "_font_cache"):
            self._font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]
        font_dir = Path("C:/Windows/Fonts")
        font_map = {
            "Microsoft YaHei UI": ("msyh.ttc", 1),
            "Microsoft YaHei": ("msyh.ttc", 0),
            "Segoe UI": ("segoeui.ttf", 0),
        }
        try:
            filename, index = font_map.get(family, ("msyh.ttc", 0))
            font = ImageFont.truetype(str(font_dir / filename), size * 2, index=index)
        except Exception:
            font = ImageFont.load_default()
        self._font_cache[cache_key] = font
        return font

    def make_text_image(self, text: str, family: str, size: int, color: str) -> ImageTk.PhotoImage:
        scale = 2
        font = self._load_font(family, size)
        bbox = font.getbbox(text)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        pad_x = 4 * scale
        pad_y = 2 * scale
        canvas_w = text_w + pad_x * 2
        canvas_h = text_h + pad_y * 2
        image = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.text((pad_x, pad_y), text, fill=color, font=font)
        image = image.resize((canvas_w // scale, canvas_h // scale), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(image)

    def zone(self, action: str, payload: str, box: tuple[int, int, int, int]) -> None:
        self.click_zones.append((action, payload, box))

    def render(self) -> None:
        if self.mode == "expanded":
            self.draw_expanded()
        else:
            self.draw_compact()

    def draw_compact(self) -> None:
        self.click_zones = []
        self.image_refs = []
        self.entry.place_forget()
        self.canvas.delete("all")
        self.canvas.configure(width=self.compact_size[0], height=self.compact_size[1])
        if self.mode == "hidden":
            self.center_top(*self.compact_size, y=-(self.compact_size[1] - self.hidden_peek))
        else:
            self.center_top(*self.compact_size)

        active = self.store.active()
        completed_count = len(self.store.completed())
        total_count = len(self.store.todos)
        percent = 100 if total_count == 0 else round(completed_count / total_count * 100)
        remaining = str(len(active))

        pinned = None
        if self.pinned_id:
            for todo in active:
                if todo.id == self.pinned_id:
                    pinned = todo
                    break
            if pinned is None:
                self.pinned_id = None
        current = pinned if pinned else (active[0] if active else None)
        is_pinned = pinned is not None

        self.draw_panel(14, 8, 446, 74, 28)
        if self.mode == "hidden":
            self.rounded_rect(165, 75, 295, 83, 4, fill="#101820", outline="#182630", width=1)
            self.canvas.create_line(180, 76, 280, 76, fill=ACCENT, width=1)
        self.draw_ring(49, 41, 46, percent, remaining)

        if current:
            if is_pinned:
                self.canvas.create_line(82, 26, 82, 60, fill=ACCENT, width=2)
            self.canvas.create_text(96 if is_pinned else 88, 33, anchor="w", text=short_text(current.title, 17), fill=TEXT, font=(FONT_UI, 9))
            self.canvas.create_text(96 if is_pinned else 88, 53, anchor="w", text=added_time_short(current), fill=MUTED, font=(FONT_UI, 9))
            self.draw_completion_ring(420, 41, 24, ACCENT)
            self.zone("complete", current.id, (400, 22, 440, 60))
        else:
            self.canvas.create_text(88, 33, anchor="w", text="所有待办都完成了", fill=TEXT, font=(FONT_UI, 9))
            self.canvas.create_text(88, 53, anchor="w", text="完成历史仍保存在本机", fill=MUTED, font=(FONT_UI, 9))

    def draw_expanded(self) -> None:
        self.click_zones = []
        self.image_refs = []
        self.canvas.delete("all")
        self.canvas.configure(width=self.expanded_size[0], height=self.expanded_size[1])
        self.center_top(*self.expanded_size)

        active = self.store.active()
        completed = self.store.completed()
        total_count = len(self.store.todos)
        percent = 100 if total_count == 0 else round(len(completed) / total_count * 100)
        exp_remaining = str(len(active))
        current = active[0] if active else None

        self.draw_panel(10, 8, 590, 458, 24)
        self.draw_header()

        self.draw_focus_card(22, 62, 578, 136, current, percent, exp_remaining)
        self.draw_top_section(22, 158, active)
        self.draw_input_row(22, 285)
        self.draw_history_section(22, 350, completed)

    def draw_header(self) -> None:
        self.canvas.create_oval(28, 32, 38, 42, fill=ACCENT, outline="")
        self.canvas.create_text(48, 37, anchor="w", text="Aurora Signal", fill="#a8b0bf", font=(FONT_LATIN, 11))
        self.canvas.create_text(300, 37, text="今日待办", fill=TEXT, font=(FONT_UI, 12))
        self.canvas.create_line(238, 58, 362, 58, fill=ACCENT, width=2)
        self.canvas.create_text(552, 37, text="×", fill="#b9c1ce", font=(FONT_LATIN, 18))
        self.zone("quit", "", (534, 20, 574, 56))

    def draw_focus_card(self, x: int, y: int, x2: int, y2: int, current: Todo | None, percent: int, label: str = "") -> None:
        if y2 < 66:
            return
        self.rounded_rect(x, y, x2, y2, 10, fill=FOCUS, outline="#1c2731", width=1)
        if current:
            title = f"聚焦：{short_text(current.title, 17)}"
            meta = f"添加于 {added_time(current)}"
        else:
            title = "今天的队列清空了"
            meta = "完成历史已保存在本机"
        title_img = self.make_text_image(title, FONT_UI, 15, TEXT)
        self.image_refs.append(title_img)
        self.canvas.create_image(x + 20, y + 27, anchor="w", image=title_img)
        meta_img = self.make_text_image(meta, FONT_UI, 10, "#a8b2c2")
        self.image_refs.append(meta_img)
        self.canvas.create_image(x + 20, y + 51, anchor="w", image=meta_img)
        self.draw_ring(x2 - 48, y + 39, 54, percent, label)

    def draw_top_section(self, x: int, y: int, todos: list[Todo]) -> None:
        self.canvas.create_text(x + 10, y, anchor="w", text="待办", fill=TEXT_SOFT, font=(FONT_UI, 10))
        list_y = y + 22
        row_h = 27
        visible_count = 3
        self.rounded_rect(x, list_y, x + 556, list_y + row_h * visible_count, 9, fill=SURFACE_SOFT, outline="#27313d", width=1)

        if not todos:
            self.canvas.create_text(x + 278, list_y + 41, text="暂时没有未完成待办", fill=MUTED, font=(FONT_UI, 10))
            return

        self.top_scroll = min(self.top_scroll, max(0, len(todos) - visible_count))
        visible = todos[self.top_scroll : self.top_scroll + visible_count]
        for visible_index, todo in enumerate(visible):
            index = self.top_scroll + visible_index
            top = list_y + visible_index * row_h
            row_y = top + row_h // 2
            is_pinned = todo.id == self.pinned_id
            if is_pinned:
                self.rounded_rect(x + 14, top + 1, x + 542, top + row_h - 1, 6, fill="#0d1a1a", outline="#1a3a38", width=1)
            if visible_index:
                self.canvas.create_line(x + 14, top, x + 542, top, fill=LINE)
            self.canvas.create_text(x + 22, row_y, text=str(index + 1), fill="#9ea7b5", font=(FONT_LATIN, 10))
            self.draw_smooth_dot(x + 60, row_y, 8, PRIORITY_DOT_SOFT[todo.priority])
            if is_pinned:
                self.canvas.create_text(x + 70, row_y, text="◆", fill=ACCENT, font=(FONT_LATIN, 7))
            self.canvas.create_text(x + 82, row_y, anchor="w", text=short_text(todo.title, 17), fill="#f4f7fb", font=(FONT_UI, 9))
            self.canvas.create_text(x + 450, row_y, anchor="e", text=added_time_short(todo), fill="#9aa6b8", font=(FONT_UI, 9))
            self.draw_completion_ring(x + 520, row_y, 18, ACCENT if index == 0 else "#475260")
            self.zone("pin", todo.id, (x + 40, top, x + 440, top + row_h))
            self.zone("complete", todo.id, (x + 500, row_y - 16, x + 544, row_y + 16))
        if len(todos) > visible_count:
            self.draw_scroll_hint(x + 544, list_y + 8, row_h * visible_count - 16, self.top_scroll, len(todos), visible_count)

    def draw_input_row(self, x: int, y: int) -> None:
        self.rounded_rect(x, y, x + 556, y + 48, 10, fill=SURFACE, outline="#27313d", width=1)
        self.canvas.create_text(x + 22, y + 24, text="+", fill="#b5becb", font=(FONT_LATIN, 20))
        self.entry.configure(bg=SURFACE)
        self.entry.place(x=x + 48, y=y + 13, width=250, height=24)
        if not self.entry_focused:
            self.canvas.create_text(x + 332, y + 24, anchor="w", text="Enter 添加", fill=MUTED, font=(FONT_UI, 9))
        self.draw_priority_switches(x + 438, y + 10)
        self.zone("add", "", (x + 324, y + 8, x + 414, y + 40))

    def draw_priority_switches(self, x: int, y: int) -> None:
        for index, key in enumerate(["high", "medium", "low"]):
            left = x + index * 36
            selected = key == self.new_priority
            self.rounded_rect(left, y, left + 30, y + 28, 14, fill="#121924", outline="#2b3544", width=1)
            if selected:
                self.draw_completion_ring(left + 15, y + 14, 22, ACCENT)
            self.draw_smooth_dot(left + 15, y + 14, 12, PRIORITY_DOT_SOFT[key])
            self.zone("priority", key, (left, y, left + 30, y + 28))

    def draw_history_section(self, x: int, y: int, completed: list[Todo]) -> None:
        self.canvas.create_text(x + 10, y, anchor="w", text="完成历史", fill=TEXT_SOFT, font=(FONT_UI, 10))
        list_y = y + 18
        row_h = 25
        visible_count = 3
        self.rounded_rect(x, list_y, x + 556, list_y + row_h * visible_count, 9, fill="#080d13", outline="#202a35", width=1)
        if not completed:
            self.canvas.create_text(x + 278, list_y + 38, text="完成后会在这里留下历史记录", fill=MUTED, font=(FONT_UI, 9))
            return

        self.history_scroll = min(self.history_scroll, max(0, len(completed) - visible_count))
        visible = completed[self.history_scroll : self.history_scroll + visible_count]
        for visible_index, todo in enumerate(visible):
            yy = list_y + visible_index * row_h + row_h // 2
            if visible_index:
                self.canvas.create_line(x + 14, list_y + visible_index * row_h, x + 542, list_y + visible_index * row_h, fill="#1d2631")
            self.canvas.create_text(x + 12, yy, anchor="w", text=short_text(todo.title, 21), fill="#aeb7c5", font=(FONT_UI, 9))
            self.canvas.create_text(x + 390, yy, anchor="e", text=completed_time(todo), fill="#737f91", font=(FONT_UI, 9))
            self.rounded_rect(x + 440, yy - 11, x + 490, yy + 11, 11, fill="#111923", outline="#2a3441", width=1)
            self.canvas.create_text(x + 465, yy, text="撤回", fill=ACCENT, font=(FONT_UI, 9))
            self.zone("undo", todo.id, (x + 434, yy - 15, x + 498, yy + 15))
        if len(completed) > visible_count:
            self.draw_scroll_hint(x + 544, list_y + 8, row_h * visible_count - 16, self.history_scroll, len(completed), visible_count)

    def draw_scroll_hint(self, x: int, y: int, height: int, offset: int, total: int, visible: int) -> None:
        track_color = "#18212b"
        thumb_color = "#4b5868"
        self.rounded_rect(x, y, x + 4, y + height, 2, fill=track_color, outline="")
        max_offset = max(1, total - visible)
        thumb_h = max(14, int(height * visible / total))
        travel = max(1, height - thumb_h)
        thumb_y = y + int(travel * offset / max_offset)
        self.rounded_rect(x, thumb_y, x + 4, thumb_y + thumb_h, 2, fill=thumb_color, outline="")

    def reveal_compact(self, _event=None) -> None:
        if self.collapse_after_id:
            self.root.after_cancel(self.collapse_after_id)
            self.collapse_after_id = None
        if self.mode == "hidden":
            self.mode = "compact"
            self.is_expanded = False
            self.render()

    def expand(self, _event=None) -> None:
        if self.collapse_after_id:
            self.root.after_cancel(self.collapse_after_id)
            self.collapse_after_id = None
        if self.mode != "expanded":
            self.mode = "expanded"
            self.is_expanded = True
            self.top_scroll = 0
            self.history_scroll = 0
            self.render()

    def schedule_collapse(self, _event=None) -> None:
        if self.entry.focus_get() is self.entry:
            return
        if self.collapse_after_id:
            self.root.after_cancel(self.collapse_after_id)
        self.collapse_after_id = self.root.after(220, self.hide_if_pointer_left)

    def hide_if_pointer_left(self) -> None:
        pointer_x = self.root.winfo_pointerx()
        pointer_y = self.root.winfo_pointery()
        x = self.root.winfo_rootx()
        y = self.root.winfo_rooty()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        if x <= pointer_x <= x + width and y <= pointer_y <= y + height:
            return
        screen_width = self.root.winfo_screenwidth()
        trigger_left = (screen_width - self.compact_size[0]) // 2
        trigger_right = trigger_left + self.compact_size[0]
        if self.mode == "compact" and trigger_left <= pointer_x <= trigger_right and pointer_y <= self.hidden_peek + 8:
            self.collapse_after_id = self.root.after(700, self.hide_if_pointer_left)
            return
        self.root.focus()
        self.mode = "hidden"
        self.is_expanded = False
        self.render()

    def handle_scroll(self, event) -> None:
        if self.mode != "expanded":
            return
        direction = -1 if event.delta > 0 else 1
        active = self.store.active()
        completed = self.store.completed()
        if 180 <= event.y <= 261:
            self.top_scroll = min(max(0, len(active) - 3), max(0, self.top_scroll + direction))
        elif 368 <= event.y <= 443:
            self.history_scroll = min(max(0, len(completed) - 3), max(0, self.history_scroll + direction))
        else:
            if direction > 0 and len(completed) > 3:
                self.history_scroll = min(max(0, len(completed) - 3), self.history_scroll + 1)
            elif direction < 0 and len(active) > 3:
                self.top_scroll = max(0, self.top_scroll - 1)
        self.draw_expanded()

    def handle_click(self, event) -> None:
        for action, payload, (x1, y1, x2, y2) in reversed(self.click_zones):
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.perform(action, payload)
                return
        if self.mode == "compact":
            self.expand()

    def perform(self, action: str, payload: str) -> None:
        if action == "complete":
            self.store.complete(payload)
            if self.pinned_id == payload:
                self.pinned_id = None
            self.render()
        elif action == "pin":
            self.pinned_id = None if self.pinned_id == payload else payload
            self.render()
        elif action == "undo":
            self.store.undo(payload)
            self.render()
        elif action == "priority":
            self.new_priority = payload
            self.draw_expanded()
        elif action == "add":
            self.add_todo()
        elif action == "quit":
            self.quit_app()

    def set_placeholder(self) -> None:
        self.entry_has_placeholder = True
        self.entry_var.set("添加新待办...")
        self.entry.configure(fg="#5f6876")

    def clear_placeholder(self, _event=None) -> None:
        self.expand()
        self.entry_focused = True
        if self.entry_has_placeholder:
            self.entry_var.set("")
            self.entry.configure(fg=TEXT)
            self.entry_has_placeholder = False
        if self.mode == "expanded":
            self.draw_expanded()

    def restore_placeholder(self, _event=None) -> None:
        self.entry_focused = False
        if not self.entry_var.get().strip():
            self.set_placeholder()
        if self.mode == "expanded":
            self.draw_expanded()

    def add_todo(self) -> None:
        if self.entry_has_placeholder:
            self.entry.focus_set()
            return
        title = self.entry_var.get().strip()
        if not title:
            self.entry.focus_set()
            return
        self.store.add(title, self.new_priority)
        self.entry_var.set("")
        self.restore_placeholder()
        self.top_scroll = 0
        self.render()

    def start_drag(self, event) -> None:
        self.drag_start = (event.x_root, event.y_root)

    def drag(self, event) -> None:
        if not self.drag_start:
            return
        current_geometry = self.root.geometry().split("+")
        current_x = int(current_geometry[1])
        current_y = int(current_geometry[2])
        dx = event.x_root - self.drag_start[0]
        dy = event.y_root - self.drag_start[1]
        self.root.geometry(f"+{current_x + dx}+{current_y + dy}")
        self.drag_start = (event.x_root, event.y_root)

    def _make_tray_icon(self) -> Image.Image:
        size = 32
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        pad = 5
        draw.ellipse((pad, pad, size - pad, size - pad), fill=ACCENT)
        return image

    def _tray_show(self, _icon=None, _item=None) -> None:
        self.root.after(0, self.reveal_compact)

    def _tray_quit(self, _icon=None, _item=None) -> None:
        self.root.after(0, self.quit_app)

    def quit_app(self) -> None:
        if hasattr(self, "tray_icon") and self.tray_icon is not None:
            self.tray_icon.stop()
        self.root.destroy()

    def run(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem("显示", self._tray_show, default=True),
            pystray.MenuItem("退出", self._tray_quit),
        )
        self.tray_icon = pystray.Icon("todo_island", self._make_tray_icon(), "Dynamic Todo Island", menu)
        tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        tray_thread.start()
        self.root.mainloop()


if __name__ == "__main__":
    DynamicTodoIsland().run()
