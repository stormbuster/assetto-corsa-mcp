--[[
  Claude Bridge: file-based command channel for Assetto Corsa + Custom Shaders Patch.

  Channel folder: Documents/Assetto Corsa/claude_bridge/
    cmd.json     written by the client (atomically): {"id": <int>, "cmd": "<name>", ...args}
    result.json  written here: {"id": <int>, "ok": true|false, "error": "...", ...data}
    status.json  heartbeat, rewritten about once per second while AC runs

  Only CSP Lua API functions present in extension/internal/lua-sdk/ac_apps/lib.lua are used.
  The app does nothing visible until a command arrives; while it holds the camera or worked on a command
  in the last 10 s it draws a small indicator (hidden while a screenshot is taken).
]]

local BRIDGE_VERSION = '0.1.0'
local dir = ac.getFolder(ac.FolderID.ACDocuments) .. '/claude_bridge'
local cmdFile = dir .. '/cmd.json'
local resultFile = dir .. '/result.json'
local statusFile = dir .. '/status.json'

local lastId = -1
local pollTimer = 0
local statusTimer = 0
local pending = nil        -- {id=, step=function(dt) -> result|nil, timeout=}
local grabbed = nil        -- ac.GrabbedCamera
local camTarget = nil      -- {pos=vec3, look=vec3, up=vec3, fov=number}
local lastActivity = -1e9
local hideIndicator = false
local lastError = nil
local commandsDone = 0

-- skip commands that were already in the channel before AC started
do
  local ok, raw = pcall(io.load, cmdFile)
  if ok and raw then
    local ok2, data = pcall(JSON.parse, raw)
    if ok2 and type(data) == 'table' and tonumber(data.id) then lastId = tonumber(data.id) end
  end
end

local function v3(t) return t and vec3(t[1] or t.x or 0, t[2] or t.y or 0, t[3] or t.z or 0) end
local function a3(v) return v and { v.x, v.y, v.z } or nil end

local function writeJson(path, tbl)
  local ok, s = pcall(JSON.stringify, tbl)
  if not ok then s = '{"ok":false,"error":"stringify failed"}' end
  io.save(path, s, true)
end

local function camModeName(m)
  for k, v in pairs(ac.CameraMode) do if v == m then return k end end
  return tostring(m)
end

local function collectState()
  local sim = ac.getSim()
  local car = ac.getCar(0)
  local s = {
    bridgeVersion = BRIDGE_VERSION,
    simTime = sim.time,
    frame = sim.frame,
    fps = sim.fps,
    isPaused = sim.isPaused,
    isInMainMenu = sim.isInMainMenu,
    isSessionStarted = sim.isSessionStarted,
    isLive = sim.isLive,
    isReplayActive = sim.isReplayActive,
    isOnlineRace = sim.isOnlineRace,
    isWindowForeground = sim.isWindowForeground,
    windowWidth = sim.windowWidth,
    windowHeight = sim.windowHeight,
    track = ac.getTrackID(),
    camera = {
      mode = camModeName(sim.cameraMode),
      position = a3(sim.cameraPosition),
      look = a3(sim.cameraLook),
      fov = sim.cameraFOV,
      grabbedByBridge = grabbed ~= nil and grabbed:active() or false,
    },
    time = {
      hours = sim.timeHours, minutes = sim.timeMinutes, seconds = sim.timeSeconds,
      timestampLocal = sim.timestamp, dayOfYear = sim.dayOfYear,
      multiplier = sim.timeMultiplier, postOffset = sim.timePostOffset,
      offsetIgnored = sim.isTimeOffsetIgnored,
    },
    lastError = lastError,
    commandsDone = commandsDone,
    lastCommandId = lastId,
  }
  if car then
    s.car = {
      id = ac.getCarID(0),
      position = a3(car.position), look = a3(car.look),
      speedKmh = car.speedKmh, gear = car.gear,
    }
  end
  return s
end

local function releaseCamera()
  if grabbed then pcall(function() grabbed:dispose() end) end
  grabbed = nil
  camTarget = nil
end

