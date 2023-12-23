#!/usr/bin/env python3
#This python script is only suitable for UPS Shield X1200, X1201 and X1202

import gpiod
import time
from subprocess import call

PLD_PIN = 6
chip = gpiod.Chip('gpiochip4')
pld_line = chip.get_line(PLD_PIN)
pld_line.request(consumer="PLD", type=gpiod.LINE_REQ_DIR_IN)
try:
   while True:
       pld_state = pld_line.get_value()
       if pld_state == 1:
            print ("---AC Power OK,Power Adapter OK---")
            time.sleep(1)
       else:
            print ("---AC Power Loss OR Power Adapter Failure---")
            time.sleep(1)
            #call("sudo nohup shutdown -h now", shell=True)  #uncomment to implement shutdown when power outage

finally:

 pld_line.release()