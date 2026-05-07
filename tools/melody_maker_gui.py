#!/usr/bin/env python3
"""
Simple Melody Maker GUI for ESP32 TV project.

Features:
- Build a melody note by note (including rests)
- Set BPM and note durations
- Preview melody on PC (winsound on Windows)
- Export as C arrays compatible with AudioVideoExample.ino
"""

import math
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

try:
    import winsound  # Windows only
except Exception:
    winsound = None


NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTE_INDEX = {n: i for i, n in enumerate(NOTE_NAMES)}

DURATIONS = [
    ("Whole (1)", 4.0),
    ("Half (1/2)", 2.0),
    ("Quarter (1/4)", 1.0),
    ("Eighth (1/8)", 0.5),
    ("Sixteenth (1/16)", 0.25),
]


def freq_for_note(note: str, octave: int) -> float:
    # A4 = 440 Hz
    semitones_from_a4 = (octave - 4) * 12 + (NOTE_INDEX[note] - NOTE_INDEX["A"])
    return 440.0 * (2.0 ** (semitones_from_a4 / 12.0))


class MelodyMaker(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Melody Maker - ESP32 TV")
        self.geometry("980x620")
        self.minsize(900, 560)

        self.sequence = []  # dict: {note, octave, beats}
        self.playing = False
        self.play_thread = None

        self._build_ui()

    def _build_ui(self):
        main = tk.Frame(self)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        top = tk.LabelFrame(main, text="Composer")
        top.pack(fill="x", pady=(0, 8))

        tk.Label(top, text="Note").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        self.note_var = tk.StringVar(value="C")
        tk.OptionMenu(top, self.note_var, *NOTE_NAMES, "REST").grid(row=0, column=1, padx=6, pady=6, sticky="w")

        tk.Label(top, text="Octave").grid(row=0, column=2, padx=6, pady=6, sticky="w")
        self.octave_var = tk.StringVar(value="4")
        tk.OptionMenu(top, self.octave_var, "2", "3", "4", "5", "6", "7").grid(row=0, column=3, padx=6, pady=6, sticky="w")

        tk.Label(top, text="Duration").grid(row=0, column=4, padx=6, pady=6, sticky="w")
        self.duration_var = tk.StringVar(value=DURATIONS[2][0])
        tk.OptionMenu(top, self.duration_var, *[d[0] for d in DURATIONS]).grid(row=0, column=5, padx=6, pady=6, sticky="w")

        tk.Label(top, text="BPM").grid(row=0, column=6, padx=6, pady=6, sticky="w")
        self.bpm_var = tk.StringVar(value="120")
        tk.Entry(top, textvariable=self.bpm_var, width=8).grid(row=0, column=7, padx=6, pady=6, sticky="w")

        tk.Button(top, text="Add Note", command=self.add_note, width=12).grid(row=0, column=8, padx=6, pady=6)
        tk.Button(top, text="Add Rest", command=self.add_rest, width=12).grid(row=0, column=9, padx=6, pady=6)

        body = tk.Frame(main)
        body.pack(fill="both", expand=True)

        left = tk.LabelFrame(body, text="Sequence")
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self.listbox = tk.Listbox(left)
        self.listbox.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=8)

        sb = tk.Scrollbar(left, orient="vertical", command=self.listbox.yview)
        sb.pack(side="left", fill="y", pady=8, padx=(0, 8))
        self.listbox.config(yscrollcommand=sb.set)

        controls = tk.Frame(body)
        controls.pack(side="left", fill="y")
        tk.Button(controls, text="Delete", width=14, command=self.delete_selected).pack(pady=4)
        tk.Button(controls, text="Move Up", width=14, command=self.move_up).pack(pady=4)
        tk.Button(controls, text="Move Down", width=14, command=self.move_down).pack(pady=4)
        tk.Button(controls, text="Clear", width=14, command=self.clear_all).pack(pady=4)
        tk.Label(controls, text="").pack(pady=4)
        tk.Button(controls, text="Play", width=14, command=self.play).pack(pady=4)
        tk.Button(controls, text="Stop", width=14, command=self.stop).pack(pady=4)
        tk.Button(controls, text="Export .h", width=14, command=self.export_header).pack(pady=4)
        tk.Button(controls, text="Copy C Arrays", width=14, command=self.copy_arrays).pack(pady=4)

        bottom = tk.LabelFrame(main, text="Preview / Log")
        bottom.pack(fill="x", pady=(8, 0))
        self.log = tk.Text(bottom, height=8)
        self.log.pack(fill="x", padx=8, pady=8)

        self._log("Ready.")
        self._log("Tip: build melody and press 'Copy C Arrays'.")

    def _log(self, msg: str):
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.update_idletasks()

    def _get_beats(self) -> float:
        label = self.duration_var.get()
        for n, beats in DURATIONS:
            if n == label:
                return beats
        return 1.0

    def _get_bpm(self) -> int:
        try:
            bpm = int(self.bpm_var.get())
            if bpm < 30 or bpm > 300:
                raise ValueError()
            return bpm
        except Exception:
            raise ValueError("BPM must be an integer between 30 and 300.")

    def _duration_ms(self, beats: float, bpm: int) -> int:
        ms = int(round((60000.0 / bpm) * beats))
        return max(1, min(ms, 65535))

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        bpm = 120
        try:
            bpm = self._get_bpm()
        except Exception:
            pass
        for i, e in enumerate(self.sequence):
            ms = self._duration_ms(e["beats"], bpm)
            if e["note"] == "REST":
                label = f"{i:03d} | REST | {e['beats']} beat(s) | {ms} ms"
            else:
                f = freq_for_note(e["note"], e["octave"])
                label = f"{i:03d} | {e['note']}{e['octave']} ({f:.2f} Hz) | {e['beats']} beat(s) | {ms} ms"
            self.listbox.insert("end", label)

    def add_note(self):
        note = self.note_var.get()
        if note == "REST":
            self.add_rest()
            return
        self.sequence.append(
            {
                "note": note,
                "octave": int(self.octave_var.get()),
                "beats": self._get_beats(),
            }
        )
        self._refresh_list()

    def add_rest(self):
        self.sequence.append({"note": "REST", "octave": 4, "beats": self._get_beats()})
        self._refresh_list()

    def delete_selected(self):
        sel = list(self.listbox.curselection())
        if not sel:
            return
        for idx in reversed(sel):
            del self.sequence[idx]
        self._refresh_list()

    def move_up(self):
        sel = list(self.listbox.curselection())
        if not sel or sel[0] == 0:
            return
        for i in sel:
            self.sequence[i - 1], self.sequence[i] = self.sequence[i], self.sequence[i - 1]
        self._refresh_list()
        for i in sel:
            self.listbox.selection_set(i - 1)

    def move_down(self):
        sel = list(self.listbox.curselection())
        if not sel or sel[-1] == len(self.sequence) - 1:
            return
        for i in reversed(sel):
            self.sequence[i + 1], self.sequence[i] = self.sequence[i], self.sequence[i + 1]
        self._refresh_list()
        for i in sel:
            self.listbox.selection_set(i + 1)

    def clear_all(self):
        self.sequence = []
        self._refresh_list()

    def _build_arrays_text(self, var_prefix: str = "melody") -> str:
        bpm = self._get_bpm()
        notes = []
        durs = []
        for e in self.sequence:
            if e["note"] == "REST":
                notes.append("0.0f")
            else:
                notes.append(f"{freq_for_note(e['note'], e['octave']):.2f}f")
            durs.append(str(self._duration_ms(e["beats"], bpm)))

        notes_txt = ", ".join(notes)
        durs_txt = ", ".join(durs)
        return (
            f"const float {var_prefix}Notes[] = {{\n  {notes_txt}\n}};\n"
            f"const unsigned short {var_prefix}DurMs[] = {{\n  {durs_txt}\n}};\n"
            f"const int {var_prefix}Len = sizeof({var_prefix}Notes) / sizeof({var_prefix}Notes[0]);\n"
        )

    def copy_arrays(self):
        if not self.sequence:
            messagebox.showwarning("No melody", "Add some notes first.")
            return
        try:
            txt = self._build_arrays_text("melody")
        except ValueError as e:
            messagebox.showerror("Invalid", str(e))
            return
        self.clipboard_clear()
        self.clipboard_append(txt)
        self._log("C arrays copied to clipboard.")

    def export_header(self):
        if not self.sequence:
            messagebox.showwarning("No melody", "Add some notes first.")
            return
        try:
            txt = (
                "#pragma once\n\n"
                + self._build_arrays_text("melody")
            )
        except ValueError as e:
            messagebox.showerror("Invalid", str(e))
            return

        out = filedialog.asksaveasfilename(
            title="Save melody header",
            defaultextension=".h",
            filetypes=[("Header files", "*.h"), ("All files", "*.*")],
            initialfile="melody.h",
        )
        if not out:
            return
        with open(out, "w", encoding="ascii") as f:
            f.write(txt)
        self._log(f"Saved: {out}")
        messagebox.showinfo("Saved", f"Header exported:\n{out}")

    def _play_worker(self):
        try:
            bpm = self._get_bpm()
        except Exception:
            bpm = 120

        self._log("Playback start.")
        for e in self.sequence:
            if not self.playing:
                break
            ms = self._duration_ms(e["beats"], bpm)
            if e["note"] == "REST":
                time.sleep(ms / 1000.0)
            else:
                hz = int(round(freq_for_note(e["note"], e["octave"])))
                hz = max(37, min(hz, 32767))
                if winsound is not None and sys.platform.startswith("win"):
                    winsound.Beep(hz, ms)
                else:
                    # Cross-platform fallback: no native beep here, just timing.
                    time.sleep(ms / 1000.0)
        self.playing = False
        self._log("Playback end.")

    def play(self):
        if not self.sequence:
            messagebox.showwarning("No melody", "Add some notes first.")
            return
        if self.playing:
            return
        try:
            _ = self._get_bpm()
        except ValueError as e:
            messagebox.showerror("Invalid BPM", str(e))
            return
        self.playing = True
        self.play_thread = threading.Thread(target=self._play_worker, daemon=True)
        self.play_thread.start()

    def stop(self):
        self.playing = False
        self._log("Stop requested.")


def main():
    app = MelodyMaker()
    app.mainloop()


if __name__ == "__main__":
    main()
