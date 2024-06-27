# EEPROM initial test procedure
#
# - show beginning of test message on screen
# - if ic2bus is working
#        # now let's see if eeprom has been flashed before by ubo 
# 	     # proceed to read the content of eeprom
#        (1) First approach (requires reboot happened before)
#           -> ls /proc/device-tree/hat/
#           -> custom_0  custom_1  name  product  product_id  product_ver  uuid  vendor
#           - read content of these files; if they don't exist, then eeprom has not been setup yet  
#        (2) Second approach (no previos reboot required)
#            sudo ./eepflash.sh -r -f=eeprom_readback.eep -t=24c32
#            #convert eep file to text
#            ./eepdump eeprom_readback.eep eeprom_setting_readback.txt
#            # parse text file extract key values
# 		- check if it contains a valid serial number 
# 			- extract serial number, uuid, etc
# 			- show in screen
# 			- return result = true
#    	- else:
#    		- generate a serial number to write to eeprom
#           - control GPIO to allow write to EEPROM
# 			- write EEPRPM info and serial_number in test_report json file
#           - validate write (read back and compare binary files hashes??)
#    		- show success with serial number on screen
#    		- return result = true
# - else: 
# 	- show EEPROM error message
# 	- write EEPRPM into test_report json file
# 
#     "eeprom": {
#         "model": "CAT24C32",
#         "bus_address": "0x51",
#         "test_result": true
#     }

import time
import board
import os
import sys
import string
import random
import json

up_dir = os.path.dirname(os.path.abspath(__file__))+'/../../'
print(up_dir)
sys.path.append(up_dir)
from lcd import LCD as LCD
#from ubo_keypad import KEYPAD as KEYPAD
from ubo_keypad import * # Might have to revisit this form of import
from eeprom import *

lcd = LCD()
lcd.set_lcd_present(1)