local function applyCamera()
  if not (grabbed and camTarget) then return end
  if not grabbed:active() then grabbed = nil; return end
  grabbed.ownShare = 1
  grabbed.transform.position:set(camTarget.pos)
  grabbed.transform.look:set(camTarget.look)
  grabbed.transform.up:set(camTarget.up)
  if camTarget.fov then grabbed.fov = camTarget.fov end
end

-- waits n frames then calls fn() which returns the result table
local function afterFrames(n, fn)
  local left = n
  return function()
    left = left - 1
    if left <= 0 then return fn() end
    return nil
  end
end

local handlers = {}

handlers.ping = function(c) return { ok = true, pong = true, bridgeVersion = BRIDGE_VERSION } end

handlers.get_state = function(c) local s = collectState(); s.ok = true; return s end

handlers.set_camera_mode = function(c)
  local m = tostring(c.mode or ''):lower()
  if m == 'free' then
    -- keep a grabbed camera if there is one; otherwise switch AC to its own free camera (F7)
    if not grabbed then ac.setCurrentCamera(ac.CameraMode.Free) end
  else
    releaseCamera()
    if m == 'cockpit' then ac.setCurrentCamera(ac.CameraMode.Cockpit)
    elseif m == 'chase' then ac.setCurrentCamera(ac.CameraMode.Drivable); ac.setCurrentDrivableCamera(ac.DrivableCamera.Chase)
    elseif m == 'chase2' then ac.setCurrentCamera(ac.CameraMode.Drivable); ac.setCurrentDrivableCamera(ac.DrivableCamera.Chase2)
    elseif m == 'bonnet' then ac.setCurrentCamera(ac.CameraMode.Drivable); ac.setCurrentDrivableCamera(ac.DrivableCamera.Bonnet)
    elseif m == 'car' then ac.setCurrentCamera(ac.CameraMode.Car)
    elseif m == 'track' then ac.setCurrentCamera(ac.CameraMode.Track)
    elseif m == 'release' then -- only release the grab
    else return { ok = false, error = 'unknown mode: ' .. m } end
  end
  return afterFrames(3, function() return { ok = true, camera = collectState().camera } end)
end

handlers.camera_set = function(c)
  local pos, look = v3(c.position), v3(c.look)
  if c.target then look = v3(c.target) - pos end
  if not pos or not look or look:length() < 1e-6 then return { ok = false, error = 'position and look/target required' } end
  look:normalize()
  local up = v3(c.up) or vec3(0, 1, 0)
  camTarget = { pos = pos, look = look, up = up, fov = tonumber(c.fov) }
  if not (grabbed and grabbed:active()) then
    local g, err = ac.grabCamera('claude_bridge remote camera')
    if not g then
      -- fallback: AC free camera plus the simple setters
      camTarget = nil
      ac.setCurrentCamera(ac.CameraMode.Free)
      ac.setCameraPosition(pos)
      ac.setCameraDirection(look, up)
      if c.fov then ac.setCameraFOV(tonumber(c.fov)) end
      return afterFrames(3, function()
        return { ok = true, method = 'setCameraPosition', grabError = err, camera = collectState().camera }
      end)
    end
    grabbed = g
  end
  applyCamera()
  return afterFrames(3, function() return { ok = true, method = 'grabCamera', camera = collectState().camera } end)
end

handlers.camera_release = function(c)
  releaseCamera()
  return { ok = true }
end

handlers.set_time_offset = function(c)
  local ok = ac.setWeatherTimeOffset(tonumber(c.offset) or 0, c.instant ~= false)
  return afterFrames(4, function() return { ok = ok, time = collectState().time } end)
end

handlers.set_time_multiplier = function(c)
  ac.setWeatherTimeMultiplier(tonumber(c.multiplier) or 1)
  return { ok = true }
end

