
# app.py
# Streamlit CanSat Live 3D Dashboard
# - Renders a 3D "can" that rotates using yaw/pitch/roll from a serial stream
# - Shows SpaceX-style HUD readouts: velocity (bottom-left), altitude (bottom-right)
# - Lets you select serial port/baud, connect/disconnect, and auto-refresh the UI
#
# How to run:
#   1) pip install -r requirements.txt
#   2) streamlit run app.py
#
# Expected serial message formats (flexible parser supports these):
#   - "YPR: <yaw>,<pitch>,<roll>;VEL:<vel>;ALT:<alt>"
#   - "<yaw>,<pitch>,<roll>,<vel>,<alt>"
#   - JSON: {"yaw":..,"pitch":..,"roll":..,"vel":..,"alt":..}
#
# Angles are in degrees. Yaw=Z, Pitch=Y, Roll=X (applied ZYX).
#
import math
import time
import json
import re
import threading
from dataclasses import dataclass
from typing import Optional, Tuple, Dict

import numpy as np
import plotly.graph_objects as go
import streamlit as st

try:
    import serial  # pyserial
    import serial.tools.list_ports as list_ports
    HAS_SERIAL = True
except Exception:
    HAS_SERIAL = False


# --------------------------- Utilities ---------------------------
@dataclass
class CanSatState:
    yaw: float = 0.0    # deg
    pitch: float = 0.0  # deg
    roll: float = 0.0   # deg
    vel: float = 0.0    # m/s
    alt: float = 0.0    # m
    ts: float = 0.0     # epoch seconds


def zyx_rotation_matrix(yaw_deg: float, pitch_deg: float, roll_deg: float) -> np.ndarray:
    """Return 3x3 rotation matrix for intrinsic Z (yaw) -> Y (pitch) -> X (roll)."""
    z = math.radians(yaw_deg)
    y = math.radians(pitch_deg)
    x = math.radians(roll_deg)

    cz, sz = math.cos(z), math.sin(z)
    cy, sy = math.cos(y), math.sin(y)
    cx, sx = math.cos(x), math.sin(x)

    Rz = np.array([[cz, -sz, 0],
                   [sz,  cz, 0],
                   [ 0,   0, 1]], dtype=float)
    Ry = np.array([[ cy, 0, sy],
                   [  0, 1,  0],
                   [-sy, 0, cy]], dtype=float)
    Rx = np.array([[1,  0,   0],
                   [0, cx, -sx],
                   [0, sx,  cx]], dtype=float)
    return Rz @ Ry @ Rx  # intrinsic ZYX


def make_cylinder(R=0.033, H=0.115, n_theta=64, n_z=20) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Generate a parametric cylinder surface (no end caps).
    Returns X, Y, Z arrays shaped (n_z, n_theta).
    """
    theta = np.linspace(0, 2*np.pi, n_theta)
    z = np.linspace(-H/2, H/2, n_z)
    T, Z = np.meshgrid(theta, z)
    X = R * np.cos(T)
    Y = R * np.sin(T)
    return X, Y, Z


def rotate_points(X: np.ndarray, Y: np.ndarray, Z: np.ndarray, R: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Apply 3x3 rotation to parametric surface points."""
    pts = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=0)  # (3, N)
    rot = R @ pts
    x = rot[0, :].reshape(X.shape)
    y = rot[1, :].reshape(Y.shape)
    z = rot[2, :].reshape(Z.shape)
    return x, y, z


