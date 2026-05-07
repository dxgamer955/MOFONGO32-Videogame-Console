#!/usr/bin/env python3
"""
GUI wrapper for tools/png_to_backgrounds.py
"""

import os
import json
import math
import re
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
from png_to_sprites import (
    AtariQuantizer,
    NesToAtariQuantizer,
    apply_tv_safe_rgba,
    load_atari_palette_rgb,
    parse_png,
    rgba_to_gray_level,
)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class PngToBackgroundsGui(tk.Tk):
    PREVIEW_W = 320
    PREVIEW_H = 220

    def __init__(self):
        super().__init__()
        self.title("PNG to ESP32 Backgrounds Converter (320x200)")
        self.geometry("860x560")
        self.minsize(760, 500)

        self.png_paths = []
        self.preview_image = None
        self.preview_mode_var = tk.StringVar(value="original")
        self.preview_ntsc_var = tk.BooleanVar(value=True)
        self._png_rgba_cache = {}
        self._atari_palette = load_atari_palette_rgb()
        self._atari_quant = AtariQuantizer()
        self._nes_quant = NesToAtariQuantizer()
        self._build_ui()

    def _build_ui(self):
        root = self

        frame_inputs = tk.LabelFrame(root, text="Input PNG files (must be 320x200)")
        frame_inputs.pack(fill="both", expand=True, padx=10, pady=8)

        self.listbox = tk.Listbox(frame_inputs, selectmode=tk.EXTENDED)
        self.listbox.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=8)
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self.update_preview())

        sb = tk.Scrollbar(frame_inputs, orient="vertical", command=self.listbox.yview)
        sb.pack(side="left", fill="y", pady=8)
        self.listbox.configure(yscrollcommand=sb.set)

        buttons = tk.Frame(frame_inputs)
        buttons.pack(side="left", fill="y", padx=8, pady=8)

        tk.Button(buttons, text="Add PNG(s)", width=16, command=self.add_pngs).pack(pady=3)
        tk.Button(buttons, text="Load Export", width=16, command=self.load_export).pack(pady=3)
        tk.Button(buttons, text="Remove Selected", width=16, command=self.remove_selected).pack(pady=3)
        tk.Button(buttons, text="Move Up", width=16, command=self.move_up).pack(pady=3)
        tk.Button(buttons, text="Move Down", width=16, command=self.move_down).pack(pady=3)
        tk.Button(buttons, text="Clear", width=16, command=self.clear_list).pack(pady=3)

        preview = tk.LabelFrame(frame_inputs, text="Background Preview")
        preview.pack(side="left", fill="y", padx=(0, 8), pady=8)
        preview.configure(width=self.PREVIEW_W + 24, height=self.PREVIEW_H + 96)
        preview.pack_propagate(False)
        mode_row = tk.Frame(preview)
        mode_row.pack(fill="x", padx=8, pady=(8, 0))
        tk.Label(mode_row, text="Output preview").pack(side="left")
        tk.OptionMenu(mode_row, self.preview_mode_var, "original", "atari", "nes", "gray").pack(
            side="left", padx=6
        )
        tk.Checkbutton(mode_row, text="NTSC sim", variable=self.preview_ntsc_var, command=self.update_preview).pack(
            side="left", padx=6
        )
        self.preview_mode_var.trace_add("write", lambda *_: self.update_preview())
        image_slot = tk.Frame(preview, width=self.PREVIEW_W, height=self.PREVIEW_H, bg="#202020")
        image_slot.pack(padx=8, pady=(6, 4))
        image_slot.pack_propagate(False)
        self.preview_label = tk.Label(image_slot, text="No image", anchor="center", bg="#202020", fg="#d0d0d0")
        self.preview_label.pack(fill="both", expand=True)
        self.preview_info = tk.Label(preview, text="", anchor="w", justify="left")
        self.preview_info.pack(fill="x", padx=8, pady=(0, 8))

        frame_opts = tk.LabelFrame(root, text="Options")
        frame_opts.pack(fill="x", padx=10, pady=6)

        row1 = tk.Frame(frame_opts)
        row1.pack(fill="x", padx=8, pady=5)
        tk.Label(row1, text="Output .h").pack(side="left")
        self.out_var = tk.StringVar(value=os.path.join("gfx", "backgrounds.h"))
        tk.Entry(row1, textvariable=self.out_var).pack(side="left", fill="x", expand=True, padx=8)
        tk.Button(row1, text="Browse", command=self.browse_output).pack(side="left")

        row2 = tk.Frame(frame_opts)
        row2.pack(fill="x", padx=8, pady=5)
        tk.Label(row2, text="Base name").pack(side="left")
        self.name_var = tk.StringVar(value="backgrounds")
        tk.Entry(row2, textvariable=self.name_var, width=22).pack(side="left", padx=8)

        tk.Label(row2, text="Levels").pack(side="left")
        self.levels_var = tk.StringVar(value="54")
        tk.Entry(row2, textvariable=self.levels_var, width=6).pack(side="left", padx=4)
        tk.Label(row2, text="Color mode").pack(side="left", padx=(12, 0))
        self.color_mode_var = tk.StringVar(value="atari")
        tk.OptionMenu(row2, self.color_mode_var, "atari", "nes", "gray").pack(side="left", padx=4)

        row3 = tk.Frame(frame_opts)
        row3.pack(fill="x", padx=8, pady=5)
        self.tv_safe_var = tk.BooleanVar(value=True)
        tk.Checkbutton(row3, text="TV-safe export", variable=self.tv_safe_var, command=self.update_preview).pack(
            side="left"
        )
        tk.Label(row3, text="Desat").pack(side="left", padx=(12, 0))
        self.tv_desat_var = tk.StringVar(value="0.25")
        tk.Entry(row3, textvariable=self.tv_desat_var, width=6).pack(side="left", padx=4)
        tk.Label(row3, text="Blur").pack(side="left", padx=(12, 0))
        self.tv_blur_var = tk.StringVar(value="1")
        tk.Entry(row3, textvariable=self.tv_blur_var, width=6).pack(side="left", padx=4)

        frame_run = tk.Frame(root)
        frame_run.pack(fill="x", padx=10, pady=8)
        tk.Button(frame_run, text="Generate Header", height=2, command=self.generate).pack(
            side="left", padx=(0, 8)
        )

        frame_log = tk.LabelFrame(root, text="Log")
        frame_log.pack(fill="both", expand=False, padx=10, pady=(0, 10))
        self.log = tk.Text(frame_log, height=10)
        self.log.pack(fill="both", expand=True, padx=8, pady=8)

    def add_pngs(self):
        paths = filedialog.askopenfilenames(
            title="Select PNG files",
            filetypes=[("PNG files", "*.png"), ("All files", "*.*")],
        )
        if not paths:
            return
        for p in paths:
            if p not in self.png_paths:
                self.png_paths.append(p)
                self.listbox.insert(tk.END, p)
        self.update_preview()

    def _load_meta_json(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        if not isinstance(meta, dict):
            raise ValueError("Invalid metadata json.")
        if meta.get("type") != "backgrounds_project_v1":
            raise ValueError("JSON is not a backgrounds project.")
        pngs = meta.get("pngs", [])
        if not isinstance(pngs, list):
            raise ValueError("Invalid png list in metadata.")
        self.png_paths = [str(p) for p in pngs]
        self._refresh_list()
        if "out" in meta:
            self.out_var.set(str(meta["out"]))
        if "name" in meta:
            self.name_var.set(str(meta["name"]))
        if "levels" in meta:
            self.levels_var.set(str(meta["levels"]))
        if "color_mode" in meta:
            self.color_mode_var.set(str(meta["color_mode"]))
        if "tv_safe" in meta:
            self.tv_safe_var.set(bool(meta["tv_safe"]))
        if "tv_desat" in meta:
            self.tv_desat_var.set(str(meta["tv_desat"]))
        if "tv_blur" in meta:
            self.tv_blur_var.set(str(meta["tv_blur"]))

    def _load_meta_from_header(self, path: str):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        m = re.search(r"// ASSET_META:\s*(\{.*\})", text)
        if not m:
            raise ValueError("Header has no ASSET_META. Re-export with latest converter.")
        meta = json.loads(m.group(1))
        tmp_path = os.path.join(PROJECT_ROOT, ".tmp_backgrounds_meta_load.json")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        self._load_meta_json(tmp_path)
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    def load_export(self):
        path = filedialog.askopenfilename(
            title="Load backgrounds export (.json or .h)",
            filetypes=[("Supported", "*.json *.h"), ("JSON", "*.json"), ("Header", "*.h"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext == ".json":
                self._load_meta_json(path)
            elif ext == ".h":
                self._load_meta_from_header(path)
            else:
                raise ValueError("Unsupported file type.")
            self.log_write(f"Loaded export: {path}")
            self.update_preview()
        except Exception as e:
            messagebox.showerror("Load failed", str(e))

    def remove_selected(self):
        sel = list(self.listbox.curselection())
        if not sel:
            return
        for i in reversed(sel):
            del self.png_paths[i]
            self.listbox.delete(i)
        self.update_preview()

    def clear_list(self):
        self.png_paths.clear()
        self.listbox.delete(0, tk.END)
        self.update_preview()

    def move_up(self):
        sel = list(self.listbox.curselection())
        if not sel or sel[0] == 0:
            return
        for i in sel:
            self.png_paths[i - 1], self.png_paths[i] = self.png_paths[i], self.png_paths[i - 1]
        self._refresh_list()
        for i in sel:
            self.listbox.selection_set(i - 1)

    def move_down(self):
        sel = list(self.listbox.curselection())
        if not sel or sel[-1] == len(self.png_paths) - 1:
            return
        for i in reversed(sel):
            self.png_paths[i + 1], self.png_paths[i] = self.png_paths[i], self.png_paths[i + 1]
        self._refresh_list()
        for i in sel:
            self.listbox.selection_set(i + 1)

    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for p in self.png_paths:
            self.listbox.insert(tk.END, p)
        self.update_preview()

    def update_preview(self):
        if not self.png_paths:
            self.preview_label.configure(image="", text="No image")
            self.preview_info.configure(text="")
            self.preview_image = None
            return

        sel = list(self.listbox.curselection())
        idx = sel[0] if sel else 0
        path = self.png_paths[idx]

        try:
            img, w, h = self.build_output_preview(path)
            self.preview_image = img
            self.preview_label.configure(image=self.preview_image, text="")
            size_ok = "OK 320x200" if (w == 320 and h == 200) else "INVALID SIZE"
            self.preview_info.configure(
                text=f"{os.path.basename(path)}\n{w}x{h}  {size_ok}\nmode: {self.preview_mode_var.get()}"
            )
        except Exception:
            self.preview_label.configure(image="", text="Preview unavailable")
            self.preview_info.configure(text=os.path.basename(path))
            self.preview_image = None

    def _get_png_rgba(self, path: str):
        cached = self._png_rgba_cache.get(path)
        if cached is not None:
            return cached
        parsed = parse_png(path)
        self._png_rgba_cache[path] = parsed
        return parsed

    def build_output_preview(self, path: str):
        mode = self.preview_mode_var.get().strip().lower()
        if mode == "original":
            img = tk.PhotoImage(file=path)
            w = img.width()
            h = img.height()
            img = self._fit_preview_image(img, self.PREVIEW_W, self.PREVIEW_H)
            return img, w, h

        w, h, rgba = self._get_png_rgba(path)
        if self.tv_safe_var.get():
            rgba = apply_tv_safe_rgba(w, h, rgba, desat=self._tv_desat_value(), blur_radius=self._tv_blur_value())
        max_w, max_h = self.PREVIEW_W, self.PREVIEW_H
        factor = max(1, int(math.ceil(max(w / max_w, h / max_h))))
        out_w = (w + factor - 1) // factor
        out_h = (h + factor - 1) // factor
        levels = max(1, int(self.levels_var.get().strip() or "54"))
        img = tk.PhotoImage(width=out_w, height=out_h)
        for oy in range(out_h):
            sy = min(h - 1, oy * factor)
            row_parts = []
            row_base = sy * w
            for ox in range(out_w):
                sx = min(w - 1, ox * factor)
                r, g, b, _a = rgba[row_base + sx]
                if mode == "gray":
                    lv = rgba_to_gray_level(r, g, b, levels)
                    v = int(round((lv / max(1, levels)) * 255))
                    cr, cg, cb = v, v, v
                elif mode == "atari":
                    idx = self._atari_quant.rgb_to_index(r, g, b)
                    cr, cg, cb = self._atari_palette[idx]
                else:  # nes
                    idx = self._nes_quant.rgb_to_index(r, g, b)
                    cr, cg, cb = self._atari_palette[idx]
                if self.preview_ntsc_var.get():
                    yv = 0.299 * cr + 0.587 * cg + 0.114 * cb
                    sat = 0.82
                    cr = max(0, min(255, int(yv + (cr - yv) * sat)))
                    cg = max(0, min(255, int(yv + (cg - yv) * sat)))
                    cb = max(0, min(255, int(yv + (cb - yv) * sat)))
                row_parts.append(f"#{cr:02x}{cg:02x}{cb:02x}")
            img.put("{" + " ".join(row_parts) + "}", to=(0, oy))
        img = self._fit_preview_image(img, self.PREVIEW_W, self.PREVIEW_H)
        return img, w, h

    def _tv_desat_value(self) -> float:
        try:
            v = float(self.tv_desat_var.get().strip() or "0.25")
        except Exception:
            v = 0.25
        if v < 0.0:
            v = 0.0
        if v > 1.0:
            v = 1.0
        return v

    def _tv_blur_value(self) -> int:
        try:
            v = int(self.tv_blur_var.get().strip() or "1")
        except Exception:
            v = 1
        if v < 0:
            v = 0
        if v > 4:
            v = 4
        return v

    def _fit_preview_image(self, img: tk.PhotoImage, max_w: int, max_h: int) -> tk.PhotoImage:
        w = img.width()
        h = img.height()
        if w <= 0 or h <= 0:
            return img
        down = max(1, int(math.ceil(max(w / max_w, h / max_h))))
        if down > 1:
            img = img.subsample(down, down)
            w = img.width()
            h = img.height()
        up = max(1, min(max_w // max(1, w), max_h // max(1, h)))
        if up > 1:
            img = img.zoom(up, up)
        return img

    def browse_output(self):
        path = filedialog.asksaveasfilename(
            title="Output header file",
            defaultextension=".h",
            filetypes=[("Header files", "*.h"), ("All files", "*.*")],
            initialfile=os.path.basename(self.out_var.get()) if self.out_var.get() else "backgrounds.h",
        )
        if path:
            self.out_var.set(path)

    def log_write(self, text: str):
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.update_idletasks()

    def generate(self):
        if not self.png_paths:
            messagebox.showwarning("Missing input", "Add at least one PNG file.")
            return

        out = self.out_var.get().strip()
        name = self.name_var.get().strip()
        if not out:
            messagebox.showwarning("Missing output", "Set output .h path.")
            return
        if not name:
            messagebox.showwarning("Missing name", "Set base variable name.")
            return

        out_abs = out if os.path.isabs(out) else os.path.join(PROJECT_ROOT, out)

        script_path = os.path.join(os.path.dirname(__file__), "png_to_backgrounds.py")
        cmd = [sys.executable, script_path]
        cmd.extend(self.png_paths)
        cmd.extend(
            [
                "--out",
                out_abs,
                "--name",
                name,
                "--levels",
                self.levels_var.get().strip(),
                "--color-mode",
                self.color_mode_var.get().strip(),
            ]
        )
        if self.tv_safe_var.get():
            cmd.append("--tv-safe")
        cmd.extend(["--tv-desat", self.tv_desat_var.get().strip() or "0.25"])
        cmd.extend(["--tv-blur", self.tv_blur_var.get().strip() or "1"])

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
                messagebox.showinfo("Success", f"Header generated:\n{os.path.abspath(out_abs)}")
            else:
                messagebox.showerror("Error", "Conversion failed. Check log.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to run converter:\n{e}")


def main():
    app = PngToBackgroundsGui()
    app.mainloop()


if __name__ == "__main__":
    main()
