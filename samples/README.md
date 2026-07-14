# Samples — first generation in 5 minutes

No custom assets required: this sample library maps everything to UE's built-in
`/Engine/BasicShapes/` meshes, so a fresh project can generate immediately.
Scenes will be made of simple shapes — swap in your own characters and props
later (see "Bring your own assets" below).

## Quick start

1. Copy the sample library into your project:

   ```
   YourProject/Content/StoryboardTo3D/asset_library.json
   ```

   (create the `StoryboardTo3D` folder, copy `asset_library.sample.json` there,
   and rename it to `asset_library.json`)

2. Launch the plugin: **Window → StoryboardTo3D** (or the toolbar button).

3. Create a Show and an Episode, then **Import Panels** and pick
   `sample_panel_01.png` and `sample_panel_02.png` from this folder.

4. Select a panel → **Analyze Panel** (needs an API key configured in
   Settings, or a local LLaVA via Ollama) → **Generate**.

You should see placeholder shapes placed in your level to match the sketch
layout, plus a camera. That's the whole loop: sketch → analysis → placed scene.

## Bring your own assets

Edit `Content/StoryboardTo3D/asset_library.json` in your project and point
entries at your own assets:

```json
"characters": {
  "Hero": {
    "asset_path": "/Game/Characters/BP_Hero",
    "description": "Tall knight in blue armor",
    "aliases": ["knight", "hero", "warrior"]
  }
}
```

- `asset_path` — any Blueprint, Static Mesh, or Skeletal Mesh in your project
- `description` — what the AI reads to match sketch content to the asset
- `aliases` — extra names the AI might use for the same thing

The richer the descriptions, the better the AI matches your sketch.
