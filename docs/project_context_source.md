# MOFONGO32 Engine Project Context

Generated: 2026-03-27

## 1. Executive summary

MOFONGO32 is an ESP32-based 2D game engine and toolchain built around a custom bytecode/game format called MASA. The project is no longer a single Arduino sketch; it is a full authoring pipeline with:

- a Python GUI editor for objects, rooms, tilemaps and scripts
- an export pipeline from `.ingr` project files to `.masa` runtime packages
- a dual-ESP32 runtime architecture (logic/master + video/slave)
- an interpreter/runtime for object logic, collisions, signals, HUD, audio and rooms
- SPIFFS-based game deployment to the logic ESP32
- helper tools for sprites, backgrounds, rooms, music conversion and `.masa` size analysis

The codebase is already capable of running a complete game such as Asteroids, but it is still operating close to the hardware limits of the ESP32. The most important constraints today are RAM pressure, fixed-size runtime pools, exporter/runtime alignment, and gameplay edge cases that appear when object fanout becomes high.

## 2. High-level architecture

### 2.1 Hardware architecture

The intended deployment is a dual-ESP32 setup:

- Logic ESP32 (master):
  - runs the MASA runtime
  - reads `game.masa` from SPIFFS
  - handles gameplay state, collisions, alarms, input and audio control
  - sends render state/commands over SPI
- Video ESP32 (slave):
  - renders composite NTSC video
  - receives frame/render packets from the logic board

The current guide for flashing and role selection lives in `README.md`. The main compile-time switches live in `AudioVideoExample.ino`.

### 2.2 Software architecture

The project is split into these major layers:

- Authoring layer:
  - Python GUI tools in `tools/`
  - project editing, room editing, asset packaging, music conversion
- Packaging layer:
  - export from `.ingr` to `.masa`
  - optional generated headers in `generated/`
- Runtime layer:
  - `MasaLoader` loads the MASA package
  - `MasaRuntime` interprets bytecode and produces render/audio commands
  - the main sketch integrates runtime + input + transport + video + SPIFFS
- Presentation layer:
  - composite video rendering
  - sprite/background/tilemap drawing
  - HUD, text and shape overlays
- Audio layer:
  - song playback via `songs.h`
  - procedural beeps/waves for gameplay SFX

## 3. Core source files

### 3.1 Main runtime and integration

- `AudioVideoExample.ino`
  - main sketch
  - dual-ESP role configuration
  - SPIFFS init
  - MASA load/reset
  - frame loop
  - transport/video/audio integration

- `MasaRuntime.h`
  - runtime public API
  - fixed-size runtime constants
  - render command queue definitions
  - object state definition

- `MasaRuntime.cpp`
  - MASA opcode interpreter
  - object simulation
  - signals/collisions
  - HUD/text/shape systems
  - alarms, variables, strings
  - spawn/destroy logic
  - room behavior

- `MasaLoader.h` / `MasaLoader.cpp`
  - load `.masa` from SPIFFS
  - parse header
  - expose script and room data
  - dynamic allocation path for lower static RAM pressure

- `MasaFormat.h`
  - MASA header layout
  - bytecode opcode IDs

### 3.2 Runtime support modules

- `AudioApi.cpp` / `AudioApi.h`
  - song playback
  - square/triangle/noise style beeps
  - 1ch / 4ch song support depending on `songs.h`

- `Graphics.cpp` / `Graphics.h`
  - framebuffer and draw helpers

- `BackgroundApi.cpp` / `BackgroundApi.h`
  - background/tilemap-related helpers

- `DualEspLink.cpp` / `DualEspLink.h`
  - SPI transport between logic and video ESP32s

- `MasaSpiLink.cpp` / `MasaSpiLink.h`
  - MASA render packet link utilities

- `WebInput.cpp` / `WebInput.h`
  - optional web-based input path

### 3.3 Main authoring tools

- `tools/game_engine_gui.py`
  - main editor
  - object/room/tilemap editing
  - script editor + MASA directives
  - `.ingr` import/export
  - `.masa` export
  - quota reporting and auto-trim

- `tools/masa_size_viewer_gui.py`
  - analyzes `.masa`
  - shows ROM usage
  - estimates runtime RAM impact
  - can compare against `.map` real DRAM usage

- `tools/mofongo_emulator.py`
  - emulator for testing content without flashing hardware

- `tools/spiffs_builder_gui.py`
  - SPIFFS image builder/flashing helper

