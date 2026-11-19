# Quick Start — get something playable

> Goal: from nothing to "changed one line, previewed it, exported a bundle a friend can open".
> No programming needed — editing a text line is enough. The phone / Android APK is the primary
> route; the desktop is only needed for video/camera effects, APK builds, and tests.

**Note on language:** the directive keywords and the editor UI are Chinese by design (see the
[English README](../../README.en.md)). This guide refers to UI elements
by position so you can follow it without reading Chinese.

## 1. Install and open

**Phone / tablet (recommended)**

1. Download `MYONL-v1.2.0.apk` from the Releases page (Android 7.0+; one package serves phones
   and Android tablets).
2. Install and open it: you land on the project shelf. Tap **new project** to start.
3. To see what a finished game looks like first: tap **try the sample** on the home screen.

**Desktop browser (nothing installed)**

- A single-file `.html` someone exported opens in any browser. To author on a computer, see the
  [developer guide](../开发者使用指南.md) (Chinese).

> There is no iOS build. On the player side, any modern browser can open the single-file bundle.

## 2. Five steps to your first scene

| Step | What you do | Where |
|---|---|---|
| 1 | Create a project and open the script editor | Shelf, **＋ new project** |
| 2 | Replace the sample line with your own dialogue, one line per beat | Center editor |
| 3 | Save; the preview on the right refreshes itself | Save button / autosave |
| 4 | Add a background image and a character line (syntax below) | Bottom **assets** tab |
| 5 | Bottom **export** — you get one self-contained `.html` | **Export** tab |

The exported `.html` inlines the player, script and assets into one file. Send it over chat or
copy it to a computer; it opens in a browser — no engine install, no network, no server.

## 3. Your first script line

One directive per line, starting with `@`. A plain line without `@` is dialogue.

| Goal | How to write it |
|---|---|
| Change background | `@bg 教室` (image name matches the asset in the library) |
| Play music | `@music bgm_night` |
| Character speaks | `@[林晚] 你还不走？` (square brackets name the speaker, no registration needed) |
| Narration | `@ 晚风很轻。` |
| Branching choice | `@choice:` then an indented `> option text -> label` |
| Variable / condition | `@set 好感 += 1` / `@if 好感 >= 3:` with indented lines below |

The full directive list is in [engine_spec.md](../engine_spec.md) (Chinese); importing assets
is covered by the [asset import guide](../素材导入指南.md) (Chinese).

## 4. What the phone cannot do

The phone parser does not implement `@voice`, `@anim`, `@fg`, `@cg`, `@camera`, `@transition`,
`@plug`, or `@include`. Using one raises a clear error with the line number — it is not silently
dropped. Voice / animation / foreground / CG / camera / transition / plugins, multi-file scripts,
APK builds and tests all go through the desktop route. The full boundary is in the
[phone authoring guide](../手机端编游戏.md) (Chinese).

## 5. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Red text or placeholder blocks in the preview | The script references a missing asset: check the asset name and letter case |
| Exported file is very large | Assets inline as base64 (~+37%); warnings start at 40 MB, and past 80 MB a low-end device will likely white-screen. Shrink images or split chapters first |
| You want to keep editing on desktop / build an APK | See the [packaging guide](../打包使用指南.md) (Chinese) |

## 6. Where to go next

- [Phone authoring guide](../手机端编游戏.md) — exactly what the phone route can and cannot do
- [engine_spec.md](../engine_spec.md) — full directive set and syntax details (Chinese)
- [Packaging guide](../打包使用指南.md) — the three exits: single-file HTML, APK, Windows folder build
