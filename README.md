# assetto-corsa-mcp

An [MCP](https://modelcontextprotocol.io) server plus a small Custom Shaders Patch (CSP) Lua app that let an MCP client
(Claude Code, Claude Desktop, or any other MCP client) control **Assetto Corsa**: start an offline practice session,
fly a free camera to exact world coordinates, set the time of day and the date, take screenshots, read the camera and
car state, and quit again. Every config file it changes is backed up first and restored afterwards.

It was written to check track and building work in game ("go to x/y/z at 19:00 on 15 December and take a picture"),
but the tools are generic and work on any track.

```
MCP client  --stdio-->  ac_mcp.server (Python)  --JSON files-->  claude_bridge (CSP Lua app inside AC)
                              |                                         |
                              +-- writes race.ini, starts acs.exe        +-- camera, time, screenshots, state
```

## Requirements

- Windows, Assetto Corsa (Steam, app 244210).
- Custom Shaders Patch with Lua apps. Tested with **CSP 0.3.0-preview581 (build 4116)**. The app only uses functions
  present in that SDK (`extension/internal/lua-sdk/ac_apps/lib.lua`). Older 0.2.x builds may lack some of them
  (`ac.setWeatherExactUTC0Timestamp`, `ac.makeScreenshot` with a path, `ac.grabCamera`), so they are untested.
- Python 3.10 or newer (tested with 3.13) and the `mcp` package (tested with mcp 2.3.0; the 1.x `FastMCP` import is
  used as a fallback).
- Content Manager is **not** required. `ac_launch` writes `race.ini` itself and starts `acs.exe` directly; Steam
  must be running.

## Install

```powershell
git clone <this repo> assetto-corsa-mcp
cd assetto-corsa-mcp
py -3 -m venv .venv
.venv\Scripts\python -m pip install -e .
powershell -ExecutionPolicy Bypass -File scripts\install_lua_app.ps1
```

The last step copies `lua/claude_bridge/` to `<AC>\apps\lua\claude_bridge\`. Run it again after updating the
repository. CSP reloads the app on file change, so this also works while AC is running.

## Configuration

| what | how |
|---|---|
| AC game folder | `AC_ROOT` environment variable, else auto-detected from Steam (registry `SteamPath` plus `steamapps\libraryfolders.vdf`) |
| `Documents\Assetto Corsa` | `AC_DOCUMENTS` environment variable, else the Windows Documents folder |
| install script | `-AcRoot <path>`, else `AC_ROOT`, else Steam detection |

The bridge exchanges files in `Documents\Assetto Corsa\claude_bridge\`:

- `cmd.json`: the command
- `result.json`: the answer
- `status.json`: a heartbeat, written about once per second while a session runs
- `backups\`: config backups plus `pending_restore.json`

## MCP client setup

**Claude Code**, from your project folder:

```powershell
claude mcp add assetto-corsa -- "C:\path\to\assetto-corsa-mcp\.venv\Scripts\python.exe" -m ac_mcp.server
```

or add it to the project's `.mcp.json`:

```json
{
  "mcpServers": {
    "assetto-corsa": {
      "type": "stdio",
      "command": "C:\\path\\to\\assetto-corsa-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "ac_mcp.server"],
      "env": {}
    }
  }
}
```

**Claude Desktop**: add the same `mcpServers` entry (without `"type"`) to `%APPDATA%\Claude\claude_desktop_config.json`
and restart Claude Desktop. Restart Claude Code or start a new session after changing `.mcp.json`.

## Tools

| tool | arguments | what it does |
|---|---|---|
| `ac_launch` | `track`, `car="abarth500"`, `layout=""`, `skin=""`, `hour=13`, `window_width=0`, `window_height=0`, `start_session=true`, `timeout=240` | Backs up `race.ini` and writes an offline practice session. With a window size, it also backs up `video.ini` and switches to a single windowed screen. Starts `acs.exe`, waits for the bridge heartbeat, then presses Drive. |
| `ac_status` | | Reports whether `acs.exe` is running, whether the bridge is alive (session loaded), the last heartbeat, and any pending config restores. |
| `ac_get_state` | | Live state: camera mode, position, look direction and FOV; car position and speed; time, timestamp and day of year; fps. |
| `ac_camera_free` | `x, y, z`, `yaw=0`, `pitch=0`, `fov=0` | Holds the camera at a world position (`ac.grabCamera`). |
| `ac_camera_look_at` | `pos[3]`, `target[3]`, `fov=0` | Holds the camera at `pos`, looking at `target`. |
| `ac_camera_mode` | `mode` | Releases the camera and switches mode: `free` (F7), `cockpit`, `chase`, `chase2`, `bonnet`, `car` (F6), `track`, or `release`. |
| `ac_set_time` | `hour`, `minute=0`, `day=0`, `month=0`, `year=0`, `freeze=true` | Sets the track-local time and date with `ac.setWeatherExactUTC0Timestamp` (offline only); 0 keeps the current date. |
| `ac_screenshot` | `path`, `hide_apps=true` | Saves via `ac.makeScreenshot` (PNG, JPG or BMP by extension). Falls back to a PowerShell capture of the AC window. |
| `ac_teleport_car` | `x, y, z`, `yaw=-1` | Moves the player car (`physics.setCarPosition`) and reports whether it moved. Works offline. |
| `ac_material_get` | `filter`, `properties` | Reads material values at runtime. `filter` is a CSP mesh filter such as `material:MyMat`. |
| `ac_material_set` | `filter`, `property`, `value[]` | Overrides a material value at runtime only; nothing is written to disk. |
| `ac_track_config` | `pattern`, `values`, `limit` | Returns track CSP config sections as CSP parsed them, with INCLUDEs merged. Use it to check that an included INI was really loaded. |
| `ac_quit` | `restore_configs=true` | Asks AC to shut down through the bridge, uses `taskkill` only if it hangs, then restores the backed-up configs. |
| `ac_restore_configs` | | Restores leftover backups, for example after a crash. Only works while AC is not running. |
| `ac_blender_to_ac` | `x, y, z` | Converts Blender coordinates to AC coordinates. |

The same functions can be used without MCP from Python (`ac_mcp.api`, `ac_mcp.launcher`, `ac_mcp.bridge`); see
`tests/smoke_test.py` and `examples/`.

### Coordinates

- AC world coordinates have **Y up**.
- yaw is in degrees: 0 looks along −Z, 90 along +X, 180 along +Z, 270 along −X.
- pitch is in degrees, positive looks up.
- fov is the vertical field of view in degrees.
- From Blender (FBX/ksEditor export with default axes): **AC x = Blender x, AC y = Blender z, AC z = −Blender y**.
  On a north-up model, yaw 0 looks north.

## Limits

- Offline sessions only. Time, teleport and launch do not work online; the app refuses nothing, but CSP ignores those
  calls online.
- `freeze=true` calls `ac.setWeatherTimeMultiplier(0)`. With some weather controllers (tested: Pure, "static"
  controller) time keeps running at 1×, so set the time right before each batch of shots.
- The track's timezone is measured and corrected automatically: `set_time` reads `sim.timestamp` back and corrects the
  difference. Tracks without coordinates use longitude 0 / UTC, so sunset times are not those of the real place.
- Time changes and loading need a few seconds to settle (lighting conditions have lag). Wait 3 to 6 s before taking a
  screenshot.
- `ac_launch` always starts a one-car practice session in the pits. Content Manager presets, AI and online are not
  supported.
- The PowerShell screenshot fallback needs a windowed or borderless AC window visible on screen.
- Triple-screen setups render three views; use `window_width`/`window_height` for a single-screen session.
- While the bridge holds the camera, or has handled a command in the last 10 s, it shows a small "Claude bridge
  active" label in the top-left corner. The label is hidden during screenshots. Otherwise the app does nothing.

## Troubleshooting

- **Is the bridge alive?** Call `ac_status`. `bridgeAlive` is true when `status.json` is younger than 5 s. The app only
  runs once a session has loaded.
- **CSP log:** `Documents\Assetto Corsa\logs\custom_shaders_patch.log`. Search for `Claude Bridge`: there should be a
  line `Lua: <App: Claude Bridge> loaded and ready to run`. Screenshots show up as `Screenshot requested from Lua API`.
- **Configs not restored** after a crash: call `ac_restore_configs` with AC closed. The originals are also in
  `Documents\Assetto Corsa\claude_bridge\backups\*.orig`.
- **AC exits during loading:** see `Documents\Assetto Corsa\logs\log.txt`. A missing car or track is reported by
  `ac_launch` before it starts AC.
- **Nothing happens on commands:** make sure the app folder is `apps\lua\claude_bridge` and that CSP's Lua apps are
  enabled. The app appears as "Claude Bridge" in the in-game app list.

## Uninstall

1. `powershell -ExecutionPolicy Bypass -File scripts\install_lua_app.ps1 -Uninstall`. This removes
   `<AC>\apps\lua\claude_bridge\`.
2. Delete `Documents\Assetto Corsa\claude_bridge\` (channel files and config backups). Check first that
   `backups\pending_restore.json` does not exist, or run `ac_restore_configs` before deleting.
3. Remove the `assetto-corsa` entry from your `.mcp.json` / `claude_desktop_config.json`, or run
   `claude mcp remove assetto-corsa`.
4. Delete this folder, including `.venv`.

## License

MIT. See [LICENSE](LICENSE).
