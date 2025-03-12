#!/usr/bin/env python3
"""Command-line interface for EEPROM operations.

This tool provides a command-line interface for managing EEPROM content, including:
- Reading EEPROM content (both raw directly from EEPROM and from device tree)
- Writing custom data to EEPROM
- Updating serial numbers
- Managing multiple custom data sections
- Resetting EEPROM to blank state

Configuration:
    The tool can be configured using a JSON configuration file that specifies:
    - EEPROM model and size
    - I2C bus and address
    - File paths for tools and data
    - GPIO pin for write protection
    
    Example config.json:
        {
            "model": "24c32",
            "size_kbytes": 4,
            "i2c_bus": 9,
            "i2c_address": "0x50",
            "write_protect_pin": 16,
            "tools_path": "/usr/local/bin",
            "files_path": "./files",
            "json_path": "./json"
        }
    
    All fields are optional and will use defaults if not specified.

Examples:
    1. Replace all custom data sections with a new one:
        $ eeprom_cli.py write -j new_data.json
        
    2. Replace with multiple custom data sections:
        $ eeprom_cli.py write -j section1.json -j section2.json
        
    3. Preserve existing first section and add a new one:
        $ eeprom_cli.py write -j new_section.json --append
        
    4. Preserve first section and add multiple new ones:
        $ eeprom_cli.py write -j second.json -j third.json --append
        
    5. Read EEPROM content in JSON format:
        $ eeprom_cli.py read --json
        
    6. Save EEPROM content to a file:
        $ eeprom_cli.py read --output eeprom_data.json
        
    7. Read and save device tree content:
        $ eeprom_cli.py read --device-tree --output dt_data.json
        
    8. Display and save EEPROM content in JSON format:
        $ eeprom_cli.py read --json --output eeprom_data.json
        
    9. Update serial number:
        $ eeprom_cli.py write --serial ABC123XYZ
        
    10. Reset EEPROM with custom settings:
        $ eeprom_cli.py reset --settings my_settings.txt
        
    11. Use custom configuration:
        $ eeprom_cli.py -c config.json write -j data.json

Options:
    --verbose, -v    Enable verbose logging
    --force, -f      Force operations even with existing content
    --config, -c     Path to configuration file
    --settings, -s   Path to EEPROM settings file (default: eeprom_settings.txt)

Commands:
    read    Read EEPROM content
    write   Write to EEPROM
    reset   Reset EEPROM to blank state

For more detailed help on each command:
    $ eeprom_cli.py <command> --help
"""

import sys
import json
import argparse
import logging
from pathlib import Path
from eeprom import EEPROM, EEPROMConfig, EEPROMError
import os

logger = logging.getLogger(__name__)

def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('eeprom_cli.log')
        ]
    )

