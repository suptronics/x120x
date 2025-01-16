#!/usr/bin/env python3
# This script is improved by @p1r473, Thanks for his contribution and support
# Improved UPS power monitoring by madbear with bits from SupTronics Technologies
# originals: https://github.com/suptronics/x120x.git
# only suitable for use with a Raspberry Pi 5 running Raspberry Pi OS with desktop
# and the below UPS HATs:
# http://suptronics.com/Raspberrypi/Power_mgmt/x1200-v1.2.html
# http://suptronics.com/Raspberrypi/Power_mgmt/x1201-v1.1.html
# http://suptronics.com/Raspberrypi/Power_mgmt/x1202-v1.1.html
# http://suptronics.com/Raspberrypi/Power_mgmt/x1203-v1.0.html

import sys
import struct
from pathlib import Path
from subprocess import check_output, CalledProcessError, call
import smbus2
from PyQt5.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QIcon
from gpiozero import InputDevice, Button

# Constants
CHG_ONOFF_PIN = 16 # pinctrl get 16
PLD_BUTTON = Button(6) # down = fail, up = pass
bus = smbus2.SMBus(1) # i2cdetect -y 1

def read_voltage_and_capacity(bus):
    address = 0x36 # i2cget -y 1 0x36 ...
    voltage_read = bus.read_word_data(address, 2) # 0x02 w
    capacity_read = bus.read_word_data(address, 4) # 0x04 w
    voltage_swapped = struct.unpack("<H", struct.pack(">H", voltage_read))[0] # big endian to little endian
    voltage = voltage_swapped * 1.25 / 1000 / 16 # convert to understandable voltage
    capacity_swapped = struct.unpack("<H", struct.pack(">H", capacity_read))[0] # big endian to little endian
    capacity = capacity_swapped / 256 # convert to 1-100% scale
    return voltage, capacity

def get_pld_state():
    if PLD_BUTTON.is_pressed:
        return 0 # power loss/adapter failure
    else:
        return 1 # power ok

def read_hardware_metric(command_args, strip_chars): #(["command","arg1", "arg2",...],'strip_chars') ** not likely to be very useful outside of vcgencmd **
    try:
        output = check_output(command_args).decode("utf-8") # runs a command w/ args and captures its output converting to UTF-8 encoded string
        metric_str = output.split("=")[1].strip().rstrip(strip_chars)
                    # split output string into a list using "="
                    # [1] selects the second element of the list
                    # strip any leading/trailing whitespace
                    # further strips specific characters (strip_chars) from result
        return float(metric_str) # converts the cleaned-up string to float and returns it.
    except (CalledProcessError, ValueError) as e: # command not found, command fails, ValueError could occur if converting cleaned string to float fails
        print(f"Error reading hardware metric: {e}")
        return None

def read_cpu_volts(): 
    return read_hardware_metric(["vcgencmd", "pmic_read_adc", "VDD_CORE_V"], 'V') # return current cpu voltage

def read_cpu_amps():
    return read_hardware_metric(["vcgencmd", "pmic_read_adc", "VDD_CORE_A"], 'A') # reurn current cpu amperage

def read_cpu_temp():
    return read_hardware_metric(["vcgencmd", "measure_temp"], "'C") # return current cpu temp

def read_input_voltage():
    return read_hardware_metric(["vcgencmd", "pmic_read_adc", "EXT5V_V"], 'V') # return input voltage

def get_fan_rpm():
    try:
        sys_devices_path = Path('/sys/devices/platform/cooling_fan') 
        fan_input_files = list(sys_devices_path.rglob('fan1_input')) # scan path for fan1_input (sometimes its under hwmon2, sometimes hwmon3...)
        if not fan_input_files: # nothing found?
            return "No fan?"
        with open(fan_input_files[0], 'r') as file: # file found, opened
            rpm = file.read().strip() # read value and strip anything else
        return f"{rpm} RPM" # return "xxxx RPM"
    except FileNotFoundError: 
        return "Fan RPM file not found"
    except PermissionError:
        return "Permission denied accessing the fan RPM file"
    except Exception as e:
        return f"Unexpected error: {e}"

def power_consumption_watts():
    output = check_output(['vcgencmd', 'pmic_read_adc']).decode("utf-8") # gets a printout of all rpi5 voltages/amperages, converts output from binary to utf-8 string
    lines = output.split('\n') # splits the output based on newline
    amperages = {} # initialize amps dictionary
    voltages = {} # initialize volts dictionary
    for line in lines: # go through all lines one by one
        cleaned_line = line.strip() # removes any leading or trailing whitespace from the line
        if cleaned_line: # checks if the line is not empty after stripping
            parts = cleaned_line.split(' ') # split into parts based on spaces
            label, value = parts[0], parts[-1] # label = V or A, value = reading
            val = float(value.split('=')[1][:-1]) # convert value to float
            short_label = label[:-2] # 
            if label.endswith('A'): # If the label ends with 'A', it's an amperage value and is added to the amperages dictionary
                amperages[short_label] = val
            else: # Otherwise, it's added to the voltages dictionary
                voltages[short_label] = val
    wattage = sum(amperages[key] * voltages[key] for key in amperages if key in voltages) # iterates over each key in amperages
    return wattage                                                                        # and checks if the same key exists in voltages
                                                                                          # then multiplies the keys to get system wattage
class UPSStatusWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(" X120X UPS Status ")
        self.setStyleSheet("BACKGROUND-COLOR: #2C132C;")
        self.resize(450, 380)
        self.label = QLabel(self)
        self.label.setMinimumSize(450, 380)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("COLOR: #FFFFFF; FONT-WEIGHT: bold; FONT-SIZE: 14pt;")
        self.label.setAlignment(Qt.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        self.setLayout(layout)
        # Populate initial data
        self.shutdown = False
        self.update_status()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_status)
        self.timer.start(30000)  ## milliseconds

    def update_status(self):
        voltage, capacity = read_voltage_and_capacity(bus)
        cpu_volts = read_cpu_volts()
        cpu_amps = read_cpu_amps()
        cpu_temp = read_cpu_temp()
        input_voltage = read_input_voltage()
        fan_rpm = get_fan_rpm()
        pwr_use = power_consumption_watts()
        pld_state = get_pld_state()
        warn_status = ""

        if capacity >= 90: # up = disabled
            charge_status = "<FONT COLOR='#FF0000'>disabled</FONT>"
            InputDevice(CHG_ONOFF_PIN,pull_up=True)
        else: # down = enabled
            charge_status = "<FONT COLOR='#FF0000'>enabled</FONT>"
            InputDevice(CHG_ONOFF_PIN,pull_up=False)

        if pld_state == 1:
            power_status = "<FONT COLOR='#00FF00'>\U00002714 AC Power: OK! \U00002714<BR/>\U00002714 Power Adapter: OK! \U00002714</FONT>"
        else:
            power_status = "<FONT COLOR='#FF0000'>\U000026A0 Power Loss OR Power Adapter Failure \U000026A0</FONT>"

        if pld_state != 1 and capacity >=51:
            warn_status = f"<FONT COLOR='#FF0000';FONT-SIZE: 14pt;>Running on UPS Backup Power<BR/>Batteries @{capacity:.2f}&#37;"
        elif pld_state != 1 and capacity <= 50 and capacity >= 25:
            warn_status = f"<FONT COLOR='#FF0000';FONT-SIZE: 14pt;>UPS Power levels approaching critical,<BR/>Batteries @{capacity:.2f}&#37;</FONT><BR/>"
        elif pld_state != 1 and capacity <= 24 and capacity >= 16:
            warn_status = f"<FONT COLOR='#FF0000';FONT-SIZE: 16pt;>UPS Power levels critical,<BR/>Batteries @{capacity:.2f}&#37;</FONT><BR/>"
        elif pld_state != 1 and capacity <= 15 and not self.shutdown:
            self.shutdown = True
            warn_status = "<FONT COLOR='#FF0000';FONT-SIZE: 18pt;>UPS Power failure imminent!<BR/>Auto shutdown to occur in 5 minutes!</FONT><BR/>"
            call("sudo shutdown -P +5 'Power failure, shutdown in 5 minutes.'", shell=True)
        elif pld_state != 1 and self.shutdown:
            warn_status = "<FONT COLOR='#FF0000';FONT-SIZE: 18pt;>UPS Power failure imminent!<BR/>Auto shutdown to occur within 5 minutes!</FONT><BR/>"
        elif pld_state == 1 and self.shutdown:
            call("sudo shutdown -c 'Shutdown is cancelled'", shell=True)
            warn_status = "<FONT COLOR='#00FF00';FONT-SIZE: 18pt;>AC Power has been restored<BR/>Auto shutdown has been cancelled!</FONT><BR/>"
            self.shutdown = False
        else:
            warn_status = ""

        text = (
            f"<FONT COLOR='#9C009C'>-=-=-=-=-=</FONT><FONT COLOR='#FF00FF'> X120x Stats </FONT><FONT COLOR='#9C009C'>=-=-=-=-=-</FONT><BR/>"
            f"UPS Voltage: <FONT COLOR='#FF0000'>{voltage:.3f}V</FONT><BR/>"
            f"Battery: <FONT COLOR='#FF0000'>{capacity:.3f}&#37;</FONT><BR/>"
            f"Charging: </FONT>{charge_status}</FONT><BR/>"
            f"<FONT COLOR='#9C009C'>-=-=-=-=-=</FONT><FONT COLOR='#FF00FF'> RPi5 Stats </FONT><FONT COLOR='#9C009C'>=-=-=-=-=-</FONT><BR/>"
            f"Input Voltage: <FONT COLOR='#FF0000'>{input_voltage:.3f}V</FONT><BR/>"
            f"CPU Volts: <FONT COLOR='#FF0000'>{cpu_volts:.3f}V</FONT><BR/>"
            f"CPU Amps: <FONT COLOR='#FF0000'>{cpu_amps:.3f}A</FONT><BR/>"
            f"System Watts: <FONT COLOR='#FF0000'>{pwr_use:.3f}W</FONT><BR/>"
            f"CPU Temp: <FONT COLOR='#FF0000'>{cpu_temp:.1f}&deg;C</FONT><BR/>"
            f"Fan RPM: <FONT COLOR='#FF0000'>{fan_rpm}</FONT><BR/>"
            f"<FONT COLOR='#9C009C'>-=-=-= <FONT COLOR='#FF00FF'>\U000026A1 Power Status \U000026A1 </FONT><FONT COLOR='#9C009C'>=-=-=-</FONT><BR/>"
            f"{power_status}<BR/>"
            f"{warn_status}"
        )
        self.label.setText(text)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = UPSStatusWindow()
    icon = QIcon("/usr/share/icons/accumulator.png")
    window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec_())
