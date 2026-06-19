# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Run

```powershell
pip install -r requirements.txt
python app.py
```

No build, no server, no tests.

## Architecture

Single-file Windows desktop widget: `app.py` (~635 lines). Uses Tkinter `overrideredirect` for a borderless, topmost floating window with a transparent color key (`#ff00ff`) to create irregular window shapes. Pillow is used for anti-aliased ring/dot graphics (Tkinter ovals are pixelated).

### Three modes

The window has three visual states, tracked by `self.mode`:

- **hidden** — positioned above the screen, only a 10px peek edge visible. A polling loop (`watch_top_edge`, 80ms interval) detects when the mouse enters the trigger zone and reveals the widget.
- **compact** — a narrow pill (430×74) showing the current top-priority todo with a progress ring and completion button.
- **expanded** — a larger panel (600×470) with focus card, todo list (3 visible, scrollable), input row, priority selector, and history section (3 visible, scrollable). Entered by clicking the compact view.

Transitions: `hidden → compact` on mouse hover near top edge → `compact → hidden` on mouse leave (220ms delay). `compact → expanded` on click (anywhere except click zones). `expanded → hidden` on mouse leave (if entry not focused).

### Click zone pattern

Instead of Tkinter buttons, the UI uses a hit-testing pattern. Each interactive area registers a zone via `self.zone(action, payload, (x1, y1, x2, y2))`. On `Button-1`, `handle_click` iterates `self.click_zones` in reverse order (last-drawn wins) to find a match and calls `self.perform(action, payload)`.

Actions: `complete`, `undo`, `priority`, `add`, `quit`.

### Coordinate-based layout

Everything is drawn on a single `Canvas` with absolute pixel coordinates. There are no layout managers — positioning is manual. The two view sizes (`self.compact_size`, `self.expanded_size`) are centered horizontally via `center_top()`. When changing coordinates, trace through all references in the relevant draw method.

### Data layer

- `Todo` dataclass: `id`, `title`, `priority` (high/medium/low), `status` (active/completed), `created_at`, `completed_at`
- `TodoStore` persists to `%LOCALAPPDATA%\DynamicTodoIsland\todos.json`. On first run it seeds 6 sample todos.
- Active todos are sorted by `priority_weight DESC, created_at ASC`. Completed todos sorted by `completed_at DESC`.
- Priority weights: high=3, medium=2, low=1.

### Visual constants

- Color palette defined at module level: `PANEL`, `FOCUS`, `SURFACE`, `SURFACE_SOFT`, `LINE`, `TEXT`, `TEXT_SOFT`, `MUTED`, `ACCENT`, `RING_MUTED`
- Priority dot colors: `PRIORITY_DOT` (vivid), `PRIORITY_DOT_SOFT` (slightly lighter for dark backgrounds)
- Fonts: `Microsoft YaHei UI` for CJK text, `Segoe UI` for Latin/numeric
- Tkinter has no native blur — glass effect is faked with layered dark shapes, cyan highlights, and subtle dividers

### Scrolling

Two independent scroll offsets (`self.top_scroll`, `self.history_scroll`) control which subset of items is visible. Mouse wheel on the active-todo area scrolls the top list; on the history area scrolls the history list. Maximum 3 visible rows per section — overflow handled by scroll offsets with a custom scrollbar thumb drawn on the right edge.

### Drag

Right-click drag (`B3-Motion`) repositions the window by adjusting geometry offsets. No persistence of custom position — resets on next render cycle.
