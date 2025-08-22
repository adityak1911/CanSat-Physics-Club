import asyncio
import json
import time
import serial
import serial.tools.list_ports
import websockets

# ---------------- Serial Setup ----------------
PORT = "COM3"     # Change to your Arduino/CanSat port
BAUD = 115200

try:
    ser = serial.Serial(PORT, BAUD, timeout=1)
    print(f"✅ Connected to {PORT} at {BAUD}")
except Exception as e:
    print(f"❌ Could not open serial port: {e}")
    ser = None

# ---------------- Serial Parser ----------------
def parse_serial_line(line: str):
    """Parse telemetry lines like: Data: A-450; T-27.5; X-5"""
    out = {
        "alt": 0.0, "temp": 0.0, "pres": 0.0,
        "acc_x": 0.0, "acc_y": 0.0, "acc_z": 0.0,
        "yaw_x": 0.0, "yaw_y": 0.0, "yaw_z": 0.0,
        "ts": time.time()
    }
    if not line.startswith("Data:"):
        return out
    parts = [p.strip() for p in line[5:].split(";") if p.strip()]
    for p in parts:
        if "-" not in p: continue
        key, val = p.split("-", 1)
        try: val = float(val)
        except: val = 0.0
        if key == "A": out["alt"] = val
        elif key == "T": out["temp"] = val
        elif key == "P": out["pres"] = val
        elif key == "X": out["acc_x"] = val
        elif key == "Y": out["acc_y"] = val
        elif key == "Z": out["acc_z"] = val
        elif key == "YX": out["yaw_x"] = val
        elif key == "YY": out["yaw_y"] = val
        elif key == "YZ": out["yaw_z"] = val
    return out

# ---------------- WebSocket Server ----------------
clients = set()

async def telemetry_server(websocket, path):
    print("🔗 Client connected")
    clients.add(websocket)
    try:
        while True:
            await asyncio.sleep(0.1)
    except websockets.exceptions.ConnectionClosed:
        print("❌ Client disconnected")
    finally:
        clients.remove(websocket)

async def serial_reader():
    """Read serial and broadcast to WebSocket clients"""
    while True:
        if ser and ser.in_waiting:
            try:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if line:
                    data = parse_serial_line(line)
                    msg = json.dumps(data)
                    print("➡️ Sending:", msg)
                    await asyncio.gather(*(c.send(msg) for c in clients))
            except Exception as e:
                print(f"[Serial Error] {e}")
        await asyncio.sleep(0.05)

async def main():
    server = await websockets.serve(telemetry_server, "0.0.0.0", 8765)
    print("🚀 WebSocket server running at ws://localhost:8765")
    await serial_reader()  # keeps running

if __name__ == "__main__":
    asyncio.run(main())