def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="EEPROM Management Tool")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--force", "-f", action="store_true", help="Force operations even with existing content")
    parser.add_argument("--config", "-c", type=Path, help="Path to configuration file")
    parser.add_argument("--settings", "-s", type=str, default="eeprom_settings.txt", help="Path to EEPROM settings file")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Read command
    read_parser = subparsers.add_parser("read", help="Read EEPROM content")
    read_parser.add_argument("--json", "-j", action="store_true", help="Output in JSON format")
    read_parser.add_argument("--device-tree", "-d", action="store_true", help="Read from device tree instead of EEPROM")
    read_parser.add_argument("--output", "-o", type=Path, help="Save output to JSON file")
    
    # Write command
    write_parser = subparsers.add_parser("write", help="Write to EEPROM")
    write_parser.add_argument("--serial", "-s", type=str, help="Serial number to write")
    write_parser.add_argument("--json-file", "-j", type=Path, action="append", help="JSON file(s) containing custom data to write. Can be specified multiple times for multiple sections.")
    write_parser.add_argument("--append", "-a", action="store_true", help="Append new JSON data while preserving existing custom data")
    
    # Reset command
    subparsers.add_parser("reset", help="Reset EEPROM to blank state")
    
    args = parser.parse_args()
    
    setup_logging(args.verbose)
    
    try:
        # Validate command
        if not args.command:
            logger.error("No command specified")
            parser.print_help()
            return 1
            
        # Initialize EEPROM with optional config
        config = None
        if args.config:
            try:
                with open(args.config) as f:
                    config_data = json.load(f)
                    config = EEPROMConfig(**config_data)
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"Failed to load config file: {e}")
                return 1
        
        eeprom = EEPROM(config)
        
        if not eeprom.test_result:
            logger.error("No EEPROM device detected!")
            return 1
            
        # Handle commands
        if args.command == "read":
            if args.device_tree:
                data = eeprom.read_device_tree()
                if not data:
                    logger.error("Failed to read from device tree")
                    return 1
            else:
                data = eeprom.read_eeprom_content()
                if not data:
                    logger.error("Failed to read EEPROM content")
                    return 1
            
            # Handle output
            if args.output:
                try:
                    # Create parent directories if they don't exist
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    
                    with open(args.output, 'w') as f:
                        json.dump(data, f, indent=2)
                    logger.info(f"Successfully saved EEPROM content to {args.output}")
                except OSError as e:
                    logger.error(f"Failed to write to output file: {e}")
                    return 1
            
            # Display output
            if args.json:
                logger.info("\n" + json.dumps(data, indent=2))
            else:
                for key, value in data.items():
                    logger.info(f"{key}: {value}")
            return 0
            
        elif args.command == "write":
            if args.json_file:
                try:
                    json_files = []
                    if args.append:
                        # Read current content to preserve first custom data section
                        info = eeprom.read_eeprom_content()
                        if not info:
                            logger.error("Failed to read current EEPROM content for append operation")
                            return 1
                            
                        if "custom_data" not in info:
                            logger.warning("No existing custom data found to append to")
                        else:
                            # Save current custom data to a temporary file
                            temp_json = eeprom.config.json_path / "temp_current.json"
                            try:
                                with open(temp_json, "w") as f:
                                    if isinstance(info["custom_data"], dict):
                                        json.dump(info["custom_data"], f)
                                    else:
                                        json.dump({"data": info["custom_data"]}, f)
                                json_files.append(str(temp_json))
                            except Exception as e:
                                logger.error(f"Failed to save current custom data: {e}")
                                return 1
                    
                    # Validate and add new JSON files
                    for json_file in args.json_file:
                        try:
                            with open(json_file) as f:
                                logger.info(f"Loaded custom data from {json_file}")
                            json_files.append(str(json_file))
                        except json.JSONDecodeError as e:
                            logger.error(f"Invalid JSON in {json_file}: {e}")
                            return 1
                        except OSError as e:
                            logger.error(f"Failed to read {json_file}: {e}")
                            return 1
                    
                    # Update EEPROM with all custom data sections
                    if eeprom.update_eeprom(f_json=json_files):
                        logger.info("Successfully updated EEPROM with custom data")
                        # Clean up temporary file if it was created
                        if args.append and "temp_json" in locals():
                            try:
                                os.remove(temp_json)
                            except OSError as e:
                                logger.warning(f"Failed to remove temporary file: {e}")
                        return 0
                    logger.error("Failed to update EEPROM")
                    return 1
                except Exception as e:
                    logger.error(f"Unexpected error while handling JSON files: {e}")
                    if args.verbose:
                        logger.exception("Detailed error information:")
                    return 1
                    
            if args.serial:
                if not args.serial.strip():
                    logger.error("Serial number cannot be empty")
                    return 1
                if eeprom.update_serial_number(args.serial):
                    logger.info(f"Successfully updated serial number to: {args.serial}")
                    return 0
                return 1
            
            # If no specific write operation was requested
            if not (args.json_file or args.serial):
                info = eeprom.read_eeprom_content()
                if not info:
                    logger.error("Failed to read current EEPROM content")
                    return 1
                    
                if eeprom.handle_existing_content(info, args.force):
                    logger.info("Successfully handled EEPROM content")
                    return 0
                return 1
            
        elif args.command == "reset":
            if not args.settings:
                logger.warning("No settings file specified, using default")
            elif not os.path.exists(args.settings):
                logger.error(f"Settings file not found: {args.settings}")
                return 1
                
            if eeprom.refresh(args.settings):
                logger.info("Successfully refreshed EEPROM")
                return 0
            logger.error("Failed to refresh EEPROM")
            return 1
            
        else:
            parser.print_help()
            return 1
            
    except KeyboardInterrupt:
        logger.info("Operation interrupted by user")
        return 130
    except EEPROMError as e:
        logger.error(f"EEPROM operation failed: {e}")
        if args.verbose:
            logger.exception("Detailed error information:")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if args.verbose:
            logger.exception("Detailed error information:")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 