import serial
import json
import os

# ---------------- USER CONFIG ----------------
LAUNCH_NUMBER = 1  # <-- change manually for each launch
PORT = "COM13"      # <-- change this to your ESP32 LoRa serial port
BAUDRATE = 115200
# ---------------------------------------------

# Make sure folder exists
folder_name = "Launch_Data"
os.makedirs(folder_name, exist_ok=True)

# File path for this launch
file_path = os.path.join(folder_name, f"Launch{LAUNCH_NUMBER}.my_format")

# If file doesn’t exist, create empty list
if not os.path.exists(file_path):
    with open(file_path, "w") as f:
        f.write("")

# Open serial connection
ser = serial.Serial(PORT, BAUDRATE, timeout=1)

def parse_data(line):
    """
    Parse incoming line like:
    CAN-TI-34; A-450; T-27.5; P-1; X-200; Y-500; Z-450; YX-1; YY-1; YZ-1;
    into structured dict
    """
    parts = [p.strip() for p in line.split(";") if p.strip()]
    data_dict = {}

    accel = {"Category": "Accelerometer"}
    yaw = {"Category": "Yaw"}

    for p in parts:
        if p.startswith("CAN-"):
            key_val = p.split("-")
            if len(key_val) >= 3 and key_val[1] == "TI":
                data_dict["TI"] = key_val[2]
        elif p.startswith("A-"):
            data_dict["A"] = p.split("-")[1]
        elif p.startswith("T-"):
            data_dict["T"] = p.split("-")[1]
        elif p.startswith("P-"):
            data_dict["P"] = p.split("-")[1]
        elif p.startswith("X-"):
            accel["X"] = p.split("-")[1]
        elif p.startswith("Y-"):
            accel["Y"] = p.split("-")[1]
        elif p.startswith("Z-"):
            accel["Z"] = p.split("-")[1]
        elif p.startswith("YX-"):
            yaw["YX"] = p.split("-")[1]
        elif p.startswith("YY-"):
            yaw["YY"] = p.split("-")[1]
        elif p.startswith("YZ-"):
            yaw["YZ"] = p.split("-")[1]

    # ✅ Only return record if meaningful fields exist
    if any(k in data_dict for k in ["TI", "A", "T", "P"]):
        data_dict["Accelerometer"] = accel
        data_dict["Yaw"] = yaw
        return data_dict
    else:
        return None   # skip invalid line


print(f"Listening on {PORT} at {BAUDRATE} baud...")

while True:
    try:
        line = ser.readline().decode("utf-8").strip()
        if not line:
            continue

        print("Received:", line)
        record = parse_data(line)

        if record:  # ✅ Only append valid data
            with open(file_path, "a") as f:
                f.write(str(record)+"\n")


            print("✅ Data appended to", file_path)
        else:
            print("⏭️ Skipped invalid/empty line")

    except KeyboardInterrupt:
        print("\nStopped by user.")
        break
    except Exception as e:
        print("⚠️ Error:", e)