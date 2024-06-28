import time
import os
import sys

up_dir = os.path.dirname(os.path.abspath(__file__))+'/../../'
print(up_dir)
sys.path.append(up_dir)
from eeprom import *


def main():
    """ Script to self test EEPROM"""
    test_result = False
    info = {}
    print("starting eeprom test...")
    e2p = EEPROM()
    if e2p.bus_address:
        # check if eeprom ic2bus is working
        e2p.test_result = True
    else:
        e2p.test_result = False
        print("no eeprom IC detected!")
        time.sleep(1)
        # abort test here...
        return
    try:
        e2p.update_serial("ZFH2UL4UGF")
    except Exception as e:
        print(e)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Interrupted')
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
