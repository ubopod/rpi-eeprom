import time
import board
import os
import sys
import string
import random
import json
import RPi.GPIO as GPIO
import subprocess as sp

up_dir = os.path.dirname(os.path.abspath(__file__))+'/../../'
print(up_dir)
print("hello")
sys.path.append(up_dir)

EEPROM_TOOLS_PATH = '/home/pi/ubo/setup/hats/eepromutils'

EEPROM_FILES = '/home/pi/ubo/tests/hw_acceptance/eeprom_files/'
JSON_PATH = '/home/pi/ubo/tests/hw_acceptance/test_results/'

if not os.path.exists(EEPROM_FILES):
  # Create a new directory because it does not exist 
  os.makedirs(EEPROM_FILES)
  print("The new EEPROM directory is created!")

if not os.path.exists(JSON_PATH):
  # Create a new directory because it does not exist 
  os.makedirs(JSON_PATH)
  print("The new JSON test result directory is created!")


#TODO: write a reset method to reset the eeprom with blank.eep image 

class EEPROM:
    def __init__(self):
        self.info = {}
        self.summary = {}
        self.serial_number = None
        self.bus_address = None
        self.test_result = False
        self.size_kbytes = 4
        self.model = "24c32"
        self.binary_file = EEPROM_FILES + "eeprom.eep"
        self.binary_readback_file = EEPROM_FILES + "eeprom_readback.eep"
        self.text_file = "eeprom_settings.txt"
        self.readback_text_file = EEPROM_FILES + "eeprom_readback.txt"
        self.json_file = "test_summary.json"
        self.temp_readback = EEPROM_FILES + "temp_readback.txt"
        self.blank_readback_file = EEPROM_FILES + "blank_readback.eep"
        self.blank_file = EEPROM_FILES + "blank.eep"
        # Set this to the GPIO of EEPROM write protect (16):
        self.WRITE_PROTECT = 16
        #GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.WRITE_PROTECT, GPIO.OUT)
        self.clean_files()
        self.check_i2c()
        

    def clean_files(self):
        try:
            os.remove(self.readback_text_file)
        except OSError as error:
            print(error)
            print("eeprom_readback.txt not found!")
        try:
            os.remove(self.binary_readback_file)
        except OSError as error:
            print(error)
            print("eeprom_readback.eep not found!")


    def get_serial_number(self):
        if self.serial_number:
            return self.serial_number
        self.read_eeprom()
        info = self.parse_eeprom()
        try:
            if info:
                self.serial_number = info.get("custom_data").get("serial_number")
        except Exception as e:
            print(e)
            self.serial_number = None
        return self.serial_number

    def check_i2c(self):
        if (os.system("i2cdetect -y 0 | grep '50: 50'") == 0):
            print("eeprom detected!")
            self.bus_address = "0x50"
            self.test_result = True
        else:
            print("No eeprom detected!")
            self.bus_address = False
            self.test_result = False

    def gen_serial_number(self):
        N = 12  # serial number length
        # choose_from = string.ascii_uppercase + string.digits
        choose_from = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789" # 34 options
        #choose_from = "ABCDEFGHIJKLMNPQRSTUVWXYZabcdefghijklmnopqrstvwxyz0123456789~!@#$%^&*?<>=+" #74 options
        self.serial_number = ''.join(
                        random.SystemRandom().choice(choose_from) for _ in range(N)
                        )
        return self.serial_number

    def gen_summary(self):
        summary = {}
        summary["eeprom"] = {}
        summary["eeprom"]["model"] = self.model
        summary["eeprom"]["bus_address"] = self.bus_address
        summary["eeprom"]["test_result"] = self.test_result
        summary["serial_number"] = self.gen_serial_number()
        self.summary = summary
        return summary

    def parse_eeprom(self, filename = "eeprom_reedback.txt"):
        """ This function will read eeprom content and parses the information"""
        info = {}
        try:
            myfile = open(self.readback_text_file, "r")
        except OSError as error:
            print(error)
            print("File not found! EEPROM is empty")
            return info
        while myfile:
            line = myfile.readline()
            print(line)
            c_data = []
            #process line 
            if line.startswith("product_uuid"):
                info["product_uuid"] = line.split()[1]
            elif line.startswith("product_id"):
                info["product_id"] = line.split()[1]
            elif line.startswith("product_ver"):
                info["product_ver"] = line.split()[1]
            elif line.startswith("vendor"):
                info["vendor"] = line.split("\"")[1]
            elif line.startswith("product"):
                info["product "] = line.split("\"")[1]
            elif line.startswith("custom_data"):
                # TODO parse multiple custom data
                line = myfile.readline()
                while "End of atom" not in line:
                    c_data.extend(line.split())
                    line = myfile.readline()
                #info["cdata"] = c_data
                byte_array = bytearray.fromhex(''.join(c_data))
                custom_data =  byte_array.decode("ISO-8859-1")
                custom_data_clean = custom_data.replace("\n", "")
                print(custom_data_clean)
                try:
                    custom_data_json = json.loads(custom_data_clean)
                    info["custom_data"] = custom_data_json
                except: 
                    info["custom_data"] = custom_data
            if line == "":
                break
        myfile.close()
        return info

    def read_eeprom(self):
        if self.bus_address:
            #read EEPROM content into binary file eeprom_readback.eep
            sp.run(["sudo", EEPROM_TOOLS_PATH + "/eepflash.sh", "-r", "-f=" + self.binary_readback_file, "-y", "-t=" + self.model])
            # convert eep file to text file eeprom_readback.txt
            sp.run([EEPROM_TOOLS_PATH + "/eepdump", self.binary_readback_file, self.readback_text_file])
        else:
            print("No EEPROM is detected!")

    def reset_eeprom(self):
         # disable write protect
        # set port/pin value to 0/GPIO.LOW/False       
        GPIO.output(self.WRITE_PROTECT, GPIO.LOW)
        print("Making blank binary file")
        #os.system("dd if=/dev/zero ibs=1k count=" + str(self.size_kbytes) + " of=blank.eep")
        sp.run(["dd", "if=/dev/zero", "ibs=1k", "count=" + str(self.size_kbytes), "of=" + self.blank_file])
        print("Writing blank binary file")
        #os.system("sudo " + EEPROM_TOOLS_PATH + "/eepflash.sh -w -f=blank.eep -y -t=" + self.model)
        sp.run(["sudo", EEPROM_TOOLS_PATH + "/eepflash.sh", "-w", "-f=" + self.blank_file, "-y", "-t=" + self.model])     
        # write
        # enable write protect
        # set port/pin value to 1/GPIO.HIGH/True
        GPIO.output(self.WRITE_PROTECT, GPIO.HIGH)
        time.sleep(0.5)
        # a second level eeprom functional test to test reset fucntionality
        # to make sure the eeprom is reset to blank by making sure read back image DOES contain
        # all zeros (4K bytes to be exact) - this is an addition to testing whether the eeprom is
        # detected on the i2c bus
        p1 = sp.run(["sudo", EEPROM_TOOLS_PATH + "/eepflash.sh", "-r", "-f=" + self.blank_readback_file, "-y", "-t=" + self.model])
        print("GPIO 24 function is " + str(GPIO.gpio_function(24)))
        #p1.wait()
        with open(self.blank_readback_file, "rb") as f:
            byte = f.read(1)
            while byte:
                #print(byte)
                if (byte != b'\x00'):
                    print("EEPROM is not blank!")
                    self.bus_address = False
                    return False
                byte = f.read(1)
            print("EEPROM is blank!")
            return True 

    def write_eeprom(self, f_bin=None):
        if not f_bin:
            f_bin = self.binary_file # default to eeprom.eep
        if self.bus_address:
            # clean EEPROM first
            r = self.reset_eeprom()
            if (r == False):
                self.test_result = False
                print("EEPROM reset failed!")
                return False
            # disable write protect
            # set port/pin value to 0/GPIO.LOW/False       
            GPIO.output(self.WRITE_PROTECT, GPIO.LOW)
            print("Writing generated binary file")
            #os.system("sudo " + EEPROM_TOOLS_PATH + "/eepflash.sh -w -f=" + f_bin + " -y -t=" + self.model)
            sp.run(["sudo", EEPROM_TOOLS_PATH + "/eepflash.sh", "-w", "-f=" + f_bin, "-y", "-t=" + self.model])
            # readback
            print("Reading back binary file")
            #os.system("sudo " + EEPROM_TOOLS_PATH + "/eepflash.sh -r -f=" + self.binary_readback_file + " -y -t=" + self.model)
            sp.run(["sudo", EEPROM_TOOLS_PATH + "/eepflash.sh", "-r", "-f=" + self.binary_readback_file, "-y", "-t=" + self.model])
            # TODO: compare checksum of binary files
            # enable write protect
            # set port/pin value to 1/GPIO.HIGH/True
            GPIO.output(self.WRITE_PROTECT, GPIO.HIGH)
        else:
            print("No EEPROM is detected!")

    def read_eeprom_dt(self, index=0):
        try:
            with open("/proc/device-tree/hat/custom_" + str(index), "r") as read_file:
                data = json.load(read_file)
                return data
        except OSError as error:
            print(error)
            print("File not found! EEPROM is empty")
            return False

    def make_eeprom(self, f_txt=None, f_json=None ):
        if not f_txt:
            f_txt = EEPROM_FILES + self.text_file
        if not f_json:
            f_json = self.json_file
        #"./eepmake eeprom_settings.txt myhat-with-dt.eep myled.dtb -c myparams.json"
        print("Making eeprom binary file")
        print("settings is file: " + f_txt)
        print("json data is file: " + JSON_PATH + f_json)
        #os.system(EEPROM_TOOLS_PATH + "/eepmake " + f_txt + " " + self.binary_file + " -c " + f_json)
        sp.run([EEPROM_TOOLS_PATH + "/eepmake", f_txt, self.binary_file, "-c", JSON_PATH + f_json])
        print("Binary file is generated")

    def remove_custom_data(self, f_txt=None):
        if f_txt is None:
            f_txt = self.readback_text_file
        with open(self.temp_readback, "w") as write_file:
            with open(f_txt, "r") as read_file:
                #read line by line 
                line = read_file.readline()
                while line:
                    if "Start of atom #2" in line or "Start of atom #3" in line:
                        break
                    #write line to write_file
                    write_file.write(line)
                    line = read_file.readline()
                read_file.close()
            write_file.close()
        # overwrite self.readback_text_file with temp_readback.txt
        os.rename(self.temp_readback, self.readback_text_file) 


    def update_eeprom(self, f_json=None, f_setting=None):
        """ this method preserves uuid, and other eeprom settings
        It uses readback text and new json file to make a new binary 
        file, write the new binary file, and verify write action """
        #TODO: have a forced update option to update eeprom with new json file 
        # ignoring previous eeprom settings and have a safe update option to
        # preserve previous eeprom settings such as uuid, serial number, etc.
        serial_number = self.get_serial_number()
        if f_json is None:
            if serial_number:
                f_json = serial_number + ".json"
            else:
                f_json = self.json_file
        # make new binary using readback_text_file.txt which includes uuid, etc
        if f_setting is not None:
            print("Making new binary file using " + f_setting + " and " + f_json + " as custom date") 
            self.make_eeprom(f_txt= EEPROM_FILES + f_setting, f_json = f_json)
        else:
            # if no setting file is provided, use readback settings file 
            # clean readback_text_file.txt to remove any existing custom data
            print("Removing existing custom data")
            self.remove_custom_data(f_txt=self.readback_text_file)
            print("Making eeprom binary image with new custom data of json file")
            self.make_eeprom(f_txt=self.readback_text_file, f_json = f_json)
        print("writing new binary file to eeprom")
        r = self.write_eeprom()
        if (r == False):
            self.test_result = False
            print("EEPROM write failed!")
            return False
    
    def read_json(self, f_json=None):
        serial_number = self.get_serial_number()
        if not f_json:
            if serial_number:
                # if has serial number, then use correct summary file
                f_json = serial_number + ".json"
            else:
                # if no serial number exists due to eeprom problem, 
                # then use default summary file
                f_json = self.json_file
        #read data
        try:
            with open(JSON_PATH + f_json, "r") as read_file:
                data = json.load(read_file)
                read_file.close()
        except FileNotFoundError as error:
            print(error)
            print("File not found! Using empty summary")
            data = {}
        return data, f_json

    def update_json(self, summary={}, f_json=None):
        data, f_json = self.read_json(f_json)
        print("Updating json file: " + f_json)
        #update exising data with test summary info
        data.update(summary)
        #write updated data back to file
        with open(JSON_PATH + f_json, "w") as write_file:
            json.dump(data, write_file, indent=4)
            write_file.close()
        # if serial_number:
        #     #update eeprom contents with new test summary info
        #     self.update_eeprom(f_json = serial_number + ".json")


