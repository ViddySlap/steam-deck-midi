# Engines config directory

Each `*.json` file in this directory defines one engine instance. The file's
`"type"` field is the engine type (matched against `_ENGINE_TYPES` in
`windows/engines/registry.py`); the filename is purely organizational.

## Layout

```
config/
  engines/                    <- you are here. User-owned. Installer never overwrites.
    audio_opacity.json
    osc_sync.json
    autopilot.json
    <your_custom_engine>.json
  engines.factory/            <- factory defaults, always overwritten by installer.
    audio_opacity.json
    osc_sync.json
    autopilot.json
```

## Rules the loader enforces

- One engine per `type`. If two files declare the same `type`, the loader
  warns and keeps the alphabetically-first file.
- A file with `"enabled": false` is parsed but the engine is not instantiated.
- For each engine `type` present in `engines.factory/` but not in `engines/`,
  the loader merges the factory stanza in memory only (your dir is never
  modified). This is how new engine types ship to existing installs without
  clobbering your customizations to engines you've already configured.
- Disabling a factory engine: keep the file in `engines/` and set
  `"enabled": false`. Don't delete the file, or factory-merge will re-add it.

## Adding a custom engine

1. Implement the engine class (see `windows/engines/audio_opacity.py` as a
   template) and register it in `_ENGINE_TYPES` in
   `windows/engines/registry.py`.
2. Drop a `<your_type>.json` file in this directory with at least
   `{"name": "...", "type": "<your_type>", "enabled": true, ...}`.
3. Restart the receiver.

## Migration from v0.3.x single-file `engines.json`

If you upgrade from a v0.3.x install that used the single-file
`config/engines.json` array, the loader auto-splits it into per-file configs
on first run and renames the legacy file to `engines.json.migrated`. No
manual intervention required.
