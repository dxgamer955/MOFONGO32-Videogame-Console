#!/usr/bin/env python3
"""
GUI wrapper for famitracker_to_melody.py
"""

import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class FamiTrackerToMelodyGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FamiTracker TXT -> Melody Header")
        self.geometry("860x540")
        self.minsize(760, 500)
        self._build_ui()

    def _build_ui(self):
        root = self

        frame_io = tk.LabelFrame(root, text="Input / Output")
        frame_io.pack(fill="x", padx=10, pady=8)

        r1 = tk.Frame(frame_io)
        r1.pack(fill="x", padx=8, pady=6)
        tk.Label(r1, text="Input TXT").pack(side="left")
        self.in_var = tk.StringVar(value=os.path.join("tools", "DK_test.txt"))
        tk.Entry(r1, textvariable=self.in_var).pack(side="left", fill="x", expand=True, padx=8)
        tk.Button(r1, text="Browse", command=self.browse_input).pack(side="left")

        r2 = tk.Frame(frame_io)
        r2.pack(fill="x", padx=8, pady=6)
        tk.Label(r2, text="Output .h").pack(side="left")
        self.out_var = tk.StringVar(value=os.path.join("gfx", "melody.h"))
        tk.Entry(r2, textvariable=self.out_var).pack(side="left", fill="x", expand=True, padx=8)
        tk.Button(r2, text="Browse", command=self.browse_output).pack(side="left")

        frame_opts = tk.LabelFrame(root, text="Options")
        frame_opts.pack(fill="x", padx=10, pady=6)

        r3 = tk.Frame(frame_opts)
        r3.pack(fill="x", padx=8, pady=6)
        tk.Label(r3, text="Channel").pack(side="left")
        self.ch_var = tk.StringVar(value="7")
        tk.Entry(r3, textvariable=self.ch_var, width=6).pack(side="left", padx=(6, 14))

        tk.Label(r3, text="Prefix").pack(side="left")
        self.prefix_var = tk.StringVar(value="melody")
        tk.Entry(r3, textvariable=self.prefix_var, width=18).pack(side="left", padx=(6, 14))

        self.mode_var = tk.StringVar(value="rowms")
        tk.Radiobutton(r3, text="Use row-ms", variable=self.mode_var, value="rowms").pack(side="left")
        self.rowms_var = tk.StringVar(value="38")
        tk.Entry(r3, textvariable=self.rowms_var, width=8).pack(side="left", padx=(6, 14))

        tk.Radiobutton(r3, text="Use BPM", variable=self.mode_var, value="bpm").pack(side="left")
        tk.Label(r3, text="BPM").pack(side="left", padx=(6, 2))
        self.bpm_var = tk.StringVar(value="150")
        tk.Entry(r3, textvariable=self.bpm_var, width=8).pack(side="left", padx=(0, 8))
        tk.Label(r3, text="Rows/beat").pack(side="left", padx=(2, 2))
        self.rpb_var = tk.StringVar(value="4")
        tk.Entry(r3, textvariable=self.rpb_var, width=8).pack(side="left")

        r4 = tk.Frame(frame_opts)
        r4.pack(fill="x", padx=8, pady=(2, 8))
        self.hold_empty_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            r4,
            text="Sustain on ... (disable to treat ... as rest)",
            variable=self.hold_empty_var,
        ).pack(side="left")

        frame_actions = tk.Frame(root)
        frame_actions.pack(fill="x", padx=10, pady=8)
        tk.Button(frame_actions, text="Convert", height=2, width=16, command=self.convert).pack(side="left")
        tk.Button(frame_actions, text="Open Output Folder", command=self.open_output_folder).pack(side="left", padx=8)

        frame_log = tk.LabelFrame(root, text="Log")
        frame_log.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log = tk.Text(frame_log, height=14)
        self.log.pack(fill="both", expand=True, padx=8, pady=8)

    def _log(self, msg: str):
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.update_idletasks()

    def browse_input(self):
        p = filedialog.askopenfilename(
            title="Select FamiTracker TXT",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if p:
            self.in_var.set(p)

    def browse_output(self):
        p = filedialog.asksaveasfilename(
            title="Save output header",
            defaultextension=".h",
            filetypes=[("Header files", "*.h"), ("All files", "*.*")],
            initialfile=os.path.basename(self.out_var.get()) if self.out_var.get() else "melody.h",
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

    def convert(self):
        in_path = self.in_var.get().strip()
        out_path = self.out_var.get().strip()
        prefix = self.prefix_var.get().strip()
        if not in_path:
            messagebox.showwarning("Missing input", "Select a TXT file.")
            return
        if not out_path:
            messagebox.showwarning("Missing output", "Set output .h path.")
            return
        if not prefix:
            messagebox.showwarning("Missing prefix", "Set variable prefix.")
            return

        in_abs = in_path if os.path.isabs(in_path) else os.path.join(PROJECT_ROOT, in_path)
        out_abs = out_path if os.path.isabs(out_path) else os.path.join(PROJECT_ROOT, out_path)
        script = os.path.join(os.path.dirname(__file__), "famitracker_to_melody.py")

        cmd = [
            sys.executable,
            script,
            in_abs,
            "--out",
            out_abs,
            "--channel",
            self.ch_var.get().strip(),
            "--prefix",
            prefix,
        ]

        if self.mode_var.get() == "rowms":
            cmd.extend(["--row-ms", self.rowms_var.get().strip()])
        else:
            cmd.extend(["--bpm", self.bpm_var.get().strip(), "--rows-per-beat", self.rpb_var.get().strip()])

        if not self.hold_empty_var.get():
            cmd.append("--no-hold-empty")

        self.log.delete("1.0", "end")
        self._log("Running:")
        self._log(" ".join(f'"{c}"' if " " in c else c for c in cmd))
        self._log("")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                cwd=PROJECT_ROOT,
            )
            if proc.stdout:
                self._log(proc.stdout.rstrip())
            if proc.stderr:
                self._log(proc.stderr.rstrip())
            if proc.returncode == 0:
                self._log("\nDone.")
                messagebox.showinfo("Success", f"Generated:\n{os.path.abspath(out_abs)}")
            else:
                messagebox.showerror("Error", "Conversion failed. Check log.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to run converter:\n{e}")


def main():
    app = FamiTrackerToMelodyGui()
    app.mainloop()


if __name__ == "__main__":
    main()
