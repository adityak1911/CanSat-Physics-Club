import streamlit as st
import serial
import threading
import time
import pandas as pd
import plotly.express as px

# ---------------- USER CONFIG ----------------
PORT = "COM13"  # Change this to your ESP32 port
BAUDRATE = 115200
REFRESH_INTERVAL = 1  # seconds
# ---------------------------------------------

# ---------------- SESSION STATE ----------------
if "data" not in st.session_state:
    st.session_state.data = {
        "TI": [], "T": [], "P": [], "A": [],
        "YX": [], "YY": [], "YZ": []
    }
if "serial_thread_started" not in st.session_state:
    st.session_state.serial_thread_started = False
if "serial_error" not in st.session_state:
    st.session_state.serial_error = None
if "raw_lines" not in st.session_state:
    st.session_state.raw_lines = []

# ---------------- SERIAL THREAD ----------------
def read_serial():
    try:
        ser = serial.Serial(PORT, BAUDRATE, timeout=1)
        st.session_state.serial_error = None
    except Exception as e:
        st.session_state.serial_error = f"Cannot open serial port {PORT}: {e}"
        return

    while True:
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if line:
                st.session_state.raw_lines.append(line)
            parts = [p.strip() for p in line.split(";") if p.strip()]
            record = {}
            for p in parts:
                if "-" in p:
                    k, v = p.split("-", 1)
                    record[k] = v

            if "TI" in record:
                st.session_state.data["TI"].append(int(record["TI"]))
                st.session_state.data["T"].append(float(record.get("T", "nan")))
                st.session_state.data["P"].append(float(record.get("P", "nan")))
                st.session_state.data["A"].append(float(record.get("A", "nan")))
                st.session_state.data["YX"].append(float(record.get("YX", "nan")))
                st.session_state.data["YY"].append(float(record.get("YY", "nan")))
                st.session_state.data["YZ"].append(float(record.get("YZ", "nan")))
        except Exception as e:
            st.session_state.raw_lines.append(f"⚠️ Serial error: {e}")

# Start serial thread once
if not st.session_state.serial_thread_started:
    threading.Thread(target=read_serial, daemon=True).start()
    st.session_state.serial_thread_started = True

# ---------------- STREAMLIT UI ----------------
st.set_page_config(layout="wide")
st.title("🚀 CanSat Live Telemetry Dashboard")

# Placeholders for live data
placeholder_values = st.empty()
placeholder_graphs = st.empty()
placeholder_yaw = st.empty()
placeholder_debug = st.expander("🛠️ Debug Serial Data", expanded=False)

# ---------------- LIVE UPDATE ----------------
def update_dashboard():
    data = st.session_state.data

    # Live values
    latest_values = {
        "TI": data["TI"][-1] if data["TI"] else "—",
        "Temperature (T)": data["T"][-1] if data["T"] else "—",
        "Pressure (P)": data["P"][-1] if data["P"] else "—",
        "Altitude (A)": data["A"][-1] if data["A"] else "—",
        "Yaw YX": data["YX"][-1] if data["YX"] else "—",
        "Yaw YY": data["YY"][-1] if data["YY"] else "—",
        "Yaw YZ": data["YZ"][-1] if data["YZ"] else "—",
    }
    placeholder_values.json(latest_values)

    # Graphs
    with placeholder_graphs.container():
        st.subheader("📊 Live Graphs")
        col1, col2, col3 = st.columns(3)

        with col1:
            if data["TI"] and data["T"]:
                fig = px.line(
                    x=data["TI"], y=data["T"],
                    labels={"x": "TI", "y": "Temperature (°C)"},
                    title="Temperature vs TI"
                )
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            if data["TI"] and data["P"]:
                fig = px.line(
                    x=data["TI"], y=data["P"],
                    labels={"x": "TI", "y": "Pressure"},
                    title="Pressure vs TI"
                )
                st.plotly_chart(fig, use_container_width=True)

        with col3:
            if data["TI"] and data["A"]:
                fig = px.line(
                    x=data["TI"], y=data["A"],
                    labels={"x": "TI", "y": "Altitude"},
                    title="Altitude vs TI"
                )
                st.plotly_chart(fig, use_container_width=True)

    # Yaw orientation
    with placeholder_yaw.container():
        st.subheader("🛰️ CanSat Orientation (Yaw)")
        if data["YX"] and data["YY"] and data["YZ"]:
            yaw_df = pd.DataFrame({
                "x": [0, data["YX"][-1]],
                "y": [0, data["YY"][-1]],
                "z": [0, data["YZ"][-1]],
            })
            fig = px.line_3d(yaw_df, x="x", y="y", z="z", title="Yaw Orientation")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Waiting for yaw data...")

    # Debug raw serial
    with placeholder_debug:
        st.write(st.session_state.raw_lines[-20:])  # show last 20 lines
        if st.session_state.serial_error:
            st.error(st.session_state.serial_error)

# Auto-refresh the dashboard every REFRESH_INTERVAL seconds
st_autorefresh = st.experimental_data_editor([], key="dummy")  # dummy to force Streamlit to refresh

update_dashboard()
time.sleep(REFRESH_INTERVAL)
st.experimental_rerun()