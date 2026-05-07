# MOFONGO32 Code Map and External References

This note is for quick code review before compiling/flashing.

## Main project code

- `AudioVideoExample.ino`: Arduino entrypoint. Chooses logic/video role, initializes SPIFFS, input, audio, video and MASA.
- `MasaLoader.*`: loads `/game.masa` from SPIFFS and exposes script/room buffers.
- `MasaRuntime.*`: interprets MASA bytecode, updates objects/signals/collisions/HUD/audio commands, and emits render commands.
- `MasaFormat.h`: binary contract between the Python exporter and ESP32 runtime.
- `MasaSpiLink.*`: active SPI packet format for MASA frames between logic ESP32 and video ESP32.
- `DualEspLink.*`: older/simple SPI packet path used by the non-MASA demo mode.
- `Graphics.*`, `Image.h`, `Sprites.h`, `Font.h`: local framebuffer and bitmap drawing helpers.
- `GameApi.*`, `BackgroundApi.*`, `AudioApi.*`: small gameplay-facing APIs for sprites, backgrounds and sound.
- `WebInput.*`: optional browser/controller input path, disabled by default.

## Generated or content files

- `gfx/*.h`: generated assets: sprites, backgrounds, songs, rooms and tilemaps.
- `generated/program_logic.h`: generated object/room logic when present.
- `Programs/*.ingr`: editable Mofongo projects.
- `Programs/*.masa`, `data/game.masa`, `spiffs/game.masa`: exported runtime packages.
- `ingr_cache/`, `tools/emulator_cache/`, `tmp/`: caches/backups. Do not hand-comment these unless you are preserving a specific experiment.

## External libraries and platform APIs

- ESP32 Arduino core: `Arduino.h`, `SPI.h`, `SPIFFS.h`, `FS.h`, `WiFi.h`, LEDC PWM, DAC/timer drivers and ESP-IDF SoC headers.
- Bluepad32: Bluetooth gamepad support, compiled only when `ENABLE_BT_CONTROLLER` is on for the logic board.
- `ESP32CompositeColorVideo-master`: vendored bitluni-style composite color video output. The active include is `ESP32CompositeColorVideo-master/src/CompositeColorOutput.h`.
- bitluni demo code lineage: several drawing/video helper files started as bitluni examples and were adapted for this project.

## Archived unused code

Low-confidence or old code should not be deleted directly. I moved only files with no references from active root `.ino/.cpp/.h` files into `unused_code/`, with a README explaining why. If one is needed again, move it back to the sketch root and include it intentionally.
