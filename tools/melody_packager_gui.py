#!/usr/bin/env python3
"""
GUI wrapper for tools/melody_packager.py
"""

import os
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class MelodyPackagerGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Melody Packager -> songs.h")
        self.geometry("860x560")
        self.minsize(760, 500)

        self.header_paths = []
        self._build_ui()

    def _build_ui(self):
        root = self

        frame_inputs = tk.LabelFrame(root, text="Input melody .h files")
        frame_inputs.pack(fill="both", expand=True, padx=10, pady=8)

        self.listbox = tk.Listbox(frame_inputs, selectmode=tk.EXTENDED)
        self.listbox.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=8)

        sb = tk.Scrollbar(frame_inputs, orient="vertical", command=self.listbox.yview)
        sb.pack(side="left", fill="y", pady=8)
        self.listbox.configure(yscrollcommand=sb.set)

        buttons = tk.Frame(frame_inputs)
        buttons.pack(side="left", fill="y", padx=8, pady=8)

        tk.Button(buttons, text="Add .h file(s)", width=16, command=self.add_headers).pack(pady=3)
        tk.Button(buttons, text="Remove Selected", width=16, command=self.remove_selected).pack(pady=3)
        tk.Button(buttons, text="Move Up", width=16, command=self.move_up).pack(pady=3)
        tk.Button(buttons, text="Move Down", width=16, command=self.move_down).pack(pady=3)
        tk.Button(buttons, text="Clear", width=16, command=self.clear_list).pack(pady=3)

        frame_opts = tk.LabelFrame(root, text="Options")
        frame_opts.pack(fill="x", padx=10, pady=6)

        row1 = tk.Frame(frame_opts)
        row1.pack(fill="x", padx=8, pady=5)
        tk.Label(row1, text="Output songs.h").pack(side="left")
        self.out_var = tk.StringVar(value=os.path.join("gfx", "songs.h"))
        tk.Entry(row1, textvariable=self.out_var).pack(side="left", fill="x", expand=True, padx=8)
        tk.Button(row1, text="Browse", command=self.browse_output).pack(side="left")

        frame_run = tk.Frame(root)
        frame_run.pack(fill="x", padx=10, pady=8)
        tk.Button(frame_run, text="Generate songs.h", height=2, command=self.generate).pack(
            side="left", padx=(0, 8)
        )

        frame_log = tk.LabelFrame(root, text="Log")
        frame_log.pack(fill="both", expand=False, padx=10, pady=(0, 10))
        self.log = tk.Text(frame_log, height=10)
        self.log.pack(fill="both", expand=True, padx=8, pady=8)

    def add_headers(self):
        paths = filedialog.askopenfilenames(
            title="Select melody header files",
            filetypes=[("Header files", "*.h"), ("All files", "*.*")],
        )
        if not paths:
            return
        for p in paths:
            if p not in self.header_paths:
                self.header_paths.append(p)
                self.listbox.insert(tk.END, p)

    def remove_selected(self):
        sel = list(self.listbox.curselection())
        if not sel:
            return
        for i in reversed(sel):
            del self.header_paths[i]
            self.listbox.delete(i)

    def clear_list(self):
        self.header_paths.clear()
        self.listbox.delete(0, tk.END)

    def move_up(self):
        sel = list(self.listbox.curselection())
        if not sel or sel[0] == 0:
            return
        for i in sel:
            self.header_paths[i - 1], self.header_paths[i] = self.header_paths[i], self.header_paths[i - 1]
        self._refresh_list()
        for i in sel:
            self.listbox.selection_set(i - 1)

    def move_down(self):
        sel = list(self.listbox.curselection())
        if not sel or sel[-1] == len(self.header_paths) - 1:
            return
        for i in reversed(sel):
            self.header_paths[i + 1], self.header_paths[i] = self.header_paths[i], self.header_paths[i + 1]
        self._refresh_list()
        for i in sel:
            self.listbox.selection_set(i + 1)

    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for p in self.header_paths:
            self.listbox.insert(tk.END, p)

    def browse_output(self):
        path = filedialog.asksaveasfilename(
            title="Output songs.h file",
            defaultextension=".h",
            filetypes=[("Header files", "*.h"), ("All files", "*.*")],
            initialfile=os.path.basename(self.out_var.get()) if self.out_var.get() else "songs.h",
        )
        if path:
            self.out_var.set(path)

    def log_write(self, text: str):
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.update_idletasks()

    def generate(self):
        if not self.header_paths:
            messagebox.showwarning("Missing input", "Add at least one melody .h file.")
            return

        out = self.out_var.get().strip()
        if not out:
            messagebox.showwarning("Missing output", "Set output songs.h path.")
            return
        out_abs = out if os.path.isabs(out) else os.path.join(PROJECT_ROOT, out)

        script_path = os.path.join(os.path.dirname(__file__), "melody_packager.py")
        cmd = [sys.executable, script_path]
        cmd.extend(self.header_paths)
        cmd.extend(["--out", out_abs])

        self.log.delete("1.0", tk.END)
        self.log_write("Running:")
        self.log_write(" ".join(f'"{c}"' if " " in c else c for c in cmd))
        self.log_write("")

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                cwd=PROJECT_ROOT,
            )
            if proc.stdout:
                self.log_write(proc.stdout.rstrip())
            if proc.stderr:
                self.log_write(proc.stderr.rstrip())

            if proc.returncode == 0:
                self.log_write("")
                self.log_write("Done.")
                messagebox.showinfo("Success", f"songs.h generated:\n{os.path.abspath(out_abs)}")
            else:
                messagebox.showerror("Error", "Generation failed. Check log.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to run packager:\n{e}")


def main():
    app = MelodyPackagerGui()
    app.mainloop()


if __name__ == "__main__":
    main()
