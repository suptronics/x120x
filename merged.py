#!/usr/bin/python3

import os
import struct
import smbus
import time
import logging
import subprocess
import gpiod
from subprocess import call

# User-configurable variables
SHUTDOWN_THRESHOLD = 3  # Number of consecutive failures required for shutdown
SLEEP_TIME = 60  # Time in seconds to wait between failure checks
Loop =  False

# Ensure only one instance of the script is running
pid = str(os.getpid())
pidfile = "/run/X1200.pid"

# Define functions for reading voltage and capacity
def readVoltage(bus):
    read = bus.read_word_data(address, 2)
    swapped = struct.unpack("<H", struct.pack(">H", read))[0]
    voltage = swapped * 1.25 / 1000 / 16
    return voltage

def readCapacity(bus):
    read = bus.read_word_data(address, 4)
    swapped = struct.unpack("<H", struct.pack(">H", read))[0]
    capacity = swapped / 256
    return capacity

if os.path.isfile(pidfile):
    print("Script already running")
    exit(1)
else:
    with open(pidfile, 'w') as f:
        f.write(pid)

try:
    # Initialize SMBus (I2C)
    bus = smbus.SMBus(1)
    address = 0x36
    
    # GPIO setup for AC power monitoring
    PLD_PIN = 6
    chip = gpiod.Chip('gpiochip4')
    pld_line = chip.get_line(PLD_PIN)
    pld_line.request(consumer="PLD", type=gpiod.LINE_REQ_DIR_IN)

    while True:
        failure_counter = 0

        # Main check logic
        for _ in range(SHUTDOWN_THRESHOLD):
            ac_power_state = pld_line.get_value()
            voltage = readVoltage(bus)
            capacity = readCapacity(bus)
            # Print and log status
            print(f"Voltage: {voltage:.2f}V, Capacity: {capacity:.2f}%, AC Power State: {'OK' if ac_power_state == 1 else 'FAIL'}","True")
            # Check for low battery
            if capacity < 20:
                print("Battery level critical.")
                failure_counter += 1
            elif voltage < 3.20:
                print("Battery voltage critical.")
                failure_counter += 1
            elif ac_power_state == 0:
                print("UPS is unplugged or AC power loss detected.")
                failure_counter += 1
            else:
                # If none of the conditions are met, it means everything is OK
                failure_counter = 0
                break

            if failure_counter < SHUTDOWN_THRESHOLD:
                time.sleep(SLEEP_TIME)  # Wait for the specified sleep time before the next check

        # Evaluate whether to shutdown
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
            # If the script exits the loop without reaching the shutdown threshold,
            # it means the conditions for a critical shutdown were not met in consecutive checks.
            #print("System operating within normal parameters. No action required.")
            if Loop:
                # If the conditions for a shutdown are not met, wait before starting the next set of checks
                time.sleep(SLEEP_TIME)
            else:
                exit(0)

finally:
    if os.path.isfile(pidfile):
        os.unlink(pidfile)
    exit(0)

