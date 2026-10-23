# LEDMatrix Flip Clock

Animated split-flap style clock plugin for [ChuckBuilds/LEDMatrix](https://github.com/ChuckBuilds/LEDMatrix), designed around a **128x32** RGB LED matrix.

## Layout

- **Left:** large `HH:MM` clock
- **Right:** minimal date rail: weekday, day/month, year
- **Minute/hour rollover:** only the digits that change perform a short split-flap animation
- Uses the Raspberry Pi's local system time, so timezone/DST follow the host configuration

Example layout:

```text
┌──────────────────────────────┬──────────────┐
│          23:59               │     SAT      │
│                              │    24 OCT    │
│                              │     2026     │
└──────────────────────────────┴──────────────┘
```

## Configuration

| Setting | Default | Description |
| --- | --- | --- |
| `use_24_hour` | `true` | 24-hour or 12-hour time |
| `show_weekday` | `true` | Show weekday on the top date row |
| `date_uppercase` | `true` | Uppercase weekday/month text |
| `animation_ms` | `420` | Total flip duration |
| `animation_frames` | `7` | Frames used for each flip |
| `display_duration` | `60` | Rotation duration in seconds |

## Development install from this branch

This plugin currently lives under `plugins/flip-clock/` on the `feature/flip-clock-plugin` branch. Clone the repository and link that directory into LEDMatrix:

```bash
git clone -b feature/flip-clock-plugin https://github.com/jakejayeden/ledmatrix-nct-bus.git
cd LEDMatrix
./scripts/dev/dev_plugin_setup.sh link flip-clock ../ledmatrix-nct-bus/plugins/flip-clock
```

If your LEDMatrix installation uses the production plugin directory, either copy the folder into `plugin-repos/flip-clock` or set `plugin_system.plugins_directory` to `plugins` while developing.

## Notes

- No network connection or API key is required.
- Pillow is already part of LEDMatrix's rendering stack; this plugin adds no extra Python dependency.
- The layout reads the active display width/height dynamically, but 128x32 is the intended design target.
- The animation is intentionally short so it remains responsive within LEDMatrix's plugin display execution path.

## Future packaging

The clean final home is a standalone `ledmatrix-flip-clock` repository or a plugin directory in a fork of `ChuckBuilds/ledmatrix-plugins`. The source here is already structured as a standard LEDMatrix plugin (`manifest.json`, `config_schema.json`, `manager.py`).