def parse_serial_line(s: str) -> Dict[str, float]:
    """
    Parse a line into fields yaw, pitch, roll, vel, alt (floats). Missing fields default to 0.
    Supports three flexible formats shown at the top of the file.
    """
    s = s.strip()
    out = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0, "vel": 0.0, "alt": 0.0}

    # Try JSON
    if s.startswith("{") and s.endswith("}"):
        try:
            obj = json.loads(s)
            for k in out:
                if k in obj:
                    out[k] = float(obj[k])
            return out
        except Exception:
            pass

    # Try labeled pattern like YPR: a,b,c;VEL:v;ALT:a
    m = re.search(r"YPR\s*:\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)", s)
    if m:
        out["yaw"] = float(m.group(1)); out["pitch"] = float(m.group(2)); out["roll"] = float(m.group(3))
        mv = re.search(r"VEL\s*:\s*([-+0-9.eE]+)", s)
        ma = re.search(r"ALT\s*:\s*([-+0-9.eE]+)", s)
        if mv: out["vel"] = float(mv.group(1))
        if ma: out["alt"] = float(ma.group(1))
        return out

    # Try simple CSV yaw,pitch,roll,vel,alt
    parts = [p for p in re.split(r"[,\s]+", s) if p]
    if len(parts) >= 3:
        try:
            out["yaw"] = float(parts[0]); out["pitch"] = float(parts[1]); out["roll"] = float(parts[2])
            if len(parts) >= 4: out["vel"] = float(parts[3])
            if len(parts) >= 5: out["alt"] = float(parts[4])
            return out
        except Exception:
            pass

    return out


