# MOFONGO32 Flashing Guide (Logic + Video + SPIFFS)

This guide explains how to flash the **Logic ESP32**, **Video ESP32**, and **SPIFFS** for the dual‑ESP setup.

This Project uses the following Repositories
- **https://github.com/bitluni/ESP32CompositeVideo**
- **https://github.com/marciot/ESP32CompositeColorVideo**

## Quick Summary

- **Logic ESP32** (master): runs MASA runtime + Bluetooth input.
- **Video ESP32** (slave): renders composite video (NTSC).
- **SPIFFS**: only required on the **Logic ESP32** (contains `game.masa`).

## Prereqs

- Two Arduino IDE installs (recommended):
  - **IDE A (Video)**: ESP32 core **1.0.6** (composite video compatible).
  - **IDE B (Logic)**: **ESP32 + Bluepad32** core.
- USB cables for both ESP32 boards.
- `game.masa` exported from the Mofongo IDE.

## Project Settings (in `AudioVideoExample.ino`)

Set these before building:

```
#define USE_DUAL_ESP 1
#define USE_MASA_RUNTIME 1

// Logic build
#define DUAL_ESP_ROLE_VIDEO 0
#define ENABLE_BT_CONTROLLER 1

// Video build
#define DUAL_ESP_ROLE_VIDEO 1
#define ENABLE_BT_CONTROLLER 0
```

## Flashing the Logic ESP32 (Master)

1. Open the project in **IDE B (Bluepad32 core)**.
2. Select **ESP32 Dev Module** (or equivalent) under:
   `Tools > Board > ESP32 + Bluepad32 Arduino`.
3. Choose a partition that includes SPIFFS.
   - Example: **Huge APP** (core Bluepad32)
4. Set `DUAL_ESP_ROLE_VIDEO 0`.
5. **Compile & upload** to the logic ESP32.
6. Open Serial Monitor (115200) and confirm:

```
[Mofongo] role=logic, spi=master
[Mofongo] SPIFFS ok
[Mofongo] MASA loaded
```

## Flashing the Video ESP32 (Slave)

1. Open the project in **IDE A (ESP32 core 1.0.6)**.
2. Select your video board (e.g. ESP32 Dev Module).
3. Set `DUAL_ESP_ROLE_VIDEO 1`.
4. **Compile & upload** to the video ESP32.
5. On TV you should see the UI overlay and video output.

## SPIFFS (Logic ESP32 Only)

You must flash SPIFFS to the **Logic ESP32** whenever `game.masa` changes.

### Required SPIFFS layout

```
<project>\data\game.masa
```

### SPIFFS size/offset for Bluepad32 “Huge APP”

From `huge_app.csv`:

- **Offset:** `0x310000`
- **Size:** `0xE0000`

### Flash via GUI (recommended)

Use the **Mofongo SPIFFS Builder**:

1. SPIFFS folder → `...\AudioVideoExample\data`
2. Size → `0xE0000`
3. Offset → `0x310000`
4. Build `spiffs.bin`
5. Flash to logic ESP32

### Flash via CLI (optional)

```
py -m esptool --chip esp32 --port COMX --baud 921600 write-flash 0x310000 spiffs.bin
```

## Python Tools (SPIFFS Builder + Emulator)

These tools live in `tools/` and use the project virtual environment.

### 1) Activate the venv

From the project root:

```
cd C:\Users\YourUser\Desktop\MofongoEngine
.\.venv\Scripts\activate
```

### 2) Run the SPIFFS Builder GUI

```
python tools\mofongo_spiffs_builder.py
```

### 3) Run the Emulator

```
python tools\mofongo_emulator.py
```

### 4) Exit the venv (optional)

```
deactivate
```

## Wiring (SPI)

Logic ESP32 (Master) ↔ Video ESP32 (Slave):

- SCLK → GPIO 18
- MISO → GPIO 19
- MOSI → GPIO 23
- CS   → GPIO 5
- GND  → GND (shared)

## Notes

- The **Video ESP32** never needs SPIFFS.
- If video is black: confirm the Video ESP32 is compiled with core **1.0.6**.
- If objects don’t appear: confirm `SPI: LINK` in video overlay and that logic logs **MASA loaded**.
