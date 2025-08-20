import serial

ser = serial.Serial('COM3', 9600, timeout=1)
print("Reading altitude data...\n")

while True:
    try:
        raw = ser.readline()
        # Decode safely, ignore non-UTF characters
        line = raw.decode('utf-8', errors='ignore').strip()
        if line.startswith("ALT"):
            print(line)
    except Exception as e:
        print("Error:", e)
        break