- `tools/famitracker_to_song_atlas.py`
  - converts FamiTracker text export into `songs.h` atlas data

## 4. Main content and data formats

### 4.1 `.ingr`

`.ingr` is the editable project format used by the Python editor. It represents:

- project metadata
- objects and their properties
- room data and room instances
- script text
- asset references

The editor also uses `ingr_cache/` to unpack/import and cache asset bundles associated with projects.

### 4.2 `.masa`

`.masa` is the deployable runtime package used by the logic ESP32. It contains:

- MASA header
- bytecode script block
- optional sprite/tilemap/room sections depending on export path

The runtime loads the file from SPIFFS, typically as `/game.masa`.

### 4.3 Generated headers

`generated/` can contain generated C/C++ headers used by the sketch when compiling with header-based content instead of (or in addition to) SPIFFS runtime loading.

### 4.4 Audio content

Song data is embedded through `gfx/songs.h`. The pipeline is:

- compose in FamiTracker
- export as text
- convert with `tools/famitracker_to_song_atlas.py`
- include resulting atlas in the project

## 5. MASA runtime model

The MASA runtime is conceptually object-centric and signal-driven.

### 5.1 Objects

Each runtime object has:

- position
- sprite
- active flag
- movement state
- collision/hitbox state
- optional animation state
- optional input behavior
- per-object alarms and vars

Objects are stored in fixed-size arrays controlled by `kMaxObjects`.

### 5.2 Signals

Signals are shared slots used to drive actions. A signal can come from:

- input bind
- collision
- alarm ring
- music signal
- HUD/game over logic
- choice selection

Signal actions include:

- destroy
- destroy other
- spawn
- spawn bullet
- stop
- room goto/next
- text operations
- HUD add
- beeps and wave beeps

### 5.3 Rooms

Rooms define:

- placed object instances
- background and color
- optional tilemap
- optional song hash

The runtime can switch rooms and also uses room data to avoid enabling every exported object at once.

### 5.4 HUD/Text/Shapes

The runtime can draw:

- sprite commands
- text slots
- shape slots
- HUD text with token replacement
- textbox/choice UI
- game over UI flows

## 6. Current runtime limits

As of the current code in `MasaRuntime.h`, the main fixed limits are:

- `kMaxObjects = 48`
- `kMaxCommands = 24`
- `kMaxTextSlots = 5`
- `kMaxTextLen = 30`
- `kMaxShapeSlots = 8`
- `kMaxSignals = 20`
- `kMaxColliders = 34`
- `kMaxSignalActions = 48`
- `kMaxTextBoxes = 1`
- `kMaxTextBoxLen = 40`
- `kMaxChoiceSlots = 1`
- `kMaxChoiceItems = 4`
- `kMaxChoiceLen = 10`
- `kMaxInputBinds = 14`
- `kMaxAlarms = 6`

These limits are central to the current design. Many of the gameplay bugs observed recently are not logic parser bugs in isolation; they are runtime pressure bugs that appear when these pools are saturated or when exporter assumptions and runtime fallback rules disagree.

## 7. Export pipeline behavior

The export logic in `tools/game_engine_gui.py` is not a trivial object dump. It currently does all of the following:

- normalizes object definitions vs room instances
- resolves reachable prototypes from the active room through script references
- auto-creates spawn pools / clone pools for objects referenced by `MASA_ON_SIGNAL_SPAWN`
- aligns export limits with runtime constants from `MasaRuntime.h`
- estimates:
  - object count
  - used signal slots
  - colliders
  - signal actions
  - input binds
  - alarms
- emits a quota table at export time
- auto-trims lower-priority beep actions if `signalActions` would exceed runtime max

This export layer is now effectively part of the engine runtime contract. The project depends heavily on exporter/runtime consistency.

## 8. Audio system status

The audio system is already more advanced than a simple tone player.

Current capabilities:

- playback of imported song data from `songs.h`
- optional 4-channel mode
- channel wave mapping for pulse/triangle/noise style behavior
- gameplay SFX through `beep_hz`, `beep_wave_hz`, `beep_note`, etc.
- MASA-level beeps and signal beeps

Important caveats:

- audio timing and gameplay can interact if serial logging/debug output is enabled
- multiple simultaneous effects still compete for limited CPU and timing margin
- the FamiTracker conversion path is important to the workflow and should be documented clearly

## 9. Known technical constraints and pain points

### 9.1 RAM pressure

This is the single biggest technical constraint in the project.

Important facts:

