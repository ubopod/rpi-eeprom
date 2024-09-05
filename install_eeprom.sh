git clone https://github.com/raspberrypi/utils
sudo apt install cmake
# then install these
cd utils/eeptools
cmake .
make
sudo make install
sudo dtoverlay i2c-gpio i2c_gpio_sda=0 i2c_gpio_scl=1 bus=9
