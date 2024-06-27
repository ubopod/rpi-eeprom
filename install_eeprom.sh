git clone https://github.com/raspberrypi/hats.git
wget -c https://raw.githubusercontent.com/RobertCNelson/tools/master/pkgs/dtc.sh
chmod +x dtc.sh
./dtc.sh
# then install these
cd hats/eepromutils/
make && sudo make install