#TODO 
# (1) write some test to compare
# parsed json from readback file 
# with the one used to generate
# the binary (extracted json)
#
# (2) organize file paths; path
# for eepromutils, text & binary
# files
#

def main():
    """ Script to try EEPROM functions"""
    e2p = EEPROM()
    summary = {}
    summary["eeprom"] = {}
    summary["eeprom"]["model"] = e2p.model
    summary["eeprom"]["bus_address"] = e2p.bus_address
    summary["eeprom"]["test_result"] = True
    summary["serial_number"] = e2p.gen_serial_number()
    with open("summary.json", "w") as write_file:
        json.dump(summary, write_file, indent=4)
    e2p.read_eeprom()
    e2p.update_eeprom(f_json="summary.json")
    info = e2p.parse_eeprom()
    print(info)
    data = e2p.read_eeprom_dt()
    print(data)
    if data and e2p.bus_address:
        serial_number = data.get("serial_number")
        print(serial_number)
        # show serial number on screen
        # create json file with serial_number+timedate.json format
        ##################
        # "unique_id": ""
        # "version": "full"
        # customize eeprom_setting.txt, convert to eep, and flash
        # everytime a write operation is performed read back binary
        # file and do crc check90
    else:
        print("eeprom on i2c bus was not detected or eeprom is empty")
        # eeprom on i2c bus was not detected
        # ask user if they want to abort test or continue with tests



if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Interrupted')
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)