#!/usr/bin/python3

import os
import struct
import smbus2
import time
import logging
import subprocess
import gpiod
from subprocess import call

# User-configurable variables
SHUTDOWN_THRESHOLD = 3  # Number of consecutive failures required for shutdown
SLEEP_TIME = 60  # Time in seconds to wait between failure checks
Loop =  False

def readVoltage(bus):
    read = bus.read_word_data(address, 2) # reads word data (16 bit)
    swapped = struct.unpack("<H", struct.pack(">H", read))[0] # big endian to little endian
    voltage = swapped * 1.25 / 1000 / 16 # convert to understandable voltage
    return voltage

def readCapacity(bus):
    read = bus.read_word_data(address, 4) # reads word data (16 bit)
    swapped = struct.unpack("<H", struct.pack(">H", read))[0] # big endian to little endian
    capacity = swapped / 256 # convert to 1-100% scale
    return capacity

def get_battery_status(voltage):
    if 3.87 <= voltage <= 4.2:
        return "Full"
    elif 3.7 <= voltage < 3.87:
        return "High"
    elif 3.55 <= voltage < 3.7:
        return "Medium"
    elif 3.4 <= voltage < 3.55:
        return "Low"
    elif voltage < 3.4:
        return "Critical"
    else:
        return "Unknown"

# Ensure only one instance of the script is running
pid = str(os.getpid())
pidfile = "/var/run/X1200.pid" # move to /var/run because of conventions
if os.path.isfile(pidfile):
    print("Script already running")
    exit(1)
else:
    with open(pidfile, 'w') as f:
        f.write(pid)

try:
    bus = smbus2.SMBus(1)
    address = 0x36
    PLD_PIN = 6
    chip = gpiod.Chip('gpiochip0') # since kernel release 6.6.45 you have to use 'gpiochip0' - before it was 'gpiochip4'
    pld_line = chip.get_line(PLD_PIN)
    pld_line.request(consumer="PLD", type=gpiod.LINE_REQ_DIR_IN)

    while True:
        failure_counter = 0

        for _ in range(SHUTDOWN_THRESHOLD):
            ac_power_state = pld_line.get_value()
            voltage = readVoltage(bus)
            battery_status = get_battery_status(voltage)
            capacity = readCapacity(bus)
            print(f"Capacity: {capacity:.2f}% ({battery_status}), AC Power State: {'Plugged in' if ac_power_state == 1 else 'Unplugged'}, Voltage: {voltage:.2f}V")
            if ac_power_state == 0:
                print("UPS is unplugged or AC power loss detected.")
                failure_counter += 1
                if capacity < 20:
                    print("Battery level critical.")
                    failure_counter += 1
                if voltage < 3.20:
                    print("Battery voltage critical.")
                    failure_counter += 1
            else:
                failure_counter = 0
                break

            if failure_counter < SHUTDOWN_THRESHOLD:
                time.sleep(SLEEP_TIME) 

        if failure_counter >= SHUTDOWN_THRESHOLD:
            shutdown_reason = ""
            if capacity < 20:
                shutdown_reason = "due to critical battery level."
            elif voltage < 3.20:
                shutdown_reason = "due to critical battery voltage."
            elif ac_power_state == 0:
                shutdown_reason = "due to AC power loss or UPS unplugged."

            shutdown_message = f"Critical condition met {shutdown_reason} Initiating shutdown."
            print(shutdown_message)
            call("sudo nohup shutdown -h now", shell=True)
        else:
            #print("System operating within normal parameters. No action required.")
            if Loop:
                time.sleep(SLEEP_TIME)
            else:
                exit(0)

finally:
    if os.path.isfile(pidfile):
        os.unlink(pidfile)
    exit(0)

