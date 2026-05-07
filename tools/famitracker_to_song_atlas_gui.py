#!/usr/bin/env python3
"""
GUI: FamiTracker TXT -> songs.h atlas
"""

import os
import re
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
import json


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class FamiTrackerSongAtlasGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FamiTracker TXT -> songs.h Atlas")
        self.geometry("980x620")
        self.minsize(860, 540)
        self.inputs = []
        self._build_ui()

    def _build_ui(self):
        frame_inputs = tk.LabelFrame(self, text="Input TXT files")
        frame_inputs.pack(fill="both", expand=True, padx=10, pady=8)

        self.listbox = tk.Listbox(frame_inputs, selectmode=tk.EXTENDED)
        self.listbox.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=8)

        sb = tk.Scrollbar(frame_inputs, orient="vertical", command=self.listbox.yview)
        sb.pack(side="left", fill="y", pady=8)
        self.listbox.configure(yscrollcommand=sb.set)

        buttons = tk.Frame(frame_inputs)
        buttons.pack(side="left", fill="y", padx=8, pady=8)
        tk.Button(buttons, text="Add TXT(s)", width=16, command=self.add_inputs).pack(pady=3)
        tk.Button(buttons, text="Load Exported", width=16, command=self.load_exported).pack(pady=3)
        tk.Button(buttons, text="Remove Selected", width=16, command=self.remove_selected).pack(pady=3)
        tk.Button(buttons, text="Move Up", width=16, command=self.move_up).pack(pady=3)
        tk.Button(buttons, text="Move Down", width=16, command=self.move_down).pack(pady=3)
        tk.Button(buttons, text="Clear", width=16, command=self.clear_list).pack(pady=3)

        frame_opts = tk.LabelFrame(self, text="Options")
        frame_opts.pack(fill="x", padx=10, pady=6)

        r1 = tk.Frame(frame_opts)
        r1.pack(fill="x", padx=8, pady=5)
        tk.Label(r1, text="Output songs.h").pack(side="left")
        self.out_var = tk.StringVar(value=os.path.join("gfx", "songs.h"))
        tk.Entry(r1, textvariable=self.out_var).pack(side="left", fill="x", expand=True, padx=8)
        tk.Button(r1, text="Browse", command=self.browse_output).pack(side="left")

        r2 = tk.Frame(frame_opts)
        r2.pack(fill="x", padx=8, pady=5)
        tk.Label(r2, text="Channel").pack(side="left")
        self.ch_var = tk.StringVar(value="0")
        tk.Entry(r2, textvariable=self.ch_var, width=6).pack(side="left", padx=(6, 16))

        self.mode_var = tk.StringVar(value="rowms")
        tk.Radiobutton(r2, text="Use row-ms", variable=self.mode_var, value="rowms").pack(side="left")
        self.rowms_var = tk.StringVar(value="38")
        tk.Entry(r2, textvariable=self.rowms_var, width=8).pack(side="left", padx=(6, 16))

        tk.Radiobutton(r2, text="Use BPM", variable=self.mode_var, value="bpm").pack(side="left")
        tk.Label(r2, text="BPM").pack(side="left", padx=(6, 2))
        self.bpm_var = tk.StringVar(value="150")
        tk.Entry(r2, textvariable=self.bpm_var, width=8).pack(side="left", padx=(0, 8))
        tk.Label(r2, text="Rows/beat").pack(side="left", padx=(2, 2))
        self.rpb_var = tk.StringVar(value="4")
        tk.Entry(r2, textvariable=self.rpb_var, width=8).pack(side="left")

        r3 = tk.Frame(frame_opts)
        r3.pack(fill="x", padx=8, pady=(2, 8))
        self.ft_timing_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            r3,
            text="Use FamiTracker timing (MACHINE/FRAMERATE + TRACK speed)",
            variable=self.ft_timing_var,
        ).pack(side="left", padx=(0, 16))
        self.mix4_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            r3,
            text="Mix 4 channels",
            variable=self.mix4_var,
        ).pack(side="left", padx=(0, 8))
        tk.Label(r3, text="Channels").pack(side="left")
        self.mix_channels_var = tk.StringVar(value="0,1,2,3")
        tk.Entry(r3, textvariable=self.mix_channels_var, width=10).pack(side="left", padx=(4, 16))
        self.export4_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            r3,
            text="Export 4ch tables",
            variable=self.export4_var,
        ).pack(side="left", padx=(0, 8))
        tk.Label(r3, text="4ch src").pack(side="left")
        self.channels4_var = tk.StringVar(value="0,1,2,3")
        tk.Entry(r3, textvariable=self.channels4_var, width=10).pack(side="left", padx=(4, 16))
        self.hold_empty_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            r3,
            text="Sustain on ... (disable to treat ... as rest)",
            variable=self.hold_empty_var,
        ).pack(side="left")

        run = tk.Frame(self)
        run.pack(fill="x", padx=10, pady=8)
        tk.Button(run, text="Generate songs.h", height=2, width=18, command=self.generate).pack(side="left")
        tk.Button(run, text="Open Output Folder", command=self.open_output_folder).pack(side="left", padx=8)

        log_frame = tk.LabelFrame(self, text="Log")
        log_frame.pack(fill="both", expand=False, padx=10, pady=(0, 10))
        self.log = tk.Text(log_frame, height=10)
        self.log.pack(fill="both", expand=True, padx=8, pady=8)

    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for p in self.inputs:
            self.listbox.insert(tk.END, p)

    def add_inputs(self):
        paths = filedialog.askopenfilenames(
            title="Select FamiTracker TXT files",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not paths:
            return
        for p in paths:
            if p not in self.inputs:
                self.inputs.append(p)
        self._refresh_list()

    def _resolve_input_path(self, value: str, header_dir: str) -> str:
        v = (value or "").strip()
        if not v:
            return v
        if os.path.isabs(v):
            return v
        cand = [
            os.path.join(header_dir, v),
            os.path.join(PROJECT_ROOT, v),
            os.path.join(PROJECT_ROOT, "tools", os.path.basename(v)),
        ]
        for p in cand:
            if os.path.isfile(p):
                return os.path.abspath(p)
        return os.path.abspath(cand[0])

    def load_exported(self):
        p = filedialog.askopenfilename(
            title="Load exported songs.h",
            filetypes=[("Header files", "*.h"), ("All files", "*.*")],
        )
        if not p:
            return
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                txt = f.read()
            m = re.search(r"// SONGS_ATLAS_META:\s*(\{.*\})", txt)
            if not m:
                raise ValueError("Header has no SONGS_ATLAS_META.")
            meta = json.loads(m.group(1))
            if not isinstance(meta, dict) or meta.get("type") != "songs_atlas_v1":
                raise ValueError("Invalid songs atlas metadata.")

            settings = meta.get("settings", {})
            if isinstance(settings, dict):
                ch = settings.get("channel")
                row_ms = settings.get("row_ms")
                hold_empty = settings.get("hold_empty")
                ft_timing = settings.get("ft_timing")
                mix_4ch = settings.get("mix_4ch")
                mix_channels = settings.get("mix_channels")
                export_4ch = settings.get("export_4ch")
                channels_4ch = settings.get("channels_4ch")
                bpm = settings.get("bpm")
                rpb = settings.get("rows_per_beat")
                if ch is not None:
                    self.ch_var.set(str(ch))
                if row_ms is not None:
                    self.rowms_var.set(str(row_ms))
                    self.mode_var.set("rowms")
                if bpm is not None:
                    self.bpm_var.set(str(bpm))
                if rpb is not None:
                    self.rpb_var.set(str(rpb))
                if hold_empty is not None:
                    self.hold_empty_var.set(bool(hold_empty))
                if ft_timing is not None:
                    self.ft_timing_var.set(bool(ft_timing))
                if mix_4ch is not None:
                    self.mix4_var.set(bool(mix_4ch))
                if isinstance(mix_channels, list) and mix_channels:
                    self.mix_channels_var.set(",".join(str(int(x)) for x in mix_channels))
                if export_4ch is not None:
                    self.export4_var.set(bool(export_4ch))
                if isinstance(channels_4ch, list) and channels_4ch:
                    self.channels4_var.set(",".join(str(int(x)) for x in channels_4ch))

            songs = meta.get("songs", [])
            if not isinstance(songs, list):
                raise ValueError("Invalid songs list in metadata.")
            header_dir = os.path.dirname(os.path.abspath(p))
            self.inputs = []
            missing = []
            for s in songs:
                if not isinstance(s, dict):
                    continue
                raw = str(s.get("input") or s.get("source") or "").strip()
                if not raw:
                    continue
                resolved = self._resolve_input_path(raw, header_dir)
                self.inputs.append(resolved)
                if not os.path.isfile(resolved):
                    missing.append(os.path.basename(raw))

            self._refresh_list()
            self.out_var.set(p)
            if missing:
                self.log_write("Missing source files (re-link manually): " + ", ".join(missing))
                messagebox.showwarning("Partial load", "Loaded metadata, but some source TXT files were not found.")
            else:
                messagebox.showinfo("Loaded", "songs.h loaded successfully.")
        except Exception as e:
            messagebox.showerror("Load failed", str(e))

    def remove_selected(self):
        sel = list(self.listbox.curselection())
        if not sel:
            return
        for i in reversed(sel):
            del self.inputs[i]
        self._refresh_list()

    def clear_list(self):
        self.inputs.clear()
        self._refresh_list()

    def move_up(self):
        sel = list(self.listbox.curselection())
        if not sel or sel[0] == 0:
            return
        for i in sel:
            self.inputs[i - 1], self.inputs[i] = self.inputs[i], self.inputs[i - 1]
        self._refresh_list()
        for i in sel:
            self.listbox.selection_set(i - 1)

    def move_down(self):
        sel = list(self.listbox.curselection())
        if not sel or sel[-1] == len(self.inputs) - 1:
            return
        for i in reversed(sel):
            self.inputs[i + 1], self.inputs[i] = self.inputs[i], self.inputs[i + 1]
        self._refresh_list()
        for i in sel:
            self.listbox.selection_set(i + 1)

    def browse_output(self):
        p = filedialog.asksaveasfilename(
            title="Output songs.h",
            defaultextension=".h",
            filetypes=[("Header files", "*.h"), ("All files", "*.*")],
            initialfile=os.path.basename(self.out_var.get()) if self.out_var.get() else "songs.h",
        )
        if p:
            self.out_var.set(p)

    def open_output_folder(self):
        out = self.out_var.get().strip()
        if not out:
            return
        out_abs = out if os.path.isabs(out) else os.path.join(PROJECT_ROOT, out)
        folder = os.path.dirname(os.path.abspath(out_abs))
        os.makedirs(folder, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(folder)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", folder], check=False)
        else:
            subprocess.run(["xdg-open", folder], check=False)

    def log_write(self, text: str):
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.update_idletasks()

    def generate(self):
        if not self.inputs:
            messagebox.showwarning("Missing input", "Add at least one TXT file.")
            return
        out = self.out_var.get().strip()
        if not out:
            messagebox.showwarning("Missing output", "Set output songs.h path.")
            return

        out_abs = out if os.path.isabs(out) else os.path.join(PROJECT_ROOT, out)
        script = os.path.join(os.path.dirname(__file__), "famitracker_to_song_atlas.py")
        cmd = [sys.executable, script]
        cmd.extend(self.inputs)
        cmd.extend(["--out", out_abs, "--channel", self.ch_var.get().strip()])
        if self.mode_var.get() == "rowms":
            cmd.extend(["--row-ms", self.rowms_var.get().strip()])
        else:
            cmd.extend(["--bpm", self.bpm_var.get().strip(), "--rows-per-beat", self.rpb_var.get().strip()])
        if self.ft_timing_var.get():
            cmd.append("--ft-timing")
        if self.mix4_var.get():
            cmd.append("--mix-4ch")
            cmd.extend(["--mix-channels", self.mix_channels_var.get().strip()])
        if self.export4_var.get():
            cmd.append("--export-4ch")
            cmd.extend(["--channels-4ch", self.channels4_var.get().strip()])
        if not self.hold_empty_var.get():
            cmd.append("--no-hold-empty")

        self.log.delete("1.0", tk.END)
        self.log_write("Running:")
        self.log_write(" ".join(f'"{c}"' if " " in c else c for c in cmd))
        self.log_write("")

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=PROJECT_ROOT)
            if proc.stdout:
                self.log_write(proc.stdout.rstrip())
            if proc.stderr:
                self.log_write(proc.stderr.rstrip())
            if proc.returncode == 0:
                self.log_write("\nDone.")
                messagebox.showinfo("Success", f"Generated:\n{os.path.abspath(out_abs)}")
            else:
                messagebox.showerror("Error", "Generation failed. Check log.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to run converter:\n{e}")


def main():
    app = FamiTrackerSongAtlasGui()
    app.mainloop()


if __name__ == "__main__":
    main()
