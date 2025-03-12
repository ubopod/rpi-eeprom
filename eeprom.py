import time
import os
import random
import json
import logging
import platform
from typing import Dict, Optional, Tuple, Any, Union
from dataclasses import dataclass
from pathlib import Path
import subprocess as sp
from datetime import datetime

# Mock class for non-Raspberry Pi environments
class MockDigitalOutputDevice:
    """Mock implementation of gpiozero.DigitalOutputDevice for non-Raspberry Pi environments."""
    def __init__(self, pin: int):
        self.pin = pin
        self._state = False
        logging.debug(f"Initialized mock GPIO pin {pin}")
        
    def on(self) -> None:
        """Turn the pin on."""
        self._state = True
        logging.debug(f"Mock GPIO pin {self.pin} turned ON")
        
    def off(self) -> None:
        """Turn the pin off."""
        self._state = False
        logging.debug(f"Mock GPIO pin {self.pin} turned OFF")

# Conditionally import gpiozero or use mock class
if platform.system() == "Linux" and os.path.exists("/proc/device-tree/model"):
    try:
        from gpiozero import DigitalOutputDevice
    except ImportError:
        logging.warning("Failed to import gpiozero. Using mock implementation.")
        DigitalOutputDevice = MockDigitalOutputDevice
else:
    logging.info("Non-Raspberry Pi environment detected. Using mock GPIO implementation.")
    DigitalOutputDevice = MockDigitalOutputDevice

class EEPROMError(Exception):
    """Base exception for EEPROM operations."""
    pass

class EEPROMConfigError(EEPROMError):
    """Exception raised when configuration is invalid."""
    pass

class EEPROMNotFoundError(EEPROMError):
    """Exception raised when EEPROM is not detected."""
    pass

class EEPROMWriteError(EEPROMError):
    """Exception raised when writing to EEPROM fails."""
    pass

class EEPROMReadError(EEPROMError):
    """Exception raised when reading from EEPROM fails."""
    pass

@dataclass
class EEPROMConfig:
    """Configuration for EEPROM operations."""
    tools_path: Path
    files_path: Path
    json_path: Path
    model: str = "24c32"
    size_kbytes: int = 4
    write_protect_pin: int = 16
    i2c_bus: int = 9  # Default I2C bus number
    i2c_address: str = "0x50"  # Default I2C device address

    def __post_init__(self) -> None:
        """Ensure directories exist after initialization and validate parameters."""
        self.tools_path.mkdir(parents=True, exist_ok=True)
        self.files_path.mkdir(parents=True, exist_ok=True)
        self.json_path.mkdir(parents=True, exist_ok=True)
        
        # Validate I2C parameters
        if not isinstance(self.i2c_bus, int) or self.i2c_bus < 0:
            raise EEPROMConfigError(f"Invalid I2C bus number: {self.i2c_bus}")
            
        if not isinstance(self.i2c_address, str) or not self.i2c_address.startswith("0x"):
            raise EEPROMConfigError(f"Invalid I2C address format: {self.i2c_address}")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('eeprom.log')
    ]
)
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_CONFIG = EEPROMConfig(
    tools_path=Path('/usr/local/bin'),
    files_path=Path('./'),
    json_path=Path('./'),
    i2c_bus=9,
    i2c_address="0x50"
)

def run_command(cmd: list[str], check: bool = True, **kwargs) -> sp.CompletedProcess:
    """Run a shell command safely.
    
    Args:
        cmd: Command to run as list of strings
        check: Whether to check return code
        **kwargs: Additional arguments to pass to subprocess.run
        
    Returns:
        CompletedProcess instance
        
    Raises:
        subprocess.CalledProcessError: If command fails and check is True
    """
    try:
        return sp.run(
            cmd,
            capture_output=True,
            text=True,
            check=check,
            **kwargs
        )
    except sp.CalledProcessError as e:
        logger.error(f"Command failed: {' '.join(cmd)}")
        logger.error(f"Error output: {e.stderr}")
        raise

