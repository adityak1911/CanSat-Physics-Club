import os
import ast
import matplotlib.pyplot as plt

# ---------------- USER CONFIG ----------------
LAUNCH_NUMBER = 1  # same as in receiver.py
# ---------------------------------------------

# File path (input data)
file_path = os.path.join("Launch_Data", f"Launch{LAUNCH_NUMBER}.my_format")

# Folder path for saving plots
plots_folder = os.path.join("Plots", f"Launch{LAUNCH_NUMBER}")
os.makedirs(plots_folder, exist_ok=True)

# Storage for values
TI, T, P, A = [], [], [], []

# Read file and parse dicts
with open(file_path, "r") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            record = ast.literal_eval(line)  # safely convert str -> dict

            if "TI" in record:
                TI.append(int(record["TI"]))
                # keep other lists aligned
                T.append(float(record["T"]) if "T" in record else None)
                P.append(float(record["P"]) if "P" in record else None)
                A.append(float(record["A"]) if "A" in record else None)

        except Exception as e:
            print("⚠️ Skipping line due to error:", e)

# Utility to plot & save
def plot_and_save(x, y, xlabel, ylabel, title, filename):
    plt.figure(figsize=(7,5))
    plt.plot(x, y, marker="o", linestyle="-")
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.grid(True)
    save_path = os.path.join(plots_folder, filename)
    plt.savefig(save_path)
    plt.close()
    print("✅ Saved:", save_path)

# Plot graphs (skip None values)
if any(v is not None for v in T):
    plot_and_save(TI, [v for v in T if v is not None], "TI", "Temperature (T)", "Temperature vs TI", "T_vs_TI.png")

if any(v is not None for v in P):
    plot_and_save(TI, [v for v in P if v is not None], "TI", "Pressure (P)", "Pressure vs TI", "P_vs_TI.png")

if any(v is not None for v in A):
    plot_and_save(TI, [v for v in A if v is not None], "TI", "Altitude (A)", "Altitude vs TI", "A_vs_TI.png")

print("🎉 All plots saved in:", plots_folder)