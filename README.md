## Testing EEPROM ROM

When the test starts, it first run `tests/hw_acceptance/test_eeprom.py` script that tests the EEPROM and write some initializtion data on it. To test the EEPROM, it first checks it the device is detected on the correct I2C bus address. Then, it reads the content to see if the EEPROM has been tested before and contains valid information. If so, it terminates the process and the scripts proceeds to next step. 

If the EEPROM does not contain recognizable information and it has not been programmed previously, it writes all zeros to the memory (erases the content) and reads back the content to make sure it is all zero.

Valid EEPROM entry must contain non-zero `product_uuid`, and `serial_number` in the custom binary data (json-formatted).


```
# Vendor info
# 128 bit UUID. If left at zero eepmake tool will auto-generate
# RFC 4122 compliant UUID

product_uuid 12345678-1234-1234-1234-012345678910 #MUST BE NON ZERO

# 16 bit product id
product_id 0x0105

# 16 bit product version
product_ver 0x0001

# ASCII vendor string  (max 255 characters)
vendor "Ubo Technology Company"

# ASCII product string (max 255 characters)
product "Ubo HAT"

# Custom binary data
SOMECUSTOMINFORMATIONHERE
```
For more information, checkout EEPROM repo here.

If the EEPROM does not contain valid and recognable information, the script writes test result data, as well as a randomly generated serial number that would be unqiue to each HAT. If it already contains a valid serial number, the test would not write new information on it. It just reads the serial number for updating subsequenct test results. 