class EEPROM:
    """Class to manage EEPROM operations."""
    
    def __init__(self, config: Optional[EEPROMConfig] = None) -> None:
        """Initialize EEPROM with optional configuration.
        
        Args:
            config: Optional configuration object. If not provided, uses default config.
        """
        self.config = config or DEFAULT_CONFIG
        self.info: Dict[str, Any] = {}
        self.summary: Dict[str, Any] = {}
        self.serial_number: Optional[str] = None
        self.test_result: bool = False
        
        # Binary files for EEPROM operations
        self.image_binary = self.config.files_path / "eeprom_image.eep"  # Binary ready to flash
        self.readback_binary = self.config.files_path / "eeprom_readback.eep"  # Raw EEPROM content
        self.blank_binary = self.config.files_path / "blank.eep"  # For reset
        self.blank_readback_binary = self.config.files_path / "blank_readback.eep"  # Verify reset
        
        # Text and configuration files
        self.template_text = self.config.files_path / "eeprom_template.txt"  # Base settings
        self.dump_text = self.config.files_path / "eeprom_dump.txt"  # Human readable dump
        self.temp_text = self.config.files_path / "temp_dump.txt"  # For processing
        self.default_config = "default_config.json"  # Default JSON config
        
        # GPIO setup
        self.write_protect = DigitalOutputDevice(self.config.write_protect_pin)
        
        self._clean_files()
        self._check_i2c()
        

    def _clean_files(self) -> None:
        """Internal method to clean up temporary files."""
        try:
            os.remove(self.dump_text)
        except OSError as error:
            logger.warning(f"Error removing dump file: {error}")
            logger.debug("eeprom_dump.txt not found!")
        try:
            os.remove(self.readback_binary)
        except OSError as error:
            logger.warning(f"Error removing readback file: {error}")
            logger.debug("eeprom_readback.eep not found!")


    def get_serial_number(self) -> Optional[str]:
        """Get the serial number from the EEPROM.
        
        This is a convenience function that:
        1. Returns previously retrieved and cached serial number if available
        2. Otherwise reads EEPROM content to find serial number
        3. Caches the found serial number
        
        Returns:
            Current serial number or None if not found
        """
        if self.serial_number:
            return self.serial_number
        self._read_raw_eeprom()
        info = self._parse_eeprom_text()
        try:
            if info:
                self.serial_number = info.get("custom_data", {}).get("serial_number")
        except Exception as e:
            logger.error(f"Error getting serial number: {e}")
            self.serial_number = None
        return self.serial_number

    def _check_i2c(self) -> None:
        """Internal method to check if EEPROM is detected on I2C bus."""
        if (os.system(f"i2cdetect -y {self.config.i2c_bus} | grep '{self.config.i2c_address[2:]}:'") == 0):
            logger.info("EEPROM detected!")
            self.test_result = True
        else:
            logger.warning("No EEPROM detected!")
            self.test_result = False

    def generate_serial_number(self) -> str:
        """Generate a random serial number."""
        N: int = 12  # serial number length
        choose_from: str = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789"
        self.serial_number = ''.join(
            random.SystemRandom().choice(choose_from) for _ in range(N)
        )
        return self.serial_number

    def generate_summary(self) -> Dict[str, Any]:
        """Generate a summary for the EEPROM."""
        summary: Dict[str, Any] = {
            "eeprom": {
                "model": self.config.model,
                "i2c_bus": self.config.i2c_bus,
                "i2c_address": self.config.i2c_address,
                "test_result": self.test_result
            },
            "serial_number": self.generate_serial_number()
        }
        self.summary = summary
        return summary

    def _read_raw_eeprom(self) -> None:
        """Internal method to read raw binary data from EEPROM hardware."""
        if self.test_result:
            run_command(
                ["sudo", f"{self.config.tools_path}/eepflash.sh", "-r", f"-d={self.config.i2c_bus}", f"-a={self.config.i2c_address[2:]}", f"-f={self.readback_binary}", "-y", f"-t={self.config.model}"]
            )
            run_command(
                [f"{self.config.tools_path}/eepdump", self.readback_binary, self.dump_text]
            )
        else:
            logger.error("No EEPROM is detected!")

    def _parse_eeprom_text(self, filename: str = "eeprom_dump.txt") -> Dict[str, Any]:
        """Internal method to parse the human-readable EEPROM text file."""
        info: Dict[str, Any] = {}
        custom_data_sections: list[Any] = []  # List to store all custom data sections
        
        try:
            with open(self.dump_text, "r") as myfile:
                for line in myfile:
                    line = line.strip()
                    if not line:
                        continue
                    
                    if line.startswith("product_uuid"):
                        info["product_uuid"] = line.split()[1]
                    elif line.startswith("product_id"):
                        info["product_id"] = line.split()[1]
                    elif line.startswith("product_ver"):
                        info["product_ver"] = line.split()[1]
                    elif line.startswith("vendor"):
                        info["vendor"] = line.split("\"")[1]
                    elif line.startswith("product"):
                        info["product"] = line.split("\"")[1]
                    elif line.startswith("dt_blob"):
                        info["dt_blob"] = line.split("\"")[1]
                    elif line.startswith("custom_data"):
                        logger.debug("Found custom_data section")
                        # Read all lines until we find the closing quote
                        json_lines = []
                        while True:
                            data_line = myfile.readline().strip()
                            if not data_line:
                                continue
                            if data_line.endswith('\\\"'):  # Found closing quote
                                json_lines.append(data_line[:-2])  # Remove closing quote
                                break
                            json_lines.append(data_line)
                        
                        if json_lines:
                            try:
                                # Join lines and parse as JSON
                                json_str = ''.join(json_lines).strip()
                                # Remove any remaining quotes at start/end
                                logger.info(f"JSON data before stripping: {json_str}")
                                json_str = json_str.strip('"')
                                logger.info(f"Parsing JSON data: {json_str}")
                                parsed_data = json.loads(json_str)
                                custom_data_sections.append(parsed_data)
                                logger.info("Successfully parsed custom data section")
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse custom data as JSON: {e}")
                                logger.info(f"Raw data that failed to parse: {json_str}")
                                custom_data_sections.append(json_str)
                            
        except OSError as error:
            logger.error(f"Error reading EEPROM file: {error}")
        
        # Store all custom data sections
        if custom_data_sections:
            info["custom_data"] = custom_data_sections[0]  # Keep first section as before for backward compatibility
            info["custom_data_all"] = custom_data_sections  # Store all sections in a new field
            logger.debug(f"Parsed custom data: {info['custom_data']}")
        else:
            logger.warning("No custom data sections found")
        
        return info

    def read_eeprom_content(self) -> Optional[Dict[str, Any]]:
        """Read and parse all EEPROM content into structured data.
        
        This is the main high-level function to read EEPROM content. It:
        1. Reads raw binary data from EEPROM hardware
        2. Converts it to human-readable format
        3. Parses into structured data with product info and custom data
        
        This should be your go-to function for reading EEPROM content.
        
        Returns:
            Dict containing all EEPROM data or None if read fails
            The dict includes:
            - product_uuid: Unique identifier
            - product_id: Product identifier
            - product_ver: Product version
            - vendor: Vendor name
            - product: Product name
            - custom_data: Custom JSON data including serial number
        """
        try:
            self._read_raw_eeprom()
            logger.info("EEPROM content read successfully! Now parsing...")
            info = self._parse_eeprom_text()
            logger.info(f"Parsed EEPROM info: {info}")
            return info
        except EEPROMError as e:
            logger.error(f"Failed to read EEPROM: {e}")
            return None

    def read_device_tree(self, index: int = 0) -> Union[Dict[str, Any], bool]:
        """Read EEPROM data from Linux device tree.
        
        This is different from direct EEPROM reading - it reads how the system
        currently sees the EEPROM content through the device tree interface.
        Use this to verify how Linux has loaded the EEPROM data. Please note that 
        the changes to the EEPROM are not reflected in the device tree until the
        linux is rebooted.

        Args:
            index: Custom data index in device tree (default: 0)
            
        Returns:
            Dict with device tree data or False if not found
            The data typically includes:
            - serial_number: Current serial number
            - Other custom data as configured in the device tree
        """
        try:
            with open(f"/proc/device-tree/hat/custom_{index}", "r") as read_file:
                data: Dict[str, Any] = json.load(read_file)
                return data
        except OSError as error:
            logger.error(f"Error reading device tree: {error}")
            logger.info("File not found! EEPROM is empty")
            return False

    def read_json_file(self, f_json: Optional[str] = None) -> Tuple[Dict[str, Any], str]:
        """Read a JSON file containing EEPROM settings or custom data.
        
        This reads JSON files used for EEPROM operations, not the EEPROM itself.
        These files store settings and custom data that can be written to EEPROM.
        
        Args:
            f_json: JSON filename (default: based on serial number)
            
        Returns:
            Tuple of (json_data, filename)
            - json_data: Dict containing the JSON data
            - filename: Actual filename used
        """
        serial_number = self.get_serial_number()
        if not f_json:
            f_json = f"{serial_number}.json" if serial_number else self.default_config

        try:
            with open(f"{self.config.json_path}{f_json}", "r") as read_file:
                data: Dict[str, Any] = json.load(read_file)
        except FileNotFoundError as error:
            logger.error(f"Error reading JSON file: {error}")
            logger.info("File not found! Using empty summary")
            data = {}
            
        return data, f_json

    def reset_eeprom(self) -> bool:
        """Reset EEPROM to blank state and verify the operation."""
        try:
            self.write_protect.off()
            logger.info("Write protect disabled")
            
            logger.info("Making blank binary file")
            run_command(
                ["dd", "if=/dev/zero", "ibs=1k", f"count={self.config.size_kbytes}", f"of={self.blank_binary}"]
            )
            
            logger.info("Writing blank binary file to EEPROM")
            run_command(
                ["sudo", f"{self.config.tools_path}/eepflash.sh", "-w", f"-d={self.config.i2c_bus}", f"-a={self.config.i2c_address[2:]}", f"-f={self.blank_binary}", "-y", f"-t={self.config.model}"]
            )
            
            time.sleep(0.5)
            
            logger.info("Verifying blank state")
            run_command(
                ["sudo", f"{self.config.tools_path}/eepflash.sh", "-r", f"-d={self.config.i2c_bus}", f"-a={self.config.i2c_address[2:]}", f"-f={self.blank_readback_binary}", "-y", f"-t={self.config.model}"]
            )
            
            with open(self.blank_readback_binary, "rb") as f:
                content: bytes = f.read()
                if any(byte != 0 for byte in content):
                    logger.error("EEPROM verification failed - not blank!")
                    self.test_result = False
                    return False
                    
            logger.info("EEPROM successfully blanked and verified")
            return True
            
        except sp.CalledProcessError as e:
            logger.error(f"Command failed with error: {e.stderr}")
            self.test_result = False
            return False
        finally:
            self.write_protect.on()
            logger.info("Write protect re-enabled")

    def write_eeprom(self, f_bin: Optional[str] = None) -> bool:
        """Write the binary file to the EEPROM."""
        if not f_bin:
            f_bin = self.image_binary
        
        if not self.test_result:
            logger.error("No EEPROM is detected!")
            return False

        try:
            if not self.reset_eeprom():
                self.test_result = False
                logger.error("EEPROM reset failed!")
                return False

            self.write_protect.off()

            logger.info(f"Writing binary file: {f_bin}")
            run_command(
                ["sudo", f"{self.config.tools_path}/eepflash.sh", "-w", f"-d={self.config.i2c_bus}", f"-a={self.config.i2c_address[2:]}", f"-f={f_bin}", "-y", f"-t={self.config.model}"]
            )
            
            logger.info("Reading back binary file for verification")
            run_command(
                ["sudo", f"{self.config.tools_path}/eepflash.sh", "-r", f"-d={self.config.i2c_bus}", f"-a={self.config.i2c_address[2:]}", f"-f={self.readback_binary}", "-y", f"-t={self.config.model}"]
            )

            return True
        except sp.CalledProcessError as e:
            logger.error(f"EEPROM write failed: {e.stderr}")
            return False
        finally:
            self.write_protect.on()
            logger.info("Write protect re-enabled")

    def _make_eeprom(self, f_txt: Optional[str] = None, f_json: Optional[Union[str, list[str]]] = None) -> None:
        """Internal method to create EEPROM binary file from text and JSON inputs.
        
        Args:
            f_txt: Optional path to template text file
            f_json: Optional JSON filename(s). Can be a single filename or list of filenames
                   for multiple custom data sections.
        """
        if not f_txt:
            f_txt = self.config.files_path / self.template_text
            
        # Handle single JSON file case
        if isinstance(f_json, str) or f_json is None:
            f_json = [f_json if f_json else self.default_config]
            
        logger.info("Making eeprom binary file")
        logger.info(f"Settings file: {f_txt}")
        
        # Build command with base arguments
        cmd = [f"{self.config.tools_path}/eepmake", "-v1", f_txt, self.image_binary]
        
        # Add custom data files if any
        if f_json:
            # Add -c flag once, followed by all JSON files
            cmd.append("-c")
            for json_file in f_json:
                logger.info(f"Adding custom data from: {self.config.json_path}{json_file}")
                cmd.append(f"{self.config.json_path}{json_file}")
            
        run_command(cmd)
        logger.info("Binary file generated")

    def _remove_custom_data(self, f_txt: Optional[str] = None) -> None:
        """Internal method to remove custom data section from EEPROM text file."""
        if f_txt is None:
            f_txt = self.dump_text
            
        with open(self.temp_text, "w") as write_file:
            with open(f_txt, "r") as read_file:
                for line in read_file:
                    if "Start of atom #2" in line or "Start of atom #3" in line:
                        break
                    write_file.write(line)
                    
        os.rename(self.temp_text, self.dump_text)

    def update_eeprom(self, f_json: Optional[Union[str, list[str]]] = None, f_setting: Optional[str] = None) -> bool:
        """Update EEPROM while preserving UUID and other settings.
        
        Args:
            f_json: JSON filename(s). Can be a single filename or list of filenames for multiple
                   custom data sections. If None, uses serial_number.json or default_config.
            f_setting: Optional settings template file
            
        Returns:
            bool: True if successful, False otherwise
        """
        serial_number = self.get_serial_number()
        
        # Handle default JSON file case
        if f_json is None:
            f_json = f"{serial_number}.json" if serial_number else self.default_config

        if f_setting is not None:
            logger.info(f"Making new binary file using {f_setting} and custom data from JSON file(s)")
            self._make_eeprom(f_txt=f"{self.config.files_path}{f_setting}", f_json=f_json)
        else:
            logger.info("Removing existing custom data")
            self._remove_custom_data()
            logger.info("Making EEPROM binary image with new custom data")
            self._make_eeprom(f_txt=self.dump_text, f_json=f_json)

        logger.info("Writing new binary file to EEPROM")
        if not self.write_eeprom():
            self.test_result = False
            logger.error("EEPROM write failed!")
            return False
        return True

    def update_json(self, summary: Dict[str, Any] = {}, f_json: Optional[str] = None) -> None:
        """Update the JSON file with new data."""
        data, f_json = self.read_json_file(f_json)
        logger.info(f"Updating JSON file: {f_json}")
        data.update(summary)
        
        with open(f"{self.config.json_path}{f_json}", "w") as write_file:
            json.dump(data, write_file, indent=4)

    def update_serial_number(self, serial_number: str) -> bool:
        """Update just the serial number while preserving other EEPROM content.
        
        Args:
            serial_number: New serial number to write
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Updating serial number to: {serial_number}")
        info = self.read_eeprom_content()
        if not info:
            logger.error("Failed to read current EEPROM content")
            return False
            
        if not info.get("product_uuid"):
            logger.error("EEPROM is blank, cannot update serial number")
            return False
            
        custom_data = info.get("custom_data", {})
        if not isinstance(custom_data, dict):
            logger.error("Invalid EEPROM content!")
            return False
            
        custom_data['serial_number'] = serial_number
        custom_data['eeprom'] = {
            'model': self.config.model,
            'i2c_bus': self.config.i2c_bus,
            'i2c_address': self.config.i2c_address,
            'test_result': self.test_result
        }
        
        self.update_json(summary=custom_data, f_json=f"{serial_number}.json")
        return self.update_eeprom(f_json=f"{serial_number}.json")

    def refresh(self, settings_file: str = "eeprom_template.txt") -> bool:
        """Refresh EEPROM with new content.
        
        This operation will:
        1. Back up current EEPROM content
        2. Reset the EEPROM
        3. Write new content
        4. Archive backup with timestamp if successful
        
        Args:
            settings_file: Path to settings file
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Backup current content
        logger.info("Creating backup of current EEPROM content...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.config.files_path / "eeprom_backups"
        backup_dir.mkdir(exist_ok=True)
        
        backup_binary = self.config.files_path / "eeprom_backup.eep"
        backup_text = self.config.files_path / "eeprom_backup.txt"
        
        try:
            # Read current content
            self._read_raw_eeprom()
            if self.readback_binary.exists():
                import shutil
                shutil.copy(self.readback_binary, backup_binary)
                shutil.copy(self.dump_text, backup_text)
                logger.info("Backup created successfully")
            else:
                logger.warning("No existing content to backup")
            
            # Proceed with refresh
            logger.info("Erasing EEPROM content...")
            if not self.reset_eeprom():
                raise EEPROMError("Failed to reset EEPROM")
                
            summary = self.generate_summary()    
            serial_number = summary["serial_number"]
            logger.info(f"Generated new serial number: {serial_number}")
            
            logger.info("Creating new JSON summary file")
            self.update_json(summary, f_json=f"{serial_number}.json")
            
            logger.info("Updating EEPROM with new settings")
            if not self.update_eeprom(f_json=f"{serial_number}.json", f_setting=settings_file):
                raise EEPROMError("Failed to write new content")
                
            return True
            
        except Exception as e:
            logger.error(f"Error during refresh: {e}")
            if backup_binary.exists():
                logger.info("Attempting to restore backup...")
                try:
                    # Disable write protect for restore
                    self.write_protect.off()
                    run_command(
                        ["sudo", f"{self.config.tools_path}/eepflash.sh", "-w", f"-d={self.config.i2c_bus}", f"-a={self.config.i2c_address[2:]}", f"-f={backup_binary}", "-y", f"-t={self.config.model}"]
                    )
                    logger.info("Backup restored successfully")
                except Exception as restore_error:
                    logger.error(f"Failed to restore backup: {restore_error}")
                finally:
                    self.write_protect.on()
            return False
        finally:
            # Archive backup files if they exist
            if backup_binary.exists():
                try:
                    # Create archive filenames with timestamp
                    archive_binary = backup_dir / f"eeprom_backup_{timestamp}.eep"
                    archive_text = backup_dir / f"eeprom_backup_{timestamp}.txt"
                    
                    # Move backup files to archive
                    backup_binary.rename(archive_binary)
                    if backup_text.exists():
                        backup_text.rename(archive_text)
                        
                    # Create a metadata file with information about the backup
                    metadata = {
                        "timestamp": timestamp,
                        "serial_number": self.serial_number,
                        "model": self.config.model,
                        "settings_file": str(settings_file)
                    }
                    metadata_file = backup_dir / f"eeprom_backup_{timestamp}_meta.json"
                    with open(metadata_file, "w") as f:
                        json.dump(metadata, f, indent=4)
                        
                    logger.info(f"Backup archived with timestamp {timestamp}")
                except Exception as e:
                    logger.warning(f"Failed to archive backup files: {e}")

    def handle_existing_content(self, info: Dict[str, Any], force: bool = False) -> bool:
        """Handle existing EEPROM content.
        
        Args:
            info: Parsed EEPROM info
            force: Whether to force refresh even with valid content
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not info.get("product_uuid"):
            logger.info("EEPROM is blank")
            return self.refresh()
            
        if info["product_uuid"] == '00000000-0000-0000-0000-000000000000':
            logger.info("EEPROM has zero UUID")
            return self.refresh()
            
        custom_data = info.get("custom_data", {})
        if not isinstance(custom_data, dict):
            logger.error("Corrupt EEPROM content!")
            if not force:
                logger.info("Use force flag to overwrite corrupt content")
                return False
            return self.refresh()
            
        serial_number = custom_data.get("serial_number")
        if serial_number:
            logger.info(f"Found existing serial number: {serial_number}")
            custom_data['eeprom'] = {
                'model': self.config.model,
                'i2c_bus': self.config.i2c_bus,
                'i2c_address': self.config.i2c_address,
                'test_result': self.test_result
            }
            self.update_json(summary=custom_data, f_json=f"{serial_number}.json")
            logger.info("Updated JSON summary")
            return True
        else:
            logger.info("No serial number found, generating new one")
            summary = self.generate_summary()
            serial_number = summary["serial_number"]
            logger.info(f"Generated new serial number: {serial_number}")
            self.update_json(summary, f_json=f"{serial_number}.json")
            return self.update_eeprom(f_json=f"{serial_number}.json")