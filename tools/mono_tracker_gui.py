#!/usr/bin/env python3
"""
Mono Tracker GUI (1 channel) for ESP32 TV project.

Tracker-style workflow:
- Pattern rows with tokens: NOTE (e.g. C-4), REST (---), HOLD (...)
- Fixed timing by BPM + rows per beat
- Playback preview on PC (winsound on Windows)
- Export to C header: melodyNotes, melodyDurMs, melodyLen
"""

import json
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import winsound  # Windows only
except Exception:
    winsound = None


NOTE_NAMES = ["C-", "C#", "D-", "D#", "E-", "F-", "F#", "G-", "G#", "A-", "A#", "B-"]
NOTE_INDEX = {
    "C": 0,
    "C#": 1,
    "D": 2,
    "D#": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "G": 7,
    "G#": 8,
    "A": 9,
    "A#": 10,
    "B": 11,
}

KEY_TO_NOTE = {
    # Lower row (base octave)
    "z": (0, 0), "s": (1, 0), "x": (2, 0), "d": (3, 0), "c": (4, 0), "v": (5, 0),
    "g": (6, 0), "b": (7, 0), "h": (8, 0), "n": (9, 0), "j": (10, 0), "m": (11, 0),
    # Upper row (base octave + 1)
    "q": (0, 1), "2": (1, 1), "w": (2, 1), "3": (3, 1), "e": (4, 1), "r": (5, 1),
    "5": (6, 1), "t": (7, 1), "6": (8, 1), "y": (9, 1), "7": (10, 1), "u": (11, 1),
}


def token_to_freq(token: str, last_freq: float) -> float:
    if token == "...":
        return last_freq
    if token == "---":
        return 0.0
    if len(token) != 3:
        return 0.0
    name = token[:2]
    octv = token[2]
    if not octv.isdigit():
        return 0.0
    key = name.replace("-", "")
    if key not in NOTE_INDEX:
        return 0.0
    octave = int(octv)
    midi = (octave + 1) * 12 + NOTE_INDEX[key]
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


