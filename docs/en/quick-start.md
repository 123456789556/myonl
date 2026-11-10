# Quick Start — your first scene in three minutes

> Goal: from nothing to "changed one line, previewed it, packed it into a double-clickable exe".
> No programming needed — editing a text file is enough.

**Note on language:** the engine's directive keywords and the editor UI are Chinese by design (see the "Language" section of the [English README](../README.en.md)). This guide references UI elements by position, so you can follow it without reading Chinese.

## 1. Get the engine

### Route A — release build (recommended)

1. Unzip `MYONL-v1.0.0-rc7-windows.zip` into any folder **outside** `Program Files` (no admin rights needed)
2. Double-click `editor/editor.exe`
3. The editor opens the bundled tutorial project automatically; the live preview appears in the right-hand pane

> The editor relies on the system WebView2 runtime, which ships with Windows 10/11. If no window appears, use Route B.

### Route B — from source

```powershell
pip install -r requirements.txt
py -3 -m engine.editor --project games/教程示例
```

Then open the `http://127.0.0.1:8000` address printed in the terminal.

## 2. Five steps to your first scene

| Step | What you do | Where |
|---|---|---|
| 1 | Click `script.gal` in the left file tree | Left pane |
| 2 | Replace a line such as `@[林晚] 你还不走？` with your own dialogue | Center editor |
| 3 | Press Ctrl+S — the preview on the right refreshes itself | Right pane |
| 4 | Click the **▶ run** button at the top (or Ctrl+R) — a real game window opens | Top bar |
| 5 | Click the **pack** button at the top, pick the project, type a game name, start | Top bar |

The build lands in `dist/<game name>/<game name>.exe`. Double-click it and hand the whole folder to a friend. The release build carries the player runtime inside, so **packing needs neither Python nor PyInstaller** and usually finishes in about a second.

## 3. Create your own project

- In the editor: "new game" button → name → theme → create
- From the command line: `py -3 -m engine.cli new 我的第一个游戏`

A project created in the editor is a **minimal empty shell**: one editable narration line, no images or audio. If you want to start from something that already looks like a scene (background + character art + audio + three acts), copy `games/教程示例` instead. The command-line variant creates an annotated teaching skeleton.

Every project contains: the script `script.gal`, settings `config.json`, asset folders `images/` and `audio/`, and the packaging manifest `pack_config.json`.

## 4. Scripting basics

| Goal | How to write it |
|---|---|
| Change background | `@bg bg_教室` (put the image in `images/`, filename must match) |
| Show a character | `@show 林晚 微笑` (file `images/林晚_微笑.png`) |
| Character line | `@[林晚] 你还不走？` (square brackets name the speaker, no registration needed) |
| Narration | `@ 晚风很轻。` |
| Branching choice | `@choice:` then indented `> option text -> label name` |
| Variables / conditions | `@set 好感 += 1` / `@if 好感 >= 3:` with indented lines below |
| See changes immediately | start with `--hot-reload`: script edits replay from the current scene in under 0.5s |

> Mistakes are cheap: the editor reports which line failed and what it expected, and the preview marks the offending line.

## 5. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Red text or placeholder blocks in the preview | The script references a missing asset: check filenames and letter case under `images/` |
| `editor.exe` opens nothing | WebView2 missing: install the [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/), or use Route B |
| Windows says "protected your PC" | SmartScreen on an unsigned binary: "More info" → "Run anyway" |
| Packing feels slow, or the build is large | Packing copies the bundled runtime, about 1s; output is ~23 MB, and unused assets can be removed |
| You want to replace the sample | Edit `games/教程示例` directly, or create a new game |

## 6. Where to go next

- `docs/开发者使用指南.md` — full directive list, every editor panel, saves/gallery/themes (Chinese)
- `docs/engine_spec.md` — engine specification: DSL, data structures, API (Chinese)
- `docs/插件开发指南.md` — adding your own directives to the engine (Chinese)

## Verify your build actually works

If you want to confirm the whole chain end to end rather than trust the UI:

```powershell
# point --zip at the release package you downloaded
py -3 tools/verify_release_flow.py --zip path\to\MYONL-v1.0.0-rc7-windows.zip
```

It unzips the package, launches the editor with an empty profile and no Python on PATH, edits one line, syntax-checks it, runs it, packs it, and then launches the packed build — each stage asserted, exit code 0 on success.
