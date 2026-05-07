#!/usr/bin/env python3
"""
GUI wrapper for tools/png_to_sprites.py
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


class PngToSpritesGui(tk.Tk):
    PREVIEW_W = 320
    PREVIEW_H = 220

    def __init__(self):
        super().__init__()
        self.title("PNG to ESP32 Sprites Converter")
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
        self.frame_names_var = tk.StringVar(value="")
        self._build_ui()

    def _build_ui(self):
        root = self

        frame_inputs = tk.LabelFrame(root, text="Input PNG files")
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

        preview = tk.LabelFrame(frame_inputs, text="Sprite Preview")
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
        self.out_var = tk.StringVar(value=os.path.join("gfx", "my_sprites.h"))
        tk.Entry(row1, textvariable=self.out_var).pack(side="left", fill="x", expand=True, padx=8)
        tk.Button(row1, text="Browse", command=self.browse_output).pack(side="left")

        row2 = tk.Frame(frame_opts)
        row2.pack(fill="x", padx=8, pady=5)
        tk.Label(row2, text="Base name").pack(side="left")
        self.name_var = tk.StringVar(value="my_sprites")
        tk.Entry(row2, textvariable=self.name_var, width=22).pack(side="left", padx=8)

        tk.Label(row2, text="Origin").pack(side="left")
        self.origin_var = tk.StringVar(value="center")
        tk.OptionMenu(row2, self.origin_var, "center", "topleft").pack(side="left", padx=8)

        tk.Label(row2, text="Levels").pack(side="left")
        self.levels_var = tk.StringVar(value="54")
        tk.Entry(row2, textvariable=self.levels_var, width=6).pack(side="left", padx=4)
        tk.Label(row2, text="Color mode").pack(side="left", padx=(12, 0))
        self.color_mode_var = tk.StringVar(value="atari")
        tk.OptionMenu(row2, self.color_mode_var, "atari", "nes", "gray").pack(side="left", padx=4)

        tk.Label(row2, text="Transparency").pack(side="left", padx=(12, 0))
        self.trans_var = tk.StringVar(value="255")
        tk.Entry(row2, textvariable=self.trans_var, width=6).pack(side="left", padx=4)

        tk.Label(row2, text="Alpha threshold").pack(side="left", padx=(12, 0))
        self.alpha_var = tk.StringVar(value="8")
        tk.Entry(row2, textvariable=self.alpha_var, width=6).pack(side="left", padx=4)

        row3 = tk.Frame(frame_opts)
        row3.pack(fill="x", padx=8, pady=5)
        tk.Label(row3, text="Origin X").pack(side="left")
        self.origin_x_var = tk.StringVar(value="")
        tk.Entry(row3, textvariable=self.origin_x_var, width=8).pack(side="left", padx=4)
        tk.Label(row3, text="Origin Y").pack(side="left")
        self.origin_y_var = tk.StringVar(value="")
        tk.Entry(row3, textvariable=self.origin_y_var, width=8).pack(side="left", padx=4)
        tk.Label(
            row3,
            text="(Optional. If both are set, these override Origin)",
            fg="#555",
        ).pack(side="left", padx=8)

        row4 = tk.Frame(frame_opts)
        row4.pack(fill="x", padx=8, pady=5)
        tk.Label(row4, text="Frame names").pack(side="left")
        tk.Entry(row4, textvariable=self.frame_names_var).pack(side="left", fill="x", expand=True, padx=8)
        tk.Label(row4, text="(optional, comma-separated)").pack(side="left")

        row5 = tk.Frame(frame_opts)
        row5.pack(fill="x", padx=8, pady=5)
        self.tv_safe_var = tk.BooleanVar(value=True)
        tk.Checkbutton(row5, text="TV-safe export", variable=self.tv_safe_var, command=self.update_preview).pack(
            side="left"
        )
        tk.Label(row5, text="Desat").pack(side="left", padx=(12, 0))
        self.tv_desat_var = tk.StringVar(value="0.25")
        tk.Entry(row5, textvariable=self.tv_desat_var, width=6).pack(side="left", padx=4)
        tk.Label(row5, text="Blur").pack(side="left", padx=(12, 0))
        self.tv_blur_var = tk.StringVar(value="1")
        tk.Entry(row5, textvariable=self.tv_blur_var, width=6).pack(side="left", padx=4)

        frame_run = tk.Frame(root)
        frame_run.pack(fill="x", padx=10, pady=8)
        tk.Button(frame_run, text="Generate Header", height=2, command=self.generate).pack(
            side="left", padx=(0, 8)
        )
        tk.Button(frame_run, text="Open Output Folder", command=self.open_output_folder).pack(side="left")

        frame_log = tk.LabelFrame(root, text="Log")
        frame_log.pack(fill="both", expand=False, padx=10, pady=(0, 10))
        self.log = tk.Text(frame_log, height=9)
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
        if meta.get("type") != "sprites_project_v1":
            raise ValueError("JSON is not a sprites project.")
        pngs = meta.get("pngs", [])
        if not isinstance(pngs, list):
            raise ValueError("Invalid png list in metadata.")
        self.png_paths = [str(p) for p in pngs]
        self._refresh_list()
        if "out" in meta:
            self.out_var.set(str(meta["out"]))
        if "name" in meta:
            self.name_var.set(str(meta["name"]))
        if "origin" in meta:
            self.origin_var.set(str(meta["origin"]))
        if meta.get("origin_x") is not None:
            self.origin_x_var.set(str(meta["origin_x"]))
        else:
            self.origin_x_var.set("")
        if meta.get("origin_y") is not None:
            self.origin_y_var.set(str(meta["origin_y"]))
        else:
            self.origin_y_var.set("")
        if "levels" in meta:
            self.levels_var.set(str(meta["levels"]))
        if "color_mode" in meta:
            self.color_mode_var.set(str(meta["color_mode"]))
        if "transparency" in meta:
            self.trans_var.set(str(meta["transparency"]))
        if "alpha_threshold" in meta:
            self.alpha_var.set(str(meta["alpha_threshold"]))
        if "tv_safe" in meta:
            self.tv_safe_var.set(bool(meta["tv_safe"]))
        if "tv_desat" in meta:
            self.tv_desat_var.set(str(meta["tv_desat"]))
        if "tv_blur" in meta:
            self.tv_blur_var.set(str(meta["tv_blur"]))
        if "frame_names" in meta and isinstance(meta["frame_names"], list):
            self.frame_names_var.set(", ".join(str(x) for x in meta["frame_names"]))
        self.update_preview()

    def _load_meta_from_header(self, path: str):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        m = re.search(r"// ASSET_META:\s*(\{.*\})", text)
        if not m:
            raise ValueError("Header has no ASSET_META. Re-export with latest converter.")
        meta = json.loads(m.group(1))
        tmp_path = os.path.join(PROJECT_ROOT, ".tmp_sprites_meta_load.json")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        self._load_meta_json(tmp_path)
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    def load_export(self):
        path = filedialog.askopenfilename(
            title="Load sprites export (.json or .h)",
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
            fname = ""
            if self.frame_names_var.get().strip():
                names = [x.strip() for x in self.frame_names_var.get().split(",")]
                if idx < len(names):
                    fname = names[idx]
            info = f"{os.path.basename(path)}\n{w}x{h}\nmode: {self.preview_mode_var.get()}"
            if fname:
                info += f"\nframe: {fname}"
            self.preview_info.configure(text=info)
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

    def _checker(self, x: int, y: int) -> tuple[int, int, int]:
        if ((x >> 3) ^ (y >> 3)) & 1:
            return (84, 84, 84)
        return (52, 52, 52)

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
        alpha_thr = int(self.alpha_var.get().strip() or "8")
        trans_idx = int(self.trans_var.get().strip() or "255")
        avoid = trans_idx if mode in ("atari", "nes") else None

        img = tk.PhotoImage(width=out_w, height=out_h)
        for oy in range(out_h):
            sy = min(h - 1, oy * factor)
            row_parts = []
            row_base = sy * w
            for ox in range(out_w):
                sx = min(w - 1, ox * factor)
                r, g, b, a = rgba[row_base + sx]
                if a <= alpha_thr:
                    cr, cg, cb = self._checker(ox, oy)
                elif mode == "gray":
                    lv = rgba_to_gray_level(r, g, b, levels)
                    v = int(round((lv / max(1, levels)) * 255))
                    cr, cg, cb = v, v, v
                elif mode == "atari":
                    idx = self._atari_quant.rgb_to_index(r, g, b, avoid_index=avoid)
                    cr, cg, cb = self._atari_palette[idx]
                else:  # nes
                    idx = self._nes_quant.rgb_to_index(r, g, b, avoid_index=avoid)
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
        # Downscale first if image is larger than preview area.
        down = max(1, int(math.ceil(max(w / max_w, h / max_h))))
        if down > 1:
            img = img.subsample(down, down)
            w = img.width()
            h = img.height()
        # Then upscale small images so sprites are readable.
        up = max(1, min(max_w // max(1, w), max_h // max(1, h)))
        if up > 1:
            img = img.zoom(up, up)
        return img

    def browse_output(self):
        path = filedialog.asksaveasfilename(
            title="Output header file",
            defaultextension=".h",
            filetypes=[("Header files", "*.h"), ("All files", "*.*")],
            initialfile=os.path.basename(self.out_var.get()) if self.out_var.get() else "my_sprites.h",
        )
        if path:
            self.out_var.set(path)

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

        script_path = os.path.join(os.path.dirname(__file__), "png_to_sprites.py")
        cmd = [sys.executable, script_path]
        cmd.extend(self.png_paths)
        cmd.extend(["--out", out_abs, "--name", name])
        cmd.extend(["--origin", self.origin_var.get().strip()])
        cmd.extend(["--levels", self.levels_var.get().strip()])
        cmd.extend(["--color-mode", self.color_mode_var.get().strip()])
        cmd.extend(["--transparency", self.trans_var.get().strip()])
        cmd.extend(["--alpha-threshold", self.alpha_var.get().strip()])
        if self.tv_safe_var.get():
            cmd.append("--tv-safe")
        cmd.extend(["--tv-desat", self.tv_desat_var.get().strip() or "0.25"])
        cmd.extend(["--tv-blur", self.tv_blur_var.get().strip() or "1"])
        frame_names = self.frame_names_var.get().strip()
        if frame_names:
            cmd.extend(["--frame-names", frame_names])

        ox = self.origin_x_var.get().strip()
        oy = self.origin_y_var.get().strip()
        if ox and oy:
            cmd.extend(["--origin-x", ox, "--origin-y", oy])
        elif ox or oy:
            messagebox.showwarning("Origin override", "Set both Origin X and Origin Y, or leave both empty.")
            return

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
    app = PngToSpritesGui()
    app.mainloop()


if __name__ == "__main__":
    main()