class MonoTracker(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mono Tracker - ESP32")
        self.geometry("980x700")
        self.minsize(920, 620)

        self.rows = ["---"] * 64
        self.cursor_row = 0
        self.playing = False
        self.play_thread = None

        self._build_ui()
        self._refresh_grid()

    def _build_ui(self):
        root = tk.Frame(self)
        root.pack(fill="both", expand=True, padx=10, pady=10)

        top = tk.LabelFrame(root, text="Tracker Settings")
        top.pack(fill="x")

        tk.Label(top, text="Rows").grid(row=0, column=0, padx=6, pady=6, sticky="w")
        self.rows_var = tk.StringVar(value="64")
        tk.Spinbox(top, from_=8, to=512, increment=8, textvariable=self.rows_var, width=8).grid(
            row=0, column=1, padx=6, pady=6, sticky="w"
        )
        tk.Button(top, text="Resize", width=10, command=self.resize_rows).grid(
            row=0, column=2, padx=6, pady=6
        )

        tk.Label(top, text="BPM").grid(row=0, column=3, padx=6, pady=6, sticky="w")
        self.bpm_var = tk.StringVar(value="120")
        tk.Entry(top, textvariable=self.bpm_var, width=8).grid(row=0, column=4, padx=6, pady=6, sticky="w")

        tk.Label(top, text="Rows/Beat").grid(row=0, column=5, padx=6, pady=6, sticky="w")
        self.rpb_var = tk.StringVar(value="4")
        tk.Entry(top, textvariable=self.rpb_var, width=8).grid(row=0, column=6, padx=6, pady=6, sticky="w")

        tk.Label(top, text="Root Note").grid(row=1, column=0, padx=6, pady=6, sticky="w")
        self.note_var = tk.StringVar(value="C-")
        ttk.Combobox(top, textvariable=self.note_var, values=NOTE_NAMES, width=6, state="readonly").grid(
            row=1, column=1, padx=6, pady=6, sticky="w"
        )

        tk.Label(top, text="Octave").grid(row=1, column=2, padx=6, pady=6, sticky="w")
        self.oct_var = tk.StringVar(value="4")
        ttk.Combobox(top, textvariable=self.oct_var, values=["2", "3", "4", "5", "6", "7"], width=6, state="readonly").grid(
            row=1, column=3, padx=6, pady=6, sticky="w"
        )

        tk.Button(top, text="Set Note", width=12, command=self.set_note_selected).grid(row=1, column=4, padx=6, pady=6)
        tk.Button(top, text="Set Hold (...)", width=12, command=self.set_hold_selected).grid(row=1, column=5, padx=6, pady=6)
        tk.Button(top, text="Set Rest (---)", width=12, command=self.set_rest_selected).grid(row=1, column=6, padx=6, pady=6)

        body = tk.Frame(root)
        body.pack(fill="both", expand=True, pady=(8, 0))

        grid_frame = tk.LabelFrame(body, text="Pattern (Single Channel)")
        grid_frame.pack(side="left", fill="both", expand=True)

        self.tree = ttk.Treeview(grid_frame, columns=("row", "note"), show="headings", selectmode="extended", height=24)
        self.tree.heading("row", text="Row")
        self.tree.heading("note", text="Note")
        self.tree.column("row", width=90, anchor="center")
        self.tree.column("note", width=140, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=8)

        sb = ttk.Scrollbar(grid_frame, orient="vertical", command=self.tree.yview)
        sb.pack(side="left", fill="y", padx=(0, 8), pady=8)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<ButtonRelease-1>", self._on_tree_select)

        side = tk.Frame(body)
        side.pack(side="left", fill="y", padx=(8, 0))
        tk.Button(side, text="Fill Note", width=14, command=self.fill_note).pack(pady=4)
        tk.Button(side, text="Fill Hold", width=14, command=self.fill_hold).pack(pady=4)
        tk.Button(side, text="Fill Rest", width=14, command=self.fill_rest).pack(pady=4)
        tk.Button(side, text="Clear All", width=14, command=self.clear_all).pack(pady=4)
        tk.Label(side, text="").pack(pady=4)
        tk.Button(side, text="Play", width=14, command=self.play).pack(pady=4)
        tk.Button(side, text="Stop", width=14, command=self.stop).pack(pady=4)
        tk.Button(side, text="Export .h", width=14, command=self.export_header).pack(pady=4)
        tk.Button(side, text="Save .json", width=14, command=self.save_pattern).pack(pady=4)
        tk.Button(side, text="Load .json", width=14, command=self.load_pattern).pack(pady=4)

        logf = tk.LabelFrame(root, text="Log")
        logf.pack(fill="x", pady=(8, 0))
        self.log = tk.Text(logf, height=6)
        self.log.pack(fill="x", padx=8, pady=8)

        self._log("Ready. Select rows and set NOTE / HOLD / REST.")
        self._log("Keyboard: ZSX... + Q2W3... = notes, . = hold, Del/Backspace = rest.")
        self._log("Export uses: melodyNotes[], melodyDurMs[], melodyLen.")
        self.bind_all("<KeyPress>", self._on_keypress)

    def _log(self, txt: str):
        self.log.insert("end", txt + "\n")
        self.log.see("end")
        self.update_idletasks()

    def _parse_bpm(self) -> int:
        try:
            v = int(self.bpm_var.get())
            if v < 30 or v > 300:
                raise ValueError
            return v
        except Exception:
            raise ValueError("BPM debe ser entero entre 30 y 300.")

    def _parse_rpb(self) -> int:
        try:
            v = int(self.rpb_var.get())
            if v < 1 or v > 16:
                raise ValueError
            return v
        except Exception:
            raise ValueError("Rows/Beat debe ser entero entre 1 y 16.")

    def _row_ms(self) -> int:
        bpm = self._parse_bpm()
        rpb = self._parse_rpb()
        ms = int(round(60000.0 / (bpm * rpb)))
        return max(1, min(65535, ms))

    def _refresh_grid(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, tok in enumerate(self.rows):
            self.tree.insert("", "end", values=(f"{i:03d}", tok))
        self._select_row(self.cursor_row)

    def _select_row(self, row: int):
        if not self.rows:
            return
        row = max(0, min(row, len(self.rows) - 1))
        self.cursor_row = row
        children = self.tree.get_children()
        if not children:
            return
        iid = children[row]
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)

    def _on_tree_select(self, _event=None):
        sel = self._selected_indices()
        if sel:
            self.cursor_row = sel[0]

    def resize_rows(self):
        try:
            n = int(self.rows_var.get())
            if n < 8 or n > 512:
                raise ValueError
        except Exception:
            messagebox.showerror("Invalid", "Rows debe estar entre 8 y 512.")
            return

        old = self.rows[:]
        if n > len(old):
            self.rows = old + ["---"] * (n - len(old))
        else:
            self.rows = old[:n]
        self._refresh_grid()
        self._log(f"Rows: {n}")

    def _selected_indices(self):
        idx = []
        for iid in self.tree.selection():
            pos = self.tree.index(iid)
            idx.append(pos)
        idx.sort()
        return idx

    def _set_selected(self, token: str):
        sel = self._selected_indices()
        if not sel:
            return
        for i in sel:
            self.rows[i] = token
        self._refresh_grid()

    def set_note_selected(self):
        token = f"{self.note_var.get()}{self.oct_var.get()}"
        self._set_selected(token)

    def set_hold_selected(self):
        self._set_selected("...")

    def set_rest_selected(self):
        self._set_selected("---")

    def _fill(self, token: str):
        for i in range(len(self.rows)):
            self.rows[i] = token
        self._refresh_grid()

    def fill_note(self):
        self._fill(f"{self.note_var.get()}{self.oct_var.get()}")

    def fill_hold(self):
        self._fill("...")

    def fill_rest(self):
        self._fill("---")

    def clear_all(self):
        self._fill("---")

    def _set_row_token(self, row: int, token: str, advance: bool = True):
        if row < 0 or row >= len(self.rows):
            return
        self.rows[row] = token
        if advance:
            self.cursor_row = min(row + 1, len(self.rows) - 1)
        else:
            self.cursor_row = row
        self._refresh_grid()

    def _is_text_entry_focus(self) -> bool:
        w = self.focus_get()
        if w is None:
            return False
        cls = w.winfo_class()
        return cls in ("Entry", "TEntry", "Text", "Spinbox", "TCombobox")

    def _token_from_key(self, char: str):
        pair = KEY_TO_NOTE.get(char.lower())
        if pair is None:
            return None
        note_idx, oct_off = pair
        try:
            base_oct = int(self.oct_var.get())
        except Exception:
            base_oct = 4
        octave = max(0, min(9, base_oct + oct_off))
        return f"{NOTE_NAMES[note_idx]}{octave}"

    def _on_keypress(self, event):
        if self._is_text_entry_focus():
            return

        key = (event.char or "").lower()
        keysym = (event.keysym or "").lower()

        if keysym == "up":
            self._select_row(self.cursor_row - 1)
            return "break"
        if keysym == "down":
            self._select_row(self.cursor_row + 1)
            return "break"

        if keysym in ("delete", "backspace"):
            self._set_row_token(self.cursor_row, "---", advance=True)
            return "break"
        if key == ".":
            self._set_row_token(self.cursor_row, "...", advance=True)
            return "break"

        token = self._token_from_key(key)
        if token is not None:
            self._set_row_token(self.cursor_row, token, advance=True)
            return "break"

    def _build_segments(self):
        row_ms = self._row_ms()
        seq = []
        last = 0.0
        for tok in self.rows:
            f = token_to_freq(tok, last)
            last = f
            seq.append(f)

        notes = []
        durs = []
        if not seq:
            return notes, durs

        cur = seq[0]
        length = row_ms
        for f in seq[1:]:
            if abs(f - cur) < 0.01:
                length += row_ms
            else:
                notes.append(cur)
                durs.append(length)
                cur = f
                length = row_ms
        notes.append(cur)
        durs.append(length)
        return notes, durs

    def _build_header(self) -> str:
        notes, durs = self._build_segments()
        if not notes:
            raise ValueError("Pattern vacio.")

        note_literals = []
        for f in notes:
            if f < 1.0:
                note_literals.append("0.0f")
            else:
                note_literals.append(f"{f:.2f}f")

        dur_literals = [str(int(d)) for d in durs]
        return (
            "#pragma once\n\n"
            "const float melodyNotes[] = {\n  "
            + ", ".join(note_literals)
            + "\n};\n"
            "const unsigned short melodyDurMs[] = {\n  "
            + ", ".join(dur_literals)
            + "\n};\n"
            "const int melodyLen = sizeof(melodyNotes) / sizeof(melodyNotes[0]);\n"
        )

    def export_header(self):
        try:
            hdr = self._build_header()
        except ValueError as e:
            messagebox.showerror("Invalid", str(e))
            return

        out = filedialog.asksaveasfilename(
            title="Guardar melody header",
            defaultextension=".h",
            filetypes=[("Header files", "*.h"), ("All files", "*.*")],
            initialfile="melody.h",
        )
        if not out:
            return
        with open(out, "w", encoding="ascii") as f:
            f.write(hdr)
        self._log(f"Header guardado: {out}")
        messagebox.showinfo("Listo", f"Exportado:\n{out}")

    def save_pattern(self):
        data = {
            "rows": self.rows,
            "bpm": self.bpm_var.get(),
            "rows_per_beat": self.rpb_var.get(),
        }
        out = filedialog.asksaveasfilename(
            title="Guardar pattern",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile="pattern.json",
        )
        if not out:
            return
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self._log(f"Pattern guardado: {out}")

    def load_pattern(self):
        path = filedialog.askopenfilename(
            title="Abrir pattern",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        rows = data.get("rows", [])
        if not isinstance(rows, list) or not rows:
            messagebox.showerror("Invalid", "Archivo pattern invalido.")
            return
        self.rows = [str(x) for x in rows][:512]
        self.rows_var.set(str(len(self.rows)))
        self.bpm_var.set(str(data.get("bpm", "120")))
        self.rpb_var.set(str(data.get("rows_per_beat", "4")))
        self._refresh_grid()
        self._log(f"Pattern cargado: {path}")

    def _play_worker(self):
        try:
            row_ms = self._row_ms()
        except ValueError:
            row_ms = 125

        self._log("Playback start.")
        last = 0.0
        for tok in self.rows:
            if not self.playing:
                break
            f = token_to_freq(tok, last)
            last = f
            if f < 1.0:
                time.sleep(row_ms / 1000.0)
            else:
                hz = int(round(f))
                hz = max(37, min(hz, 32767))
                if winsound is not None and sys.platform.startswith("win"):
                    winsound.Beep(hz, row_ms)
                else:
                    time.sleep(row_ms / 1000.0)
        self.playing = False
        self._log("Playback end.")

    def play(self):
        if self.playing:
            return
        try:
            _ = self._row_ms()
        except ValueError as e:
            messagebox.showerror("Invalid", str(e))
            return
        self.playing = True
        self.play_thread = threading.Thread(target=self._play_worker, daemon=True)
        self.play_thread.start()

    def stop(self):
        self.playing = False
        self._log("Stop requested.")


def main():
    app = MonoTracker()
    app.mainloop()


if __name__ == "__main__":
    main()
