# Unused Code Archive

These files were moved out of the Arduino sketch root because no active root `.ino`, `.cpp` or `.h` file referenced them.

Moved files:

- `AudioSystem.h` and `AudioOutput.h`: older DAC/timer audio path. Active audio now lives in `AudioApi.*`.
- `CompositeOutput.h` and `CompositeGraphics.h`: older monochrome/composite video helpers. Active video uses `ESP32CompositeColorVideo-master/src/CompositeColorOutput.h` plus local `Graphics.*`.
- `GameControllers.h`: old bitluni controller helper, not used by the current Bluepad32/WebInput paths.
- `font6x8.h` and `luni.h`: old demo assets; current font data comes from `gfx/font.h`.

If one of these is needed again, move it back to the project root and add the include/reference explicitly.
