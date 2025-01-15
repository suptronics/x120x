#!/usr/bin/env python3
#Based on - https://github.com/suptronics/x120x

import sys
import struct
from pathlib import Path
from subprocess import check_output, CalledProcessError, call
import smbus2
from gpiozero import InputDevice, Button
import time

# Constants
CHG_ONOFF_PIN = 16
PLD_BUTTON = Button(6)
bus = smbus2.SMBus(1)

def read_voltage_and_capacity(bus):
    address = 0x36
    voltage_read = bus.read_word_data(address, 2)
    capacity_read = bus.read_word_data(address, 4)
    voltage_swapped = struct.unpack("<H", struct.pack(">H", voltage_read))[0]
    voltage = voltage_swapped * 1.25 / 1000 / 16
    capacity_swapped = struct.unpack("<H", struct.pack(">H", capacity_read))[0]
    capacity = capacity_swapped / 256
    return voltage, capacity

def get_pld_state():
    return 0 if PLD_BUTTON.is_pressed else 1

def read_hardware_metric(command_args, strip_chars):
    try:
        output = check_output(command_args).decode("utf-8")
        metric_str = output.split("=")[1].strip().rstrip(strip_chars)
        return float(metric_str)
    except (CalledProcessError, ValueError) as e:
        print(f"Error reading hardware metric: {e}")
        return None

def read_cpu_volts():
    return read_hardware_metric(["vcgencmd", "pmic_read_adc", "VDD_CORE_V"], 'V')

def read_cpu_amps():
    return read_hardware_metric(["vcgencmd", "pmic_read_adc", "VDD_CORE_A"], 'A')

def read_cpu_temp():
    return read_hardware_metric(["vcgencmd", "measure_temp"], "'C")

def read_input_voltage():
    return read_hardware_metric(["vcgencmd", "pmic_read_adc", "EXT5V_V"], 'V')

def get_fan_rpm():
    try:
        sys_devices_path = Path('/sys/devices/platform/cooling_fan')
        fan_input_files = list(sys_devices_path.rglob('fan1_input'))
        if not fan_input_files:
            return "No fan?"
        with open(fan_input_files[0], 'r') as file:
            rpm = file.read().strip()
        return f"{rpm} RPM"
    except FileNotFoundError:
        return "Fan RPM file not found"
    except PermissionError:
        return "Permission denied accessing the fan RPM file"
    except Exception as e:
        return f"Unexpected error: {e}"

def power_consumption_watts():
    output = check_output(['vcgencmd', 'pmic_read_adc']).decode("utf-8")
    lines = output.split('\n')
    amperages = {}
    voltages = {}
    for line in lines:
        cleaned_line = line.strip()
        if cleaned_line:
            parts = cleaned_line.split(' ')
            label, value = parts[0], parts[-1]
            val = float(value.split('=')[1][:-1])
            short_label = label[:-2]
            if label.endswith('A'):
                amperages[short_label] = val
            else:
                voltages[short_label] = val
    wattage = sum(amperages[key] * voltages[key] for key in amperages if key in voltages)
    return wattage

def display_status(shutdown):
    voltage, capacity = read_voltage_and_capacity(bus)
    cpu_volts = read_cpu_volts()
    cpu_amps = read_cpu_amps()
    cpu_temp = read_cpu_temp()
    input_voltage = read_input_voltage()
    fan_rpm = get_fan_rpm()
    pwr_use = power_consumption_watts()
    pld_state = get_pld_state()
    warn_status = ""

    if capacity >= 90:
        charge_status = "disabled"
        InputDevice(CHG_ONOFF_PIN, pull_up=True)
    else:
        charge_status = "enabled"
        InputDevice(CHG_ONOFF_PIN, pull_up=False)

    if pld_state == 1:
        power_status = "AC Power: OK! | Power Adapter: OK!"
    else:
        power_status = "Power Loss OR Power Adapter Failure!"

    if pld_state != 1 and capacity >= 51:
        warn_status = f"Running on UPS Backup Power | Batteries @ {capacity:.2f}%"
    elif pld_state != 1 and capacity <= 50 and capacity >= 25:
        warn_status = f"UPS Power levels approaching critical | Batteries @ {capacity:.2f}%"
    elif pld_state != 1 and capacity <= 24 and capacity >= 16:
        warn_status = f"UPS Power levels critical | Batteries @ {capacity:.2f}%"
    elif pld_state != 1 and capacity <= 15 and not shutdown:
        shutdown = True
        warn_status = "UPS Power failure imminent! Auto shutdown in 5 minutes!"
        call("sudo shutdown -P +5 'Power failure, shutdown in 5 minutes.'", shell=True)
    elif pld_state != 1 and shutdown:
        warn_status = "UPS Power failure imminent! Auto shutdown to occur within 5 minutes!"
    elif pld_state == 1 and shutdown:
        call("sudo shutdown -c 'Shutdown is cancelled'", shell=True)
        warn_status = "AC Power has been restored. Auto shutdown has been cancelled!"
        shutdown = False
    else:
        warn_status = ""

    print("\n========== X120x UPS Status ==========")
    print(f"UPS Voltage: {voltage:.3f}V")
    print(f"Battery: {capacity:.3f}%")
    print(f"Charging: {charge_status}")
    print("\n========== RPi5 System Stats ==========")
    print(f"Input Voltage: {input_voltage:.3f}V")
    print(f"CPU Volts: {cpu_volts:.3f}V")
    print(f"CPU Amps: {cpu_amps:.3f}A")
    print(f"System Watts: {pwr_use:.3f}W")
    print(f"CPU Temp: {cpu_temp:.1f}°C")
    print(f"Fan RPM: {fan_rpm}")
    print("\n========== Power Status ==========")
    print(power_status)
    if warn_status:
        print(f"WARNING: {warn_status}")
    print("======================================")
    return shutdown

if __name__ == "__main__":
    shutdown = False
    try:
        while True:
            shutdown = display_status(shutdown)
            time.sleep(30)  # Update every 30 seconds
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")