- the ESP32 DRAM budget is heavily consumed by runtime arrays
- the project already moved significant MASA data from static allocation to heap-backed loading
- `.map` calibration is now part of the workflow because rough estimates were not sufficient
- runtime pool constants directly change memory usage and behavior

Consequence:

- increasing limits can fix gameplay edge cases but also causes compile/link failures or runtime memory pressure

### 9.2 Fixed-size pool behavior

The runtime uses fixed-size pools for:

- objects
- colliders
- signal actions
- text/shape/HUD subsystems
- input binds
- alarms

Consequence:

- gameplay bugs often appear only under load
- common symptoms are:
  - `SPAWN FAILED`
  - split chains not completing
  - objects becoming effectively invulnerable
  - signal actions being trimmed or dropped

### 9.3 Exporter/runtime coupling

The project depends on careful coupling between:

- how the exporter chooses owners/clones/pools
- how the runtime picks spawn fallbacks and destroy behavior

Consequence:

- a fix in export can create a new issue in runtime and vice versa

### 9.4 Debug logging cost

The runtime contains heavy debug logging in critical gameplay paths.

Consequence:

- if enabled, serial output can visibly reduce FPS and distort gameplay timing
- performance tests should be done with runtime debug disabled

### 9.5 Generic engine vs Asteroids-specific tuning

The project goal is a general-purpose engine, not an Asteroids-only runtime.

Consequence:

- pool sizing, fallback logic, signal behavior and API design should avoid hardcoding game-specific names or assumptions
- where heuristics are needed, they should be generic and based on usage/fanout rather than object names

## 10. Current gameplay-specific stress case: Asteroids

Asteroids has become the current real-world stress test for the engine. It exposes:

- object fanout (big -> middle -> small)
- multiple concurrent spawns
- short-lived bullets and explosions
- HUD + score/lives + game over overlays
- simultaneous movement, collisions, audio and room persistence

The recent debugging history strongly suggests Asteroids is serving as:

- a useful integration test
- a detector for pool exhaustion and fallback policy bugs
- a benchmark for whether the engine remains generic under pressure

## 11. Tooling strengths

The project already has several strong documentation/tooling foundations:

- GUI-based editor instead of raw JSON-only workflow
- import/export project cache structure
- emulator for iteration without hardware
- `.masa` size/RAM viewer with ROM chip and RAM chip visualization
- `.map` calibration support
- SPIFFS tooling integrated into workflow
- music conversion tooling

These tools are a major asset and should be highlighted prominently in future documentation.

## 12. Main documentation gaps to fill

A complete formal documentation set should eventually include:

### 12.1 Product overview

- what MOFONGO32 is
- target hardware
- philosophy of the engine
- what kinds of games it is intended to support

### 12.2 Setup guide

- environment setup
- Arduino IDE/core versions
- logic vs video compile settings
- SPIFFS flashing
- how to run the emulator/tools

### 12.3 Authoring guide

- how objects work
- room workflow
- tilemaps
- sprite/background asset pipeline
- `.ingr` packaging and import/export

### 12.4 MASA language/API reference

- every directive
- parameters
- examples
- caveats and runtime limits

### 12.5 Runtime internals

- opcode execution model
- command queue
- signals/collisions
- rooms
- alarms
- HUD/text
- audio

### 12.6 Limits and performance guide

- meaning of each `kMax*`
- RAM impact
- what to tune first
- how to use `.map` and the size viewer
- common failure signatures and what they mean

### 12.7 Debugging guide

- how to interpret runtime logs
- how to diagnose `SPAWN FAILED`
- how to diagnose missing collisions
- when exporter quotas are the real issue

## 13. Recommended near-term engineering priorities

Based on the current state of the codebase, the best short-term technical priorities are:

- document the MASA API formally
- document runtime limits and how they affect gameplay
- keep debug logging off by default
- improve generic pool sizing and/or split policies
- reduce accidental coupling between exporter heuristics and one specific game
- keep the RAM viewer and `.map` calibration workflow in active use

## 14. Bottom-line assessment

MOFONGO32 is already a serious custom engine/toolchain with:

- a distinct runtime format
- a usable editor
- real content pipeline
- dual-ESP deployment
- a growing script API
- practical performance instrumentation

The project is not blocked by lack of features. Its current stage is dominated by:

- stabilization
- documentation
- memory-aware runtime design
- keeping the engine generic while still supporting demanding games

That is exactly the right moment to invest in formal project documentation.

