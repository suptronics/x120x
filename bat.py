#!/usr/bin/env python3
#This python script is only suitable for UPS Shield X1200, X1201 and X1202

import struct
import smbus2
import time
from subprocess import call

def readVoltage(bus):

     address = 0x36
     read = bus.read_word_data(address, 2)
     swapped = struct.unpack("<H", struct.pack(">H", read))[0]
     voltage = swapped * 1.25 /1000/16
     return voltage


def readCapacity(bus):

     address = 0x36
     read = bus.read_word_data(address, 4)
     swapped = struct.unpack("<H", struct.pack(">H", read))[0]
     capacity = swapped/256
     return capacity


bus = smbus2.SMBus(1)

while True:

 print ("******************")
 print ("Voltage:%5.2fV" % readVoltage(bus))

 print ("Battery:%5i%%" % readCapacity(bus))

 if readCapacity(bus) == 100:

         print ("Battery FULL")

 if readCapacity(bus) < 20:

         print ("Battery Low")

#Set battery low voltage to shut down
 if readVoltage(bus) < 3.20:

         print ("Battery LOW!!!")
         print ("Shutdown in 5 seconds")
         time.sleep(5)
         call("sudo nohup shutdown -h now", shell=True)

 time.sleep(2)