def main():
    """ Script to self test EEPROM"""
    test_result = False
    info = {}
    lcd.display([(1,"Starting",0,"white"), (2,"EEPROM",0,"white"), (3,"Test", 0,"white")], 20)
    e2p = EEPROM()
    if e2p.bus_address:
        # check if eeprom ic2bus is working
        e2p.test_result = True
    else:
        e2p.test_result = False
        lcd.display([(1,"No EEPROM",0,"white"), (2,"IC Detected!",0,"white"), (3,chr(50),1,"red")], 20)
        time.sleep(1)
        # abort test here...
        # return
    try:
        e2p.read_eeprom()
        info = e2p.parse_eeprom()
        print(info)
        if (info.get("product_uuid") is not None):
            # eeprom does not have product uuid OR has product uuid but it is all zeros
            if (info.get("product_uuid") != '00000000-0000-0000-0000-000000000000'):
                # epprom has non-zero product uuid
                if info.get("custom_data"):
                    # it has some custom data in eeprom
                    cdata = info.get("custom_data")
                    if type(cdata) is dict:
                        if cdata.get("serial_number"):
                            # if eeprom custom data is not blank, then read the content 
                            # and check if it contains a valid serial number
                            serial_number = cdata["serial_number"]
                            if serial_number == 'ZNNEK99C84':
                                lcd.display([(1,"Erasing",0,"white"), (2,"EEPROM",0,"white"), (3,"Content", 0,"white")], 20)
                                e2p.reset_eeprom()
                                # lcd.display([(1,"EEPROM Reset",0,"white"), (2,"Successful!",0,"white"), (3,chr(56),1,"green")], 20)
                                lcd.display([(1,"Serial Number:",0,"white"), (2,serial_number,0,"green"), (3,"Erased...",0,"white")], 19)
                                summary = e2p.gen_summary()
                                serial_number = summary["serial_number"]
                                lcd.display([(1,"Overwritting",0,"white"), (2,"Serial Number:",0,"white"), (3,serial_number,0,"green"), (4,"Updating Data",0,"white"), (5,"Please Wait...",0,"white")], 19)
                                #update eeprom with custom data that contains serial number
                                print("creating a new serial_number.json file for summary")
                                e2p.update_json(summary, f_json=serial_number+".json")
                                print("#### updating eeprom with summary only, preserving existing product data #####")
                                e2p.update_eeprom(f_json=serial_number + ".json")
                            else:
                                # show serial number on screem
                                lcd.display([(1,"Already Has",0,"white"), (2,"Serial Number:",0,"white"), (3,serial_number,0,"green")], 19)
                                print("Already has serial number: " + serial_number)
                                #save custom data content into serial_number.json file
                                cdata['eeprom'] = {'model': '24c32', 'bus_address': "0x50", 'test_result': e2p.test_result }
                                e2p.update_json(summary=cdata, f_json=serial_number+".json")
                                print("update json summary suceeded!")
                                time.sleep(2)
                    else:
                        lcd.display([(1,"Corrupt",0,"white"), (2,"EEPROM",0,"white"), (3,"Content!", 0,"white")], 20)
                        time.sleep(1)
                        lcd.display([(1,"Erasing",0,"white"), (2,"EEPROM",0,"white"), (3,"Content", 0,"white")], 20)
                        e2p.reset_eeprom()
                        # lcd.display([(1,"EEPROM Reset",0,"white"), (2,"Successful!",0,"white"), (3,chr(56),1,"green")], 20)
                        summary = e2p.gen_summary()
                        serial_number = summary["serial_number"]
                        lcd.display([(1,"Generating",0,"white"), (2,"Serial Number:",0,"white"), (3,serial_number,0,"green"), (4,"Updating Data",0,"white"), (5,"Please Wait...",0,"white")], 19)
                        #update eeprom with custom data that contains serial number
                        print("creating a new serial_number.json file for summary")
                        e2p.update_json(summary, f_json=serial_number+".json")
                        print("#### updating eeprom with summary only, preserving existing product data #####")
                        e2p.update_eeprom(f_json=serial_number + ".json")
                else:
                    print("######eeprom has non-zero uuid but no custom data#####")
                    #generate a serial number
                    summary = e2p.gen_summary()
                    serial_number = summary["serial_number"]
                    # display serial on screen
                    lcd.display([(1,"Generated New",0,"white"), (2,"Serial Number:",0,"white"), (3,serial_number,0,"green"), (4,"Updating Data",0,"white"), (5,"Please Wait...",0,"white")], 19)
                    #update eeprom with custom data that contains serial number
                    print("creating a new serial_number.json file for summary")
                    e2p.update_json(summary, f_json=serial_number+".json")
                    print("#### updating eeprom with summary only, preserving existing product data #####")
                    e2p.update_eeprom(f_json=serial_number + ".json")
        else:
            # eeprom is blank
            print("###### eeprom is blank #######")
            # if first time programming eeprom, then write a new serial number, 
            # save content into [serial_number].json
            summary = e2p.gen_summary()
            serial_number = summary["serial_number"]
            lcd.display([(1,"Generated New",0,"white"), (2,"Serial Number:",0,"white"), (3,serial_number,0,"green"), (4,"Updating Data",0,"white"), (5,"Please Wait...",0,"white")], 19) 
            e2p.update_json(summary)
            # with open(serial_number + ".json", 'w') as outfile:
            #     json.dump(summary, outfile)
            print("#### updating eeprom with new custom data and product data...")
            e2p.update_eeprom(f_json = serial_number + ".json", \
                            f_setting = "eeprom_settings.txt")
    except Exception as e:
        print(e)
        e2p.test_result = False
    # display serial number on screen
    if e2p.test_result:
        # Display Test Result on LCD
        lcd.display([(1,"EEPROM",0,"white"), (2, "Test Result:", 0, "white"), (3,"Passed",0,"green"), (4,chr(56),1,"green")], 22)
        sys.exit(0)
    else:
        # Display Test Result on LCD
        lcd.display([(1,"EEPROM",0,"white"), (2, "Test Result:", 0, "white"), (3,"Failed",0,"red"), (4,chr(50),1,"red")], 22)
        sys.exit(1)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Interrupted')
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