handlers.screenshot = function(c)
  local path = c.path
  if not path or path == '' then
    path = ac.getFolder(ac.FolderID.Screenshots) .. '/claude_bridge_' .. os.date('%Y%m%d_%H%M%S') .. '.png'
  end
  local fmt = ac.ScreenshotFormat.PNG
  local lower = path:lower()
  if lower:match('%.jpe?g$') then fmt = ac.ScreenshotFormat.JPG elseif lower:match('%.bmp$') then fmt = ac.ScreenshotFormat.BMP end
  local hideApps = c.hide_apps ~= false
  hideIndicator = true
  if hideApps then ac.setAppsHidden(true) end
  local frames, started, done, err = 3, false, false, nil
  local t0 = os.clock()
  return function()
    if not started then
      frames = frames - 1
      if frames > 0 then return nil end
      started = true
      ac.makeScreenshot(path, { format = fmt }, function(e) err = e; done = true end)
      return nil
    end
    if not done then return nil end
    if hideApps and c.restore_apps ~= false then ac.setAppsHidden(false) end
    hideIndicator = false
    return { ok = err == nil, error = err, path = path, seconds = os.clock() - t0 }
  end
end

handlers.set_apps_hidden = function(c) ac.setAppsHidden(c.hidden ~= false); return { ok = true } end

handlers.pause = function(c) return { ok = ac.tryToPause(c.active ~= false) } end

handlers.start_session = function(c) return { ok = ac.tryToStart(c.instant ~= false) } end

handlers.teleport_car = function(c)
  local pos = v3(c.position)
  if not pos then return { ok = false, error = 'position required' } end
  local before = ac.getCar(0).position:clone()
  local okCall, e = pcall(physics.setCarPosition, 0, pos, c.direction and v3(c.direction) or nil)
  if not okCall then return { ok = false, error = 'physics.setCarPosition failed: ' .. tostring(e) } end
  return afterFrames(10, function()
    local now = ac.getCar(0).position
    local moved = now:distance(pos) < 5
    return { ok = moved, before = a3(before), after = a3(now),
      error = (not moved) and 'car did not move to the requested position (call may be ignored in this mode)' or nil }
  end)
end

local function plain(v)
  if type(v) == 'number' or type(v) == 'string' or type(v) == 'boolean' or v == nil then return v end
  if vec4.isvec4 and vec4.isvec4(v) then return { v.x, v.y, v.z, v.w } end
  if vec3.isvec3 and vec3.isvec3(v) then return { v.x, v.y, v.z } end
  if vec2.isvec2 and vec2.isvec2(v) then return { v.x, v.y } end
  local ok, t = pcall(function() return { v.x, v.y, v.z, v.w } end)
  return ok and t or tostring(v)
end

-- Track CSP config as parsed by CSP (includes merged): list sections whose name matches a Lua pattern, optionally with values
handlers.track_config = function(c)
  local cfg = ac.INIConfig.trackConfig()
  local pat = c.pattern or '.'
  local out, n = {}, 0
  for name, sec in pairs(cfg.sections) do
    if name:match(pat) then
      n = n + 1
      if n <= (tonumber(c.limit) or 200) then out[name] = c.values ~= false and sec or true end
    end
  end
  return { ok = true, matched = n, sections = out }
end

-- Runtime-only material inspection (nothing is written to disk)
handlers.material_get = function(c)
  local m = ac.findMeshes(c.filter or '')
  local res = { ok = true, meshes = m:size(), values = {} }
  for _, p in ipairs(c.properties or { 'ksEmissive', 'ksAmbient', 'ksDiffuse', 'ksAlphaRef' }) do
    res.values[p] = plain(m:getMaterialPropertyValue(1, p))
  end
  return res
end