# --------------------------- Serial Reader ---------------------------
class SerialReader:
    def __init__(self):
        self._port: Optional[str] = None
        self._baud: int = 115200
        self._ser = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest = CanSatState()

    def list_ports(self):
        if not HAS_SERIAL:
            return []
        return [p.device for p in list_ports.comports()]

    def connect(self, port: str, baud: int):
        if not HAS_SERIAL:
            raise RuntimeError("pyserial not installed. Install requirements and restart.")
        self.disconnect()
        import serial  # local import
        self._ser = serial.Serial(port=port, baudrate=baud, timeout=0.1)
        self._port, self._baud = port, baud
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def disconnect(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
        self._thread = None
        if self._ser:
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None

    def _run(self):
        buff = b""
        while not self._stop.is_set():
            try:
                data = self._ser.readline()
                if not data:
                    continue
                line = data.decode(errors="ignore").strip()
                fields = parse_serial_line(line)
                st_ = CanSatState(
                    yaw=fields["yaw"],
                    pitch=fields["pitch"],
                    roll=fields["roll"],
                    vel=fields["vel"],
                    alt=fields["alt"],
                    ts=time.time(),
                )
                with self._lock:
                    self._latest = st_
            except Exception:
                # swallow parse/serial hiccups
                pass

    def latest(self) -> CanSatState:
        with self._lock:
            return self._latest

    def is_connected(self) -> bool:
        return self._ser is not None


# --------------------------- Streamlit App ---------------------------
st.set_page_config(page_title="CanSat Live 3D", layout="wide")

if "serial_reader" not in st.session_state:
    st.session_state.serial_reader = SerialReader()
if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = True
if "refresh_hz" not in st.session_state:
    st.session_state.refresh_hz = 10
if "last_render" not in st.session_state:
    st.session_state.last_render = 0.0

sr: SerialReader = st.session_state.serial_reader

# Sidebar controls
with st.sidebar:
    st.title("CanSat Link")
    ports = sr.list_ports()
    sel_port = st.selectbox("Serial Port", options=ports if ports else ["(no ports found)"])
    baud = st.selectbox("Baud Rate", options=[9600, 19200, 57600, 115200, 230400, 460800], index=3)
    cols = st.columns(2)
    if cols[0].button("Connect", use_container_width=True, disabled=(not ports or sr.is_connected())):
        if ports:
            try:
                sr.connect(sel_port, int(baud))
            except Exception as e:
                st.error(f"Failed to connect: {e}")
    if cols[1].button("Disconnect", use_container_width=True, disabled=(not sr.is_connected())):
        sr.disconnect()

    st.divider()
    st.subheader("Refresh")
    st.session_state.auto_refresh = st.toggle("Auto-refresh", value=st.session_state.auto_refresh, help="Continuously update the scene")
    st.session_state.refresh_hz = st.slider("Refresh rate (Hz)", min_value=1, max_value=30, value=st.session_state.refresh_hz)
    st.caption("Tip: If performance dips, lower the refresh rate.")

# Main layout
col_left, col_right = st.columns([2, 1])

# 3D Model
with col_left:
    st.subheader("Attitude Visualizer")
    # Get latest state (if no serial, will be zeros)
    state = sr.latest()

    # Generate and rotate cylinder
    X, Y, Z = make_cylinder(R=0.033, H=0.115, n_theta=80, n_z=40)
    Rm = zyx_rotation_matrix(state.yaw, state.pitch, state.roll)
    x, y, z = rotate_points(X, Y, Z, Rm)

    # Coordinate axes (body frame)
    L = 0.08  # axis length
    axes = {
        "X": (np.array([0, L, np.nan]), np.array([0, 0, np.nan]), np.array([0, 0, np.nan])),
        "Y": (np.array([0, 0, np.nan]), np.array([0, L, np.nan]), np.array([0, 0, np.nan])),
        "Z": (np.array([0, 0, np.nan]), np.array([0, 0, np.nan]), np.array([0, L, np.nan])),
    }
    # Rotate axes
    for k in list(axes.keys()):
        pts = np.vstack(axes[k])  # 3 x 3
        rot = Rm @ pts
        axes[k] = (rot[0, :], rot[1, :], rot[2, :])

    surf = go.Surface(x=x, y=y, z=z, opacity=0.9, showscale=False)

    axis_traces = []
    for name, (xx, yy, zz) in axes.items():
        axis_traces.append(go.Scatter3d(
            x=xx, y=yy, z=zz,
            mode="lines",
            line=dict(width=6),
            name=f"{name}-axis",
            showlegend=False
        ))
        # Axis label at the end
        axis_traces.append(go.Scatter3d(
            x=[xx[1]], y=[yy[1]], z=[zz[1]],
            mode="text",
            text=[name],
            textposition="top center",
            showlegend=False
        ))

    fig = go.Figure(data=[surf] + axis_traces)
    fig.update_scenes(
        xaxis_title="X",
        yaxis_title="Y",
        zaxis_title="Z",
        aspectmode="data",
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=30, b=0),
        title=f"Yaw {state.yaw:.1f}°, Pitch {state.pitch:.1f}°, Roll {state.roll:.1f}°",
        scene=dict(
            xaxis=dict(range=[-0.12, 0.12]),
            yaxis=dict(range=[-0.12, 0.12]),
            zaxis=dict(range=[-0.12, 0.12]),
        ),
        # SpaceX-style HUD annotations (paper coordinates)
        annotations=[
            dict(
                x=0.01, y=0.02, xref="paper", yref="paper",
                text=f"VEL {state.vel:.1f} m/s",
                showarrow=False, font=dict(size=16)
            ),
            dict(
                x=0.99, y=0.02, xref="paper", yref="paper",
                text=f"ALT {state.alt:.1f} m",
                showarrow=False, xanchor="right", font=dict(size=16)
            ),
        ],
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# Telemetry & controls
with col_right:
    st.subheader("Telemetry")
    st.metric("Velocity (m/s)", f"{sr.latest().vel:.2f}")
    st.metric("Altitude (m)", f"{sr.latest().alt:.2f}")
    st.metric("Last update (s ago)", f"{max(0.0, time.time()-sr.latest().ts):.1f}")
    st.divider()
    st.subheader("Orientation")
    c1, c2, c3 = st.columns(3)
    c1.metric("Yaw (°)", f"{sr.latest().yaw:.1f}")
    c2.metric("Pitch (°)", f"{sr.latest().pitch:.1f}")
    c3.metric("Roll (°)", f"{sr.latest().roll:.1f}")
    st.divider()
    st.caption("Need a custom STL model? Replace the cylinder code with a mesh loader to render your own geometry.")

# Auto-refresh loop (lightweight): schedule another rerun if enabled and enough time passed
now = time.time()
min_period = 1.0 / max(1, int(st.session_state.refresh_hz))
if st.session_state.auto_refresh and (now - st.session_state.last_render) >= min_period:
    st.session_state.last_render = now
    # Yield control to Streamlit, then immediately rerun; this keeps UI responsive.
    st.rerun()