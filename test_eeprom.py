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
        # return
    try:
        e2p.read_eeprom()
        print("eeprom content read successfully! now parsing...")
        info = e2p.parse_eeprom()
        print("printing parsed readback eeprom info")
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
                                print("erasing eeprom content...")
                                e2p.reset_eeprom()
                                print("serial number: ", serial_number)
                                summary = e2p.gen_summary()
                                serial_number = summary["serial_number"]
                                print("overwriting serial number: ", serial_number)
                                #update eeprom with custom data that contains serial number
                                print("creating a new serial_number.json file for summary")
                                e2p.update_json(summary, f_json=serial_number+".json")
                                print("#### updating eeprom with summary only, preserving existing product data #####")
                                e2p.update_eeprom(f_json=serial_number + ".json")
                            else:
                                # show serial number on screem
                                print("Already has serial number: " + serial_number)
                                #save custom data content into serial_number.json file
                                cdata['eeprom'] = {'model': '24c32', 'bus_address': "0x50", 'test_result': e2p.test_result }
                                e2p.update_json(summary=cdata, f_json=serial_number+".json")
                                print("update json summary suceeded!")
                                time.sleep(2)
                    else:
                        print("Corrupt EEPROM content!")
                        time.sleep(1)
                        print("Erasing EEPROM content...")
                        e2p.reset_eeprom()
                        summary = e2p.gen_summary()
                        serial_number = summary["serial_number"]
                        print("Generating serial number: ", serial_number)
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
                    print("Generated new serial number: ", serial_number)
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
            print("Generated new serial number: ", serial_number)
            e2p.update_json(summary)
            # with open(serial_number + ".json", 'w') as outfile:
            #     json.dump(summary, outfile)
            print("#### updating eeprom with new custom data and product data...")
            e2p.update_eeprom(f_json = serial_number + ".json", \
                            f_setting = "eeprom_settings.txt")
    except Exception as e:
        print("Execption caught!")
        print(e)
        e2p.test_result = False
    # display serial number on screen
    if e2p.test_result:
        # Display Test Result on LCD
        print("EEPROM test passed!")
        sys.exit(0)
    else:
        # Display Test Result on LCD
        print("EEPROM test failed!")
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