-- Runtime-only material override for diagnostics; lasts until AC restarts (or CSP re-applies its config each frame)
handlers.material_set = function(c)
  local m = ac.findMeshes(c.filter or '')
  local v = c.value
  if type(v) == 'table' then v = (#v == 4 and vec4(v[1], v[2], v[3], v[4])) or (#v == 3 and vec3(v[1], v[2], v[3])) or (#v == 2 and vec2(v[1], v[2])) or v[1] end
  m:setMaterialProperty(c.property, v)
  return afterFrames(2, function()
    return { ok = true, meshes = m:size(), now = plain(m:getMaterialPropertyValue(1, c.property)) }
  end)
end

handlers.quit = function(c)
  releaseCamera()
  writeJson(resultFile, { id = c.id, ok = true, quitting = true })
  ac.shutdownAssettoCorsa()
  return { ok = true, quitting = true }
end

-- c.local_epoch: wall-clock seconds since 1970 in the track's local time (what sim.timestamp reports).
-- The SDK call takes a UTC0 timestamp; the track timezone offset is measured and corrected in up to 3 tries.
handlers.set_time = function(c)
  local target = tonumber(c.local_epoch)
  if not target then return { ok = false, error = 'local_epoch required' } end
  if c.multiplier ~= nil then ac.setWeatherTimeMultiplier(tonumber(c.multiplier)) end
  local sent = target
  local okCall = ac.setWeatherExactUTC0Timestamp(sent, true)
  local wait, tries = 8, 0
  return function()
    wait = wait - 1
    if wait > 0 then return nil end
    local delta = ac.getSim().timestamp - target
    if math.abs(delta) > 90 and tries < 3 then
      tries = tries + 1
      sent = sent - delta
      okCall = ac.setWeatherExactUTC0Timestamp(sent, true)
      wait = 8
      return nil
    end
    return { ok = math.abs(delta) <= 90, callOk = okCall, deltaSeconds = delta, sentUTC0 = sent, tries = tries,
      time = collectState().time }
  end
end

local function finish(id, res)
  res = res or { ok = false, error = 'no result' }
  res.id = id
  commandsDone = commandsDone + 1
  if res.ok == false then lastError = res.error end
  writeJson(resultFile, res)
end

local function poll()
  local raw = io.load(cmdFile)
  if not raw or raw == '' then return end
  local ok, c = pcall(JSON.parse, raw)
  if not ok or type(c) ~= 'table' then return end
  local id = tonumber(c.id)
  if not id or id == lastId then return end
  lastId = id
  lastActivity = os.clock()
  local h = handlers[tostring(c.cmd)]
  if not h then finish(id, { ok = false, error = 'unknown command: ' .. tostring(c.cmd) }); return end
  local okRun, r = pcall(h, c)
  if not okRun then finish(id, { ok = false, error = 'lua error: ' .. tostring(r) }); return end
  if type(r) == 'function' then
    pending = { id = id, step = r, deadline = os.clock() + (tonumber(c.timeout) or 30) }
  else
    finish(id, r)
  end
end

function script.update(dt)
  applyCamera()
  if pending then
    lastActivity = os.clock()
    local okRun, r = pcall(pending.step, dt)
    if not okRun then finish(pending.id, { ok = false, error = 'lua error: ' .. tostring(r) }); pending = nil
    elseif r then finish(pending.id, r); pending = nil
    elseif os.clock() > pending.deadline then finish(pending.id, { ok = false, error = 'timeout in bridge' }); pending = nil; hideIndicator = false end
  else
    pollTimer = pollTimer + dt
    if pollTimer > 0.15 then pollTimer = 0; pcall(poll) end
  end
  statusTimer = statusTimer + dt
  if statusTimer > 1 then
    statusTimer = 0
    pcall(function() local s = collectState(); s.wallClock = os.time(); writeJson(statusFile, s) end)
  end
end

local function isActive()
  return (grabbed ~= nil) or pending ~= nil or (os.clock() - lastActivity < 10)
end

function script.fullscreenUI()
  if hideIndicator or not isActive() then return end
  local text = 'Claude bridge active' .. (grabbed and ' | camera held' or '') .. ' | cmd #' .. tostring(lastId)
  ui.drawRectFilled(vec2(8, 8), vec2(16 + ui.measureText(text).x, 30), rgbm(0, 0, 0, 0.55))
  ui.drawText(text, vec2(12, 11), rgbm(1, 0.85, 0.2, 1))
end

function windowMain(dt)
  ui.text('Claude Bridge ' .. BRIDGE_VERSION)
  ui.text('Channel: ' .. dir)
  ui.text('Last command id: ' .. tostring(lastId) .. ', done: ' .. commandsDone)
  ui.text('Camera held: ' .. tostring(grabbed ~= nil))
  if lastError then ui.text('Last error: ' .. tostring(lastError)) end
  if grabbed and ui.button('Release camera') then releaseCamera() end
end

-- make sure the channel folder exists (io.createDir exists in the SDK)
pcall(io.createDir, dir)
