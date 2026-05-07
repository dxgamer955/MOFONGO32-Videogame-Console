#!/usr/bin/env python3
"""
GUI para crear/flashear SPIFFS del ESP32.

Toma una carpeta como data/ y genera spiffs.bin sin escribir comandos largos.
En este proyecto se usa para poner game.masa en el ESP32 de logica.
"""

import os
import re
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _find_mkspiffs() -> str:
    base = os.path.expanduser(r"~\AppData\Local\Arduino15\packages\esp32\tools\mkspiffs")
    if not os.path.isdir(base):
        return ""
    best = ""
    best_key = ()
    for root, _dirs, files in os.walk(base):
        for name in files:
            if name.lower() != "mkspiffs.exe":
                continue
            path = os.path.join(root, name)
            ver = os.path.basename(os.path.dirname(path))
            key = tuple(int(p) if p.isdigit() else 0 for p in re.split(r"[^\d]+", ver) if p != "")
            if key >= best_key:
                best_key = key
                best = path
    return best


def _parse_size(text: str) -> int:
    s = text.strip().lower()
    if not s:
        raise ValueError("Empty size")
    mult = 1
    if s.endswith("k"):
        mult = 1024
        s = s[:-1]
    elif s.endswith("m"):
        mult = 1024 * 1024
        s = s[:-1]
    if s.startswith("0x"):
        val = int(s, 16)
    else:
        val = int(s, 10)
    if val <= 0:
        raise ValueError("Size must be > 0")
    return val * mult


def _parse_partitions(csv_path: str):
    spiffs_size = None
    spiffs_offset = None
    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f.readlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            cols = [c.strip() for c in line.split(",")]
            if len(cols) < 5:
                continue
            p_type = cols[1].lower()
            p_sub = cols[2].lower()
            if p_type == "data" and p_sub in ("spiffs", "fatfs"):
                spiffs_offset = cols[3]
                spiffs_size = cols[4]
                break
    return spiffs_offset, spiffs_size


def _list_serial_ports():
    ports = []
    try:
        import serial.tools.list_ports  # type: ignore

        for p in serial.tools.list_ports.comports():
            ports.append(p.device)
    except Exception:
        pass
    if not ports and os.name == "nt":
        for i in range(1, 33):
            ports.append(f"COM{i}")
    return ports


class SpiffsBuilderGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mofongo SPIFFS Builder")
        self.geometry("760x520")
        self.minsize(720, 480)

        self.mkspiffs_var = tk.StringVar(value=_find_mkspiffs())
        self.root_var = tk.StringVar(value=PROJECT_ROOT)
        self.spiffs_dir_var = tk.StringVar(value=os.path.join(PROJECT_ROOT, "spiffs"))
        self.out_bin_var = tk.StringVar(value=os.path.join(PROJECT_ROOT, "spiffs.bin"))
        self.size_var = tk.StringVar(value="0xF0000")
        self.block_var = tk.StringVar(value="4096")
        self.page_var = tk.StringVar(value="256")
        self.csv_var = tk.StringVar(value="")
        self.offset_var = tk.StringVar(value="")
        ports = _list_serial_ports()
        default_port = ports[0] if ports else ""
        self.port_var = tk.StringVar(value=default_port)
        self.baud_var = tk.StringVar(value="921600")
        self._ports = ports
        self._port_menu = None

        self._build_ui()

    def _build_ui(self):
        root = self

        frame_paths = tk.LabelFrame(root, text="Paths")
        frame_paths.pack(fill="x", padx=10, pady=8)

        row = tk.Frame(frame_paths)
        row.pack(fill="x", padx=8, pady=4)
        tk.Label(row, text="Project root").pack(side="left")
        tk.Entry(row, textvariable=self.root_var).pack(side="left", fill="x", expand=True, padx=8)
        tk.Button(row, text="Browse", command=self.browse_root).pack(side="left")

        row = tk.Frame(frame_paths)
        row.pack(fill="x", padx=8, pady=4)
        tk.Label(row, text="SPIFFS folder").pack(side="left")
        tk.Entry(row, textvariable=self.spiffs_dir_var).pack(side="left", fill="x", expand=True, padx=8)
        tk.Button(row, text="Browse", command=self.browse_spiffs_dir).pack(side="left")

        row = tk.Frame(frame_paths)
        row.pack(fill="x", padx=8, pady=4)
        tk.Label(row, text="Output bin").pack(side="left")
        tk.Entry(row, textvariable=self.out_bin_var).pack(side="left", fill="x", expand=True, padx=8)
        tk.Button(row, text="Browse", command=self.browse_out_bin).pack(side="left")

        row = tk.Frame(frame_paths)
        row.pack(fill="x", padx=8, pady=4)
        tk.Label(row, text="mkspiffs.exe").pack(side="left")
        tk.Entry(row, textvariable=self.mkspiffs_var).pack(side="left", fill="x", expand=True, padx=8)
        tk.Button(row, text="Browse", command=self.browse_mkspiffs).pack(side="left")

        frame_opts = tk.LabelFrame(root, text="Partition")
        frame_opts.pack(fill="x", padx=10, pady=6)

        row = tk.Frame(frame_opts)
        row.pack(fill="x", padx=8, pady=4)
        tk.Label(row, text="Partition CSV (optional)").pack(side="left")
        tk.Entry(row, textvariable=self.csv_var).pack(side="left", fill="x", expand=True, padx=8)
        tk.Button(row, text="Browse", command=self.browse_csv).pack(side="left")
        tk.Button(row, text="Auto Fill", command=self.auto_fill_from_csv).pack(side="left", padx=(6, 0))

        row = tk.Frame(frame_opts)
        row.pack(fill="x", padx=8, pady=4)
        tk.Label(row, text="SPIFFS size").pack(side="left")
        tk.Entry(row, textvariable=self.size_var, width=14).pack(side="left", padx=6)
        tk.Label(row, text="Offset").pack(side="left", padx=(12, 0))
        tk.Entry(row, textvariable=self.offset_var, width=12, state="readonly").pack(side="left", padx=6)
        tk.Label(row, text="Block").pack(side="left", padx=(12, 0))
        tk.Entry(row, textvariable=self.block_var, width=8).pack(side="left", padx=4)
        tk.Label(row, text="Page").pack(side="left", padx=(12, 0))
        tk.Entry(row, textvariable=self.page_var, width=8).pack(side="left", padx=4)

        frame_actions = tk.Frame(root)
        frame_actions.pack(fill="x", padx=10, pady=6)
        tk.Button(frame_actions, text="Copy .masa to SPIFFS as game.masa", command=self.copy_masa).pack(
            side="left", padx=(0, 8)
        )
        tk.Button(frame_actions, text="Build spiffs.bin", height=2, command=self.build_spiffs).pack(side="left")

        frame_flash = tk.LabelFrame(root, text="Flash (esptool)")
        frame_flash.pack(fill="x", padx=10, pady=6)
        row = tk.Frame(frame_flash)
        row.pack(fill="x", padx=8, pady=4)
        tk.Label(row, text="Port").pack(side="left")
        self._port_menu = tk.OptionMenu(row, self.port_var, *(self._ports or [""]))
        self._port_menu.pack(side="left", padx=6)
        tk.Button(row, text="Refresh", command=self.refresh_ports).pack(side="left", padx=(2, 0))
        tk.Button(row, text="Test ESP32", command=self.test_esp32).pack(side="left", padx=(6, 0))
        tk.Label(row, text="Baud").pack(side="left", padx=(12, 0))
        tk.Entry(row, textvariable=self.baud_var, width=10).pack(side="left", padx=6)
        tk.Label(row, text="Offset").pack(side="left", padx=(12, 0))
        tk.Entry(row, textvariable=self.offset_var, width=12, state="readonly").pack(side="left", padx=6)
        tk.Button(row, text="Flash SPIFFS", command=self.flash_spiffs).pack(side="left", padx=(8, 0))

        frame_log = tk.LabelFrame(root, text="Log")
        frame_log.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log = tk.Text(frame_log, height=12)
        self.log.pack(fill="both", expand=True, padx=8, pady=8)

    def log_write(self, text: str):
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.update_idletasks()

    def refresh_ports(self):
        ports = _list_serial_ports()
        self._ports = ports
        if not self._port_menu:
            return
        menu = self._port_menu["menu"]
        menu.delete(0, "end")
        if not ports:
            menu.add_command(label="(none)", command=lambda: self.port_var.set(""))
            self.port_var.set("")
            messagebox.showinfo("Ports", "No serial ports detected.")
            return
        for p in ports:
            menu.add_command(label=p, command=lambda v=p: self.port_var.set(v))
        self.port_var.set(ports[0])
        messagebox.showinfo("Ports", "Ports refreshed.")

    def test_esp32(self):
        port = self.port_var.get().strip()
        if not port:
            messagebox.showwarning("Missing port", "Select a serial port first.")
            return
        cmd = [
            sys.executable,
            "-m",
            "esptool",
            "--chip",
            "esp32",
            "--port",
            port,
            "chip-id",
        ]
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
                self.log_write("ESP32 OK.")
                messagebox.showinfo("Success", "ESP32 responded. Port is OK.")
            else:
                messagebox.showerror("Error", "ESP32 did not respond. Check port and boot mode.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to run esptool:\n{e}")

    def browse_root(self):
        path = filedialog.askdirectory(title="Select project root", initialdir=self.root_var.get() or PROJECT_ROOT)
        if path:
            self.root_var.set(path)
            self.spiffs_dir_var.set(os.path.join(path, "spiffs"))
            self.out_bin_var.set(os.path.join(path, "spiffs.bin"))

    def browse_spiffs_dir(self):
        path = filedialog.askdirectory(
            title="Select SPIFFS folder", initialdir=self.spiffs_dir_var.get() or PROJECT_ROOT
        )
        if path:
            self.spiffs_dir_var.set(path)

    def browse_out_bin(self):
        path = filedialog.asksaveasfilename(
            title="Output spiffs.bin",
            defaultextension=".bin",
            filetypes=[("BIN files", "*.bin"), ("All files", "*.*")],
            initialfile=os.path.basename(self.out_bin_var.get()) if self.out_bin_var.get() else "spiffs.bin",
        )
        if path:
            self.out_bin_var.set(path)

    def browse_mkspiffs(self):
        path = filedialog.askopenfilename(
            title="Select mkspiffs.exe",
            filetypes=[("mkspiffs", "mkspiffs.exe"), ("All files", "*.*")],
        )
        if path:
            self.mkspiffs_var.set(path)

    def browse_csv(self):
        path = filedialog.askopenfilename(
            title="Select partition CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self.csv_var.set(path)

    def auto_fill_from_csv(self):
        path = self.csv_var.get().strip()
        if not path:
            messagebox.showwarning("Missing CSV", "Select a partition CSV first.")
            return
        try:
            offset, size = _parse_partitions(path)
            if not size:
                raise ValueError("No SPIFFS partition found in CSV.")
            self.size_var.set(size)
            self.offset_var.set(offset or "")
            self.log_write(f"Loaded SPIFFS from CSV: size={size} offset={offset}")
        except Exception as e:
            messagebox.showerror("CSV parse failed", str(e))

    def copy_masa(self):
        spiffs_dir = self.spiffs_dir_var.get().strip()
        if not spiffs_dir:
            messagebox.showwarning("Missing folder", "Set SPIFFS folder.")
            return
        path = filedialog.askopenfilename(
            title="Select .masa file",
            filetypes=[("MASA files", "*.masa"), ("All files", "*.*")],
        )
        if not path:
            return
        os.makedirs(spiffs_dir, exist_ok=True)
        dst = os.path.join(spiffs_dir, "game.masa")
        shutil.copy2(path, dst)
        self.log_write(f"Copied: {path}")
        self.log_write(f" -> {dst}")

    def build_spiffs(self):
        mkspiffs = self.mkspiffs_var.get().strip()
        spiffs_dir = self.spiffs_dir_var.get().strip()
        out_bin = self.out_bin_var.get().strip()
        if not mkspiffs or not os.path.isfile(mkspiffs):
            messagebox.showwarning("Missing mkspiffs", "Set mkspiffs.exe path.")
            return
        if not spiffs_dir:
            messagebox.showwarning("Missing folder", "Set SPIFFS folder.")
            return
        os.makedirs(spiffs_dir, exist_ok=True)
        if not out_bin:
            messagebox.showwarning("Missing output", "Set output bin path.")
            return
        try:
            size = _parse_size(self.size_var.get())
            block = int(self.block_var.get().strip() or "4096")
            page = int(self.page_var.get().strip() or "256")
        except Exception as e:
            messagebox.showerror("Invalid size", str(e))
            return

        cmd = [
            mkspiffs,
            "-c",
            spiffs_dir,
            "-b",
            str(block),
            "-p",
            str(page),
            "-s",
            str(size),
            out_bin,
        ]

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
                messagebox.showinfo("Success", f"SPIFFS image generated:\n{os.path.abspath(out_bin)}")
            else:
                messagebox.showerror("Error", "mkspiffs failed. Check log.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to run mkspiffs:\n{e}")

    def flash_spiffs(self):
        out_bin = self.out_bin_var.get().strip()
        if not out_bin or not os.path.isfile(out_bin):
            messagebox.showwarning("Missing bin", "Build spiffs.bin first.")
            return
        port = self.port_var.get().strip()
        baud = self.baud_var.get().strip()
        offset = self.offset_var.get().strip()
        if not offset:
            messagebox.showwarning("Missing offset", "Load partition CSV and Auto Fill to get SPIFFS offset.")
            return
        if not port:
            messagebox.showwarning("Missing port", "Set serial port (e.g. COM9).")
            return
        if not baud:
            baud = "921600"
            self.baud_var.set(baud)

        cmd = [
            sys.executable,
            "-m",
            "esptool",
            "--chip",
            "esp32",
            "--port",
            port,
            "--baud",
            baud,
            "write-flash",
            offset,
            out_bin,
        ]

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
                messagebox.showinfo("Success", "SPIFFS flashed successfully.")
            else:
                messagebox.showerror("Error", "esptool failed. Check log.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to run esptool:\n{e}")


def main():
    app = SpiffsBuilderGui()
    app.mainloop()


if __name__ == "__main__":
    main()
