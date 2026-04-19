"""
dashboard.py — Interfaz gráfica del operador (tkinter).

Panel principal con tres secciones:
  1. Estado del sistema  (sensores activos, operadores, uptime)
  2. Tabla de sensores   (actualización en tiempo real)
  3. Panel de alertas    (con timestamps y descripción, auto-scroll)

Uso:
    python3 dashboard.py
    python3 dashboard.py --host monitor.iot-monitor.local --port 9000
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import time
import logging
import argparse
import os
import sys

# Agrega el directorio del script al path para importar operator_client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from operator_client import OperatorClient

# ─── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)-8s]  %(name)s — %(message)s",
)
log = logging.getLogger("Dashboard")

# ─── Paleta de colores ────────────────────────────────────────
CLR = {
    "bg":         "#1e1e2e",
    "bg2":        "#2a2a3e",
    "bg3":        "#313145",
    "accent":     "#7c6af7",
    "accent2":    "#5dc8a5",
    "text":       "#e0e0f0",
    "text_muted": "#8888aa",
    "alert_crit": "#ff6b6b",
    "alert_warn": "#ffd93d",
    "ok":         "#6bcf7f",
    "border":     "#44445a",
    "header_bg":  "#252540",
}

# ─── Sensor type → emoji label ───────────────────────────────
SENSOR_ICON = {
    "TEMPERATURE": "Temp",
    "HUMIDITY":    "Hum",
    "PRESSURE":    "Pres",
    "VIBRATION":   "Vib",
    "ENERGY":      "Energ",
    "":            "—",
}


def fmt_ts(ts_str: str) -> str:
    """Convierte timestamp Unix a string legible."""
    try:
        t = int(ts_str)
        return time.strftime("%H:%M:%S", time.localtime(t))
    except Exception:
        return ts_str


class Dashboard(tk.Tk):

    def __init__(self, operator_id: str, token: str,
                 host: str, port: int):
        super().__init__()

        self.operator_id = operator_id
        self.token       = token
        self.host        = host
        self.port        = port

        # Estado interno
        self._sensors: dict[str, dict] = {}     # id → {type, value, unit}
        self._alert_count = 0
        self._connected   = False

        # Cliente de red
        self.client = OperatorClient(operator_id, token, host, port)
        self._register_callbacks()

        # Construir UI
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Auto-refesco cada 10 s
        self._schedule_refresh()

    # ── Construcción de la UI ─────────────────────────────────

    def _build_ui(self):
        self.title("Sistema de Monitoreo IoT — Panel de Operador")
        self.geometry("1050x680")
        self.configure(bg=CLR["bg"])
        self.resizable(True, True)

        # ── Barra de conexión (top) ───────────────────────────
        top = tk.Frame(self, bg=CLR["bg2"], pady=8, padx=12)
        top.pack(fill=tk.X)

        tk.Label(top, text="SIMP Monitor", font=("Helvetica", 14, "bold"),
                 bg=CLR["bg2"], fg=CLR["accent"]).pack(side=tk.LEFT, padx=(0, 20))

        tk.Label(top, text="Servidor:", bg=CLR["bg2"],
                 fg=CLR["text_muted"]).pack(side=tk.LEFT)
        self._host_var = tk.StringVar(value=self.host)
        tk.Entry(top, textvariable=self._host_var, width=28,
                 bg=CLR["bg3"], fg=CLR["text"],
                 insertbackground=CLR["text"],
                 relief=tk.FLAT).pack(side=tk.LEFT, padx=(4, 12))

        tk.Label(top, text="Puerto:", bg=CLR["bg2"],
                 fg=CLR["text_muted"]).pack(side=tk.LEFT)
        self._port_var = tk.StringVar(value=str(self.port))
        tk.Entry(top, textvariable=self._port_var, width=6,
                 bg=CLR["bg3"], fg=CLR["text"],
                 insertbackground=CLR["text"],
                 relief=tk.FLAT).pack(side=tk.LEFT, padx=(4, 16))

        self._btn_connect = tk.Button(
            top, text="Conectar", command=self._connect,
            bg=CLR["accent"], fg="white", relief=tk.FLAT,
            padx=12, activebackground=CLR["bg3"], cursor="hand2"
        )
        self._btn_connect.pack(side=tk.LEFT)

        self._btn_disconnect = tk.Button(
            top, text="Desconectar", command=self._disconnect,
            bg=CLR["border"], fg=CLR["text_muted"], relief=tk.FLAT,
            padx=12, state=tk.DISABLED, cursor="hand2"
        )
        self._btn_disconnect.pack(side=tk.LEFT, padx=8)

        self._status_lbl = tk.Label(top, text="● Desconectado",
                                    bg=CLR["bg2"], fg=CLR["alert_crit"],
                                    font=("Helvetica", 10, "bold"))
        self._status_lbl.pack(side=tk.RIGHT, padx=16)

        # ── Tarjetas de estado (fila superior) ───────────────
        cards_frame = tk.Frame(self, bg=CLR["bg"], pady=10)
        cards_frame.pack(fill=tk.X, padx=16)

        self._lbl_sensors   = self._card(cards_frame, "Sensores activos", "—")
        self._lbl_operators = self._card(cards_frame, "Operadores",       "—")
        self._lbl_alerts    = self._card(cards_frame, "Alertas totales",  "0")
        self._lbl_uptime    = self._card(cards_frame, "Uptime servidor",  "—")

        # ── Contenedor central (tabla + alertas) ──────────────
        center = tk.Frame(self, bg=CLR["bg"])
        center.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))
        center.columnconfigure(0, weight=3)
        center.columnconfigure(1, weight=2)
        center.rowconfigure(0, weight=1)

        # Tabla de sensores
        self._build_sensor_table(center)

        # Panel de alertas
        self._build_alert_panel(center)

        # ── Barra de acciones (bottom) ────────────────────────
        bot = tk.Frame(self, bg=CLR["bg2"], pady=6, padx=12)
        bot.pack(fill=tk.X, side=tk.BOTTOM)

        for label, cmd in [
            ("Actualizar sensores", self._refresh_sensors),
            ("Estado del sistema",  self._refresh_status),
            ("Limpiar alertas",     self._clear_alerts),
        ]:
            tk.Button(bot, text=label, command=cmd,
                      bg=CLR["bg3"], fg=CLR["text"], relief=tk.FLAT,
                      padx=10, pady=3, cursor="hand2"
                      ).pack(side=tk.LEFT, padx=4)

        self._footer = tk.Label(
            bot, text=f"Operador: {self.operator_id}",
            bg=CLR["bg2"], fg=CLR["text_muted"], font=("Helvetica", 9)
        )
        self._footer.pack(side=tk.RIGHT, padx=8)

    def _card(self, parent, title: str, value: str):
        """Crea una tarjeta de métrica."""
        f = tk.Frame(parent, bg=CLR["bg2"], padx=18, pady=10,
                     relief=tk.FLAT, bd=0)
        f.pack(side=tk.LEFT, padx=6, fill=tk.Y)

        tk.Label(f, text=title, bg=CLR["bg2"], fg=CLR["text_muted"],
                 font=("Helvetica", 9)).pack(anchor=tk.W)

        lbl = tk.Label(f, text=value, bg=CLR["bg2"], fg=CLR["accent2"],
                       font=("Helvetica", 22, "bold"))
        lbl.pack(anchor=tk.W)
        return lbl

    def _build_sensor_table(self, parent):
        """Tabla de sensores activos con Treeview."""
        left = tk.Frame(parent, bg=CLR["bg"])
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        tk.Label(left, text="Sensores activos", bg=CLR["bg"],
                 fg=CLR["text"], font=("Helvetica", 11, "bold"),
                 pady=6).pack(anchor=tk.W)

        # Estilo
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Dark.Treeview",
                        background=CLR["bg2"],
                        foreground=CLR["text"],
                        rowheight=28,
                        fieldbackground=CLR["bg2"],
                        bordercolor=CLR["border"],
                        font=("Helvetica", 10))
        style.configure("Dark.Treeview.Heading",
                        background=CLR["header_bg"],
                        foreground=CLR["accent"],
                        font=("Helvetica", 10, "bold"))
        style.map("Dark.Treeview",
                  background=[("selected", CLR["accent"])])

        cols = ("id", "tipo", "valor", "unidad", "estado")
        self._tree = ttk.Treeview(left, columns=cols, show="headings",
                                   style="Dark.Treeview", height=12)

        widths = {"id": 180, "tipo": 130, "valor": 100,
                  "unidad": 80, "estado": 90}
        headers = {"id": "ID Sensor", "tipo": "Tipo", "valor": "Valor",
                   "unidad": "Unidad", "estado": "Estado"}

        for col in cols:
            self._tree.heading(col, text=headers[col])
            self._tree.column(col, width=widths[col], anchor=tk.CENTER)

        # Tags de color para filas
        self._tree.tag_configure("ok",    background=CLR["bg2"])
        self._tree.tag_configure("alert", background="#3a1a1a")

        sb = ttk.Scrollbar(left, orient=tk.VERTICAL,
                           command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)

        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_alert_panel(self, parent):
        """Panel de alertas con texto de scroll."""
        right = tk.Frame(parent, bg=CLR["bg"])
        right.grid(row=0, column=1, sticky="nsew")

        header = tk.Frame(right, bg=CLR["bg"])
        header.pack(fill=tk.X)

        tk.Label(header, text="Alertas en tiempo real",
                 bg=CLR["bg"], fg=CLR["text"],
                 font=("Helvetica", 11, "bold"), pady=6).pack(side=tk.LEFT)

        self._alert_badge = tk.Label(header, text=" 0 ",
                                     bg=CLR["alert_crit"], fg="white",
                                     font=("Helvetica", 9, "bold"),
                                     padx=6, pady=2)
        self._alert_badge.pack(side=tk.LEFT, padx=8)

        self._alert_box = scrolledtext.ScrolledText(
            right, wrap=tk.WORD, height=20,
            bg=CLR["bg2"], fg=CLR["text"],
            font=("Courier", 9),
            insertbackground=CLR["text"],
            relief=tk.FLAT, state=tk.DISABLED,
            padx=8, pady=6
        )
        self._alert_box.pack(fill=tk.BOTH, expand=True)

        # Tags de colores para el texto de alertas
        self._alert_box.tag_configure("header",
                                       foreground=CLR["alert_crit"],
                                       font=("Courier", 9, "bold"))
        self._alert_box.tag_configure("value",
                                       foreground=CLR["alert_warn"])
        self._alert_box.tag_configure("desc",
                                       foreground=CLR["text_muted"])
        self._alert_box.tag_configure("sep",
                                       foreground=CLR["border"])

    # ── Callbacks del OperatorClient ──────────────────────────

    def _register_callbacks(self):
        self.client.on_connected    = self._cb_connected
        self.client.on_disconnected = self._cb_disconnected
        self.client.on_alert        = self._cb_alert
        self.client.on_sensor_list  = self._cb_sensor_list
        self.client.on_status       = self._cb_status
        self.client.on_error        = self._cb_error

    def _cb_connected(self):
        self._connected = True
        self.after(0, self._ui_connected)
        # Pedir datos iniciales
        self.after(500,  self.client.query_sensors)
        self.after(1000, self.client.query_status)

    def _cb_disconnected(self):
        self._connected = False
        self.after(0, self._ui_disconnected)

    def _cb_alert(self, alert: dict):
        self._alert_count += 1
        self.after(0, self._ui_add_alert, alert)

    def _cb_sensor_list(self, sensors: list):
        self.after(0, self._ui_update_sensors, sensors)

    def _cb_status(self, status: dict):
        self.after(0, self._ui_update_status, status)

    def _cb_error(self, message: str):
        log.warning(f"Error del servidor: {message}")
        self.after(0, self._append_alert_text,
                   f"[ERROR] {message}\n", "header")

    # ── Actualizaciones de UI (se ejecutan en hilo principal) ─

    def _ui_connected(self):
        self._status_lbl.config(text="● Conectado", fg=CLR["ok"])
        self._btn_connect.config(state=tk.DISABLED)
        self._btn_disconnect.config(state=tk.NORMAL,
                                    bg=CLR["accent"],
                                    fg="white")
        self._append_alert_text(
            f"[{time.strftime('%H:%M:%S')}] Conectado al servidor "
            f"{self.host}:{self.port}\n", "desc"
        )

    def _ui_disconnected(self):
        self._status_lbl.config(text="● Desconectado", fg=CLR["alert_crit"])
        self._btn_connect.config(state=tk.NORMAL)
        self._btn_disconnect.config(state=tk.DISABLED,
                                    bg=CLR["border"],
                                    fg=CLR["text_muted"])

    def _ui_update_sensors(self, sensors: list):
        """Actualiza la tabla de sensores."""
        # Acumular por ID (para merge con existentes)
        for s in sensors:
            sid = s.get("id", "?")
            self._sensors[sid] = s

        # Limpiar y repoblar tabla
        for row in self._tree.get_children():
            self._tree.delete(row)

        for sid, s in sorted(self._sensors.items()):
            val   = s.get("value", "—")
            stype = s.get("type",  "")
            unit  = s.get("unit",  "")

            # Determinar si hay alerta activa (valor fuera de rango)
            tag = self._value_tag(stype, val)
            estado = "NORMAL" if tag == "ok" else "ALERTA"

            self._tree.insert("", tk.END, values=(
                sid,
                SENSOR_ICON.get(stype, stype),
                self._fmt_value(val),
                unit,
                estado,
            ), tags=(tag,))

        self._lbl_sensors.config(text=str(len(self._sensors)))

    def _ui_update_status(self, status: dict):
        """Actualiza las tarjetas de estado."""
        self._lbl_sensors.config(
            text=status.get("sensores", str(len(self._sensors))))
        self._lbl_operators.config(text=status.get("operadores", "—"))
        self._lbl_alerts.config(text=status.get("alertas", "—"))

        uptime = status.get("uptime", "")
        if uptime:
            try:
                s = int(uptime)
                h, rem = divmod(s, 3600)
                m, sec = divmod(rem, 60)
                self._lbl_uptime.config(text=f"{h:02d}:{m:02d}:{sec:02d}")
            except Exception:
                self._lbl_uptime.config(text=uptime)

    def _ui_add_alert(self, alert: dict):
        """Agrega una alerta al panel de alertas."""
        ts   = fmt_ts(alert.get("timestamp", ""))
        sid  = alert.get("sensor_id",  "?")
        atype = alert.get("type",      "?")
        val  = alert.get("value",      "?")
        desc = alert.get("description", "")

        # Actualizar badge
        self._alert_badge.config(text=f" {self._alert_count} ")

        # Agregar texto al panel
        self._alert_box.config(state=tk.NORMAL)
        self._alert_box.insert(tk.END, "─" * 40 + "\n", "sep")
        self._alert_box.insert(tk.END,
            f"[{ts}] ALERTA — {sid}\n", "header")
        self._alert_box.insert(tk.END,
            f"  Tipo: {atype}   Valor: {val}\n", "value")
        self._alert_box.insert(tk.END,
            f"  {desc}\n", "desc")
        self._alert_box.config(state=tk.DISABLED)
        self._alert_box.see(tk.END)   # auto-scroll al final

        # Flash del título de la ventana
        self.title(f"[!] ALERTA — {sid} | Panel Operador")
        self.after(3000, lambda: self.title(
            "Sistema de Monitoreo IoT — Panel de Operador"))

    def _append_alert_text(self, text: str, tag: str = "desc"):
        self._alert_box.config(state=tk.NORMAL)
        self._alert_box.insert(tk.END, text, tag)
        self._alert_box.config(state=tk.DISABLED)
        self._alert_box.see(tk.END)

    # ── Acciones de botones ───────────────────────────────────

    def _connect(self):
        self.host = self._host_var.get().strip()
        self.port = int(self._port_var.get().strip())
        self.client.host = self.host
        self.client.port = self.port
        self._status_lbl.config(text="● Conectando...", fg=CLR["alert_warn"])
        threading.Thread(target=self.client.connect, daemon=True).start()

    def _disconnect(self):
        threading.Thread(target=self.client.disconnect, daemon=True).start()

    def _refresh_sensors(self):
        if self._connected:
            self.client.query_sensors()

    def _refresh_status(self):
        if self._connected:
            self.client.query_status()

    def _clear_alerts(self):
        self._alert_box.config(state=tk.NORMAL)
        self._alert_box.delete("1.0", tk.END)
        self._alert_box.config(state=tk.DISABLED)
        self._alert_count = 0
        self._alert_badge.config(text=" 0 ")

    def _on_close(self):
        if self._connected:
            self.client.disconnect()
        self.destroy()

    # ── Auto-refresco ─────────────────────────────────────────

    def _schedule_refresh(self):
        def refresh():
            if self._connected:
                self.client.query_sensors()
                self.after(1000, self.client.query_status)
            self.after(10_000, refresh)
        self.after(10_000, refresh)

    # ── Helpers ───────────────────────────────────────────────

    def _fmt_value(self, val) -> str:
        try:
            return f"{float(val):.3f}"
        except Exception:
            return str(val)

    THRESHOLDS = {
        "TEMPERATURE": (-10.0,  90.0),
        "HUMIDITY":    (  0.0,  95.0),
        "PRESSURE":    (800.0, 1100.0),
        "VIBRATION":   (  0.0,   2.0),
        "ENERGY":      (  0.0,  50.0),
    }

    def _value_tag(self, stype: str, val) -> str:
        thr = self.THRESHOLDS.get(stype)
        if not thr:
            return "ok"
        try:
            v = float(val)
            if v < thr[0] or v > thr[1]:
                return "alert"
        except Exception:
            pass
        return "ok"


# ─── Entry point ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Dashboard del operador — Sistema SIMP IoT"
    )
    parser.add_argument("--host",  default=os.getenv("SIMP_SERVER_HOST",
                                                      "monitor.iot-monitor.local"))
    parser.add_argument("--port",  type=int,
                        default=int(os.getenv("SIMP_SERVER_PORT", "9000")))
    parser.add_argument("--id",    default=os.getenv("OPERATOR_ID",
                                                      "operator_01"))
    parser.add_argument("--token", default=os.getenv("OPERATOR_TOKEN",
                                                      "tok_op_001"))
    args = parser.parse_args()

    app = Dashboard(
        operator_id=args.id,
        token=args.token,
        host=args.host,
        port=args.port,
    )
    app.mainloop()


if __name__ == "__main__":
    main()
