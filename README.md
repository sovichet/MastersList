# MastersList

A Glyphs 3 plugin that puts the font's masters in a floating panel, so you can
see and switch between them without the master dropdown, and see at a glance
which ones are interpolation-compatible with the layer you're drawing.


## What it does

- Lists every master in the current font with its axis coordinates (`wght 400, wdth 100`).
- Click a row to make that master the active one in the edit view.
- Shows, per master, whether the current glyph's layer is interpolation-compatible
  with the active layer:
  - 🔘 the active master
  - 🟢 compatible with the active layer
  - 🔴 incompatible
  - — no layer, or no glyph open
- **← / →** step to the previous/next master in list order. The 🪜 field sets
  the step size, so `4` on a 4-weight × 3-width family jumps across widths.
- The popup groups the list by any axis, with a header row per axis value.

The panel follows the frontmost font and updates as you edit.

## Install

Requires Glyphs 3 and the `vanilla` module (Glyphs: *Window > Plugin Manager >
Modules > vanilla*).

Double-click `MasterList.glyphsPlugin`, or copy it into
`~/Library/Application Support/Glyphs 3/Plugins/`, then restart Glyphs.

Open it from **Window > Masters List**. The menu item toggles the panel.

## License

Copyright 2026 Sovichet Tep (@sovichet).

Apache 2.0 — see [LICENSE](LICENSE).
