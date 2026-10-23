# NCT Bus Departures — LEDMatrix plugin

A third-party plugin for ChuckBuilds/LEDMatrix that shows upcoming Nottingham City Transport departures.

## Privacy-friendly defaults

This repository intentionally contains **no personal stop ID, stop name, or route**.

After installing the plugin, enter your own details in the LEDMatrix plugin settings:

- **Stop ID:** `YOUR_STOP_ID`
- **Stop name:** `Bus Stop`
- **Route filter:** blank (shows all routes)
- **Refresh interval:** 30 seconds
- **Maximum departures:** 3
- **Display duration:** 15 seconds

The plugin is tuned for a **128×32** LED matrix.

## Display

The screen shows up to three departures. Live countdowns are shown separately from scheduled clock times.

## Install

1. Create a public GitHub repository, for example `ledmatrix-nct-bus`.
2. Put all files from this folder at the repository root.
3. In LEDMatrix open **Plugin Manager → Install from GitHub**.
4. Paste the repository URL and install.
5. Open the plugin settings and enter your stop ID, optional stop name, and optional route filter.

The plugin reads the public NCT stop page using the configured stop ID.

## Files

- `manifest.json` — LEDMatrix plugin metadata
- `manager.py` — fetch, parse, cache, and 128×32 rendering
- `config_schema.json` — plugin settings
- `requirements.txt` — BeautifulSoup dependency

## Privacy note

Do not put your personal stop ID or descriptive stop name into this public repository. Configure them through the LEDMatrix web interface after installation.

## Reliability

The NCT website is a third-party dependency and its HTML can change. The parser uses multiple text-based fallbacks rather than relying on a single CSS class.

If no departures are available, the panel shows `NO BUSES`. On a fetch/parser error it shows `DATA ERROR` if no previous successful data is available.

## License

This starter plugin is provided for modification and use with LEDMatrix.
