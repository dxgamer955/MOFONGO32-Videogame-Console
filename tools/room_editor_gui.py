#!/usr/bin/env python3
"""
Room Editor GUI (GameMaker-like) for ESP32 scene layout.

Features:
- 320x200 room canvas (scaled preview)
- Load sprite export metadata (.json/.h from png_to_sprites)
- Load background export metadata (.json/.h from png_to_backgrounds)
- Place, move, select, and edit objects visually
- Save/load room as JSON
- Export C header with object/background data
"""

import json
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


ROOM_W = 320
ROOM_H = 200
CANVAS_SCALE = 2

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load_asset_meta(path: str, expected_type: str):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        with open(path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    elif ext == ".h":
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
        m = re.search(r"// ASSET_META:\s*(\{.*\})", txt)
        if not m:
            raise ValueError("Header has no ASSET_META.")
        meta = json.loads(m.group(1))
    else:
        raise ValueError("Unsupported file type.")

    if not isinstance(meta, dict) or meta.get("type") != expected_type:
        raise ValueError(f"Invalid metadata type. Expected {expected_type}.")
    return meta


class RoomEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ESP32 Room Editor")
        self.geometry("1280x760")
        self.minsize(1100, 680)

        self.sprites_meta = None
        self.backgrounds_meta = None
        self.sprite_images = []
        self.bg_images = []
        self.canvas_bg = None

        self.room = {
            "name": "room0",
            "width": ROOM_W,
            "height": ROOM_H,
            "background_index": -1,
            "objects": [],
        }
        self.next_obj_id = 1
        self.selected_obj_id = None
        self.dragging = False

        self._build_ui()
        self.redraw()

    def _build_ui(self):
        root = self
        top = tk.Frame(root)
        top.pack(fill="x", padx=8, pady=6)

        tk.Button(top, text="Load Sprites", command=self.load_sprites_meta).pack(side="left", padx=4)
        tk.Button(top, text="Load Backgrounds", command=self.load_backgrounds_meta).pack(side="left", padx=4)
        tk.Button(top, text="New Room", command=self.new_room).pack(side="left", padx=4)
        tk.Button(top, text="Load Room", command=self.load_room).pack(side="left", padx=4)
        tk.Button(top, text="Save Room JSON", command=self.save_room).pack(side="left", padx=4)
        tk.Button(top, text="Export Room Header", command=self.export_header).pack(side="left", padx=4)

        body = tk.Frame(root)
        body.pack(fill="both", expand=True, padx=8, pady=6)

        left = tk.LabelFrame(body, text="Scene")
        left.pack(side="left", fill="y", padx=(0, 8))

        tk.Label(left, text="Room name").pack(anchor="w", padx=8, pady=(8, 2))
        self.room_name_var = tk.StringVar(value=self.room["name"])
        tk.Entry(left, textvariable=self.room_name_var, width=28).pack(anchor="w", padx=8)

        tk.Label(left, text="Background").pack(anchor="w", padx=8, pady=(8, 2))
        self.bg_var = tk.StringVar(value="none")
        self.bg_combo = ttk.Combobox(left, textvariable=self.bg_var, state="readonly", width=24)
        self.bg_combo.pack(anchor="w", padx=8)
        self.bg_combo.bind("<<ComboboxSelected>>", lambda _e: self.on_bg_change())

        tk.Label(left, text="Sprite Frame").pack(anchor="w", padx=8, pady=(8, 2))
        self.frame_list = tk.Listbox(left, width=30, height=12, exportselection=False)
        self.frame_list.pack(anchor="w", padx=8)

        tk.Button(left, text="Add Object", command=self.add_object).pack(anchor="w", padx=8, pady=6)

        tk.Label(left, text="Objects").pack(anchor="w", padx=8, pady=(8, 2))
        self.obj_list = tk.Listbox(left, width=30, height=12, exportselection=False)
        self.obj_list.pack(anchor="w", padx=8)
        self.obj_list.bind("<<ListboxSelect>>", lambda _e: self.on_object_select_from_list())
        tk.Button(left, text="Delete Object", command=self.delete_selected_object).pack(anchor="w", padx=8, pady=6)

        props = tk.LabelFrame(left, text="Selected Object")
        props.pack(fill="x", padx=8, pady=(8, 8))

        self.obj_x = tk.StringVar(value="0")
        self.obj_y = tk.StringVar(value="0")
        self.obj_frame = tk.StringVar(value="0")
        self.obj_mode = tk.StringVar(value="normal")
        self.obj_angle = tk.StringVar(value="0")
        self.obj_scale = tk.StringVar(value="1.0")

        self._prop_row(props, "X", self.obj_x)
        self._prop_row(props, "Y", self.obj_y)
        self._prop_row(props, "Frame", self.obj_frame)
        self._prop_row(props, "Mode", self.obj_mode, combo=["normal", "rotated", "scaled"])
        self._prop_row(props, "Angle", self.obj_angle)
        self._prop_row(props, "Scale", self.obj_scale)
        tk.Button(props, text="Apply Props", command=self.apply_props).pack(anchor="w", padx=6, pady=6)

        right = tk.LabelFrame(body, text="Room View (320x200)")
        right.pack(side="left", fill="both", expand=True)

        self.canvas = tk.Canvas(
            right,
            width=ROOM_W * CANVAS_SCALE,
            height=ROOM_H * CANVAS_SCALE,
            bg="#000",
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True, padx=8, pady=8)
        self.canvas.bind("<Button-1>", self.on_canvas_down)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_up)

        self.status = tk.Label(root, text="Load sprites/backgrounds metadata to start.")
        self.status.pack(fill="x", padx=8, pady=(0, 8))

    def _prop_row(self, parent, label, var, combo=None):
        row = tk.Frame(parent)
        row.pack(fill="x", padx=6, pady=2)
        tk.Label(row, text=label, width=8, anchor="w").pack(side="left")
        if combo:
            cb = ttk.Combobox(row, textvariable=var, values=combo, state="readonly", width=14)
            cb.pack(side="left", fill="x", expand=True)
        else:
            tk.Entry(row, textvariable=var, width=18).pack(side="left", fill="x", expand=True)

    def set_status(self, txt):
        self.status.configure(text=txt)

    def load_sprites_meta(self):
        path = filedialog.askopenfilename(
            title="Load sprites metadata (.json/.h)",
            filetypes=[("Supported", "*.json *.h"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            meta = load_asset_meta(path, "sprites_project_v1")
            self.sprites_meta = meta
            self.sprite_images = []
            for p in meta.get("pngs", []):
                try:
                    img = tk.PhotoImage(file=p)
                except Exception:
                    img = None
                self.sprite_images.append(img)
            self.refresh_frame_list()
            self.set_status(f"Loaded sprites: {os.path.basename(path)}")
            self.redraw()
        except Exception as e:
            messagebox.showerror("Load failed", str(e))

    def load_backgrounds_meta(self):
        path = filedialog.askopenfilename(
            title="Load backgrounds metadata (.json/.h)",
            filetypes=[("Supported", "*.json *.h"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            meta = load_asset_meta(path, "backgrounds_project_v1")
            self.backgrounds_meta = meta
            self.bg_images = []
            for p in meta.get("pngs", []):
                try:
                    img = tk.PhotoImage(file=p)
                except Exception:
                    img = None
                self.bg_images.append(img)
            self.refresh_bg_combo()
            self.set_status(f"Loaded backgrounds: {os.path.basename(path)}")
            self.redraw()
        except Exception as e:
            messagebox.showerror("Load failed", str(e))

    def refresh_frame_list(self):
        self.frame_list.delete(0, tk.END)
        if not self.sprites_meta:
            return
        names = self.sprites_meta.get("frame_names", [])
        for i, n in enumerate(names):
            self.frame_list.insert(tk.END, f"[{i}] {n}")
        if names:
            self.frame_list.selection_set(0)

    def refresh_bg_combo(self):
        vals = ["none"]
        if self.backgrounds_meta:
            for i, p in enumerate(self.backgrounds_meta.get("pngs", [])):
                vals.append(f"{i}: {os.path.basename(p)}")
        self.bg_combo["values"] = vals
        if self.room["background_index"] < 0:
            self.bg_var.set("none")
        else:
            i = self.room["background_index"]
            self.bg_var.set(vals[i + 1] if i + 1 < len(vals) else "none")

    def on_bg_change(self):
        v = self.bg_var.get()
        if v == "none":
            self.room["background_index"] = -1
        else:
            self.room["background_index"] = int(v.split(":")[0])
        self.redraw()

    def add_object(self):
        if not self.sprites_meta:
            messagebox.showwarning("Missing sprites", "Load sprites metadata first.")
            return
        sel = list(self.frame_list.curselection())
        if not sel:
            messagebox.showwarning("No frame", "Select a frame.")
            return
        frame = sel[0]
        obj = {
            "id": self.next_obj_id,
            "name": f"obj_{self.next_obj_id}",
            "frame": frame,
            "x": ROOM_W // 2,
            "y": ROOM_H // 2,
            "mode": "normal",
            "angle": 0.0,
            "scale": 1.0,
            "visible": True,
        }
        self.next_obj_id += 1
        self.room["objects"].append(obj)
        self.selected_obj_id = obj["id"]
        self.refresh_obj_list()
        self.pull_props_from_selected()
        self.redraw()

    def refresh_obj_list(self):
        self.obj_list.delete(0, tk.END)
        for o in self.room["objects"]:
            self.obj_list.insert(tk.END, f"#{o['id']} f{o['frame']} ({o['x']},{o['y']}) {o['mode']}")
        if self.selected_obj_id is not None:
            for i, o in enumerate(self.room["objects"]):
                if o["id"] == self.selected_obj_id:
                    self.obj_list.selection_set(i)
                    break

    def get_selected_object(self):
        if self.selected_obj_id is None:
            return None
        for o in self.room["objects"]:
            if o["id"] == self.selected_obj_id:
                return o
        return None

    def on_object_select_from_list(self):
        sel = list(self.obj_list.curselection())
        if not sel:
            return
        idx = sel[0]
        if idx < len(self.room["objects"]):
            self.selected_obj_id = self.room["objects"][idx]["id"]
            self.pull_props_from_selected()
            self.redraw()

    def delete_selected_object(self):
        if self.selected_obj_id is None:
            return
        self.room["objects"] = [o for o in self.room["objects"] if o["id"] != self.selected_obj_id]
        self.selected_obj_id = None
        self.refresh_obj_list()
        self.redraw()

    def pull_props_from_selected(self):
        o = self.get_selected_object()
        if not o:
            return
        self.obj_x.set(str(o["x"]))
        self.obj_y.set(str(o["y"]))
        self.obj_frame.set(str(o["frame"]))
        self.obj_mode.set(str(o["mode"]))
        self.obj_angle.set(str(o["angle"]))
        self.obj_scale.set(str(o["scale"]))

    def apply_props(self):
        o = self.get_selected_object()
        if not o:
            return
        try:
            o["x"] = max(0, min(ROOM_W - 1, int(self.obj_x.get())))
            o["y"] = max(0, min(ROOM_H - 1, int(self.obj_y.get())))
            o["frame"] = max(0, int(self.obj_frame.get()))
            o["mode"] = self.obj_mode.get()
            o["angle"] = float(self.obj_angle.get())
            o["scale"] = max(0.01, float(self.obj_scale.get()))
        except Exception:
            messagebox.showerror("Invalid", "Invalid object property value.")
            return
        self.refresh_obj_list()
        self.redraw()

    def canvas_to_room(self, x, y):
        return int(x / CANVAS_SCALE), int(y / CANVAS_SCALE)

    def room_to_canvas(self, x, y):
        return int(x * CANVAS_SCALE), int(y * CANVAS_SCALE)

    def on_canvas_down(self, event):
        rx, ry = self.canvas_to_room(event.x, event.y)
        hit = None
        for o in reversed(self.room["objects"]):
            if abs(o["x"] - rx) <= 8 and abs(o["y"] - ry) <= 8:
                hit = o
                break
        if hit:
            self.selected_obj_id = hit["id"]
            self.dragging = True
            self.pull_props_from_selected()
            self.refresh_obj_list()
            self.redraw()

    def on_canvas_drag(self, event):
        if not self.dragging:
            return
        o = self.get_selected_object()
        if not o:
            return
        rx, ry = self.canvas_to_room(event.x, event.y)
        o["x"] = max(0, min(ROOM_W - 1, rx))
        o["y"] = max(0, min(ROOM_H - 1, ry))
        self.pull_props_from_selected()
        self.refresh_obj_list()
        self.redraw()

    def on_canvas_up(self, _event):
        self.dragging = False

    def new_room(self):
        self.room = {
            "name": "room0",
            "width": ROOM_W,
            "height": ROOM_H,
            "background_index": -1,
            "objects": [],
        }
        self.next_obj_id = 1
        self.selected_obj_id = None
        self.room_name_var.set("room0")
        self.bg_var.set("none")
        self.refresh_obj_list()
        self.redraw()

    def save_room(self):
        self.room["name"] = self.room_name_var.get().strip() or "room0"
        out = filedialog.asksaveasfilename(
            title="Save room JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"{self.room['name']}.json",
        )
        if not out:
            return
        with open(out, "w", encoding="utf-8") as f:
            json.dump(self.room, f, indent=2)
        self.set_status(f"Saved room: {out}")

    def load_room(self):
        path = filedialog.askopenfilename(
            title="Load room JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                room = json.load(f)
            if not isinstance(room, dict) or "objects" not in room:
                raise ValueError("Invalid room format.")
            self.room = room
            self.room.setdefault("width", ROOM_W)
            self.room.setdefault("height", ROOM_H)
            self.room.setdefault("background_index", -1)
            self.room.setdefault("name", "room0")
            self.room_name_var.set(self.room["name"])
            self.next_obj_id = 1 + max([o.get("id", 0) for o in self.room["objects"]] + [0])
            self.selected_obj_id = None
            self.refresh_bg_combo()
            self.refresh_obj_list()
            self.redraw()
            self.set_status(f"Loaded room: {path}")
        except Exception as e:
            messagebox.showerror("Load failed", str(e))

    def export_header(self):
        self.room["name"] = self.room_name_var.get().strip() or "room0"
        out = filedialog.asksaveasfilename(
            title="Export room header",
            defaultextension=".h",
            filetypes=[("Header files", "*.h"), ("All files", "*.*")],
            initialfile=f"{self.room['name']}.h",
        )
        if not out:
            return

        guard = re.sub(r"[^0-9A-Za-z_]", "_", os.path.basename(out)).upper() + "_"
        name = re.sub(r"[^0-9A-Za-z_]", "_", self.room["name"])
        lines = []
        lines.append(f"#ifndef {guard}")
        lines.append(f"#define {guard}")
        lines.append("")
        lines.append("struct RoomObjectDef")
        lines.append("{")
        lines.append("  int frame;")
        lines.append("  int x;")
        lines.append("  int y;")
        lines.append("  int mode; // 0=normal,1=rotated,2=scaled")
        lines.append("  float angle;")
        lines.append("  float scale;")
        lines.append("};")
        lines.append("")

        mode_map = {"normal": 0, "rotated": 1, "scaled": 2}
        lines.append(f"const int {name}BackgroundIndex = {int(self.room.get('background_index', -1))};")
        lines.append(f"const RoomObjectDef {name}Objects[] = {{")
        for o in self.room["objects"]:
            m = mode_map.get(o.get("mode", "normal"), 0)
            lines.append(
                f"  {{{int(o.get('frame', 0))}, {int(o.get('x', 0))}, {int(o.get('y', 0))}, {m}, "
                f"{float(o.get('angle', 0.0)):.3f}f, {float(o.get('scale', 1.0)):.3f}f}},"
            )
        lines.append("};")
        lines.append(f"const int {name}ObjectCount = sizeof({name}Objects) / sizeof({name}Objects[0]);")
        lines.append("")
        lines.append(f"#endif // {guard}")

        with open(out, "w", encoding="ascii") as f:
            f.write("\n".join(lines))
        self.set_status(f"Exported header: {out}")

    def redraw(self):
        self.canvas.delete("all")
        self.canvas.create_rectangle(0, 0, ROOM_W * CANVAS_SCALE, ROOM_H * CANVAS_SCALE, fill="#111", outline="")

        bg_idx = int(self.room.get("background_index", -1))
        if self.bg_images and 0 <= bg_idx < len(self.bg_images):
            img = self.bg_images[bg_idx]
            if img is not None:
                try:
                    self.canvas_bg = img.zoom(CANVAS_SCALE, CANVAS_SCALE)
                    self.canvas.create_image(0, 0, image=self.canvas_bg, anchor="nw")
                except Exception:
                    pass

        for o in self.room["objects"]:
            x, y = self.room_to_canvas(o["x"], o["y"])
            frame = int(o.get("frame", 0))

            drawn = False
            if self.sprite_images and 0 <= frame < len(self.sprite_images):
                img = self.sprite_images[frame]
                if img is not None:
                    try:
                        simg = img.zoom(CANVAS_SCALE, CANVAS_SCALE)
                        self.canvas.create_image(x, y, image=simg, anchor="center")
                        # Keep tkinter image reference alive on canvas item.
                        self.canvas.image = getattr(self.canvas, "image", [])
                        self.canvas.image.append(simg)
                        drawn = True
                    except Exception:
                        pass

            if not drawn:
                self.canvas.create_oval(x - 8, y - 8, x + 8, y + 8, fill="#ffd54f", outline="#222")
                self.canvas.create_text(x, y - 14, text=str(frame), fill="#fff")

            if o["id"] == self.selected_obj_id:
                self.canvas.create_rectangle(x - 12, y - 12, x + 12, y + 12, outline="#00e5ff")

        self.canvas.create_rectangle(
            0, 0, ROOM_W * CANVAS_SCALE, ROOM_H * CANVAS_SCALE, outline="#666", width=2
        )


def main():
    app = RoomEditor()
    app.mainloop()


if __name__ == "__main__":
    main()
