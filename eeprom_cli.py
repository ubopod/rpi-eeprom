#!/usr/bin/env python3
"""Command-line interface for EEPROM operations."""

import sys
import json
import argparse
import logging
from pathlib import Path
from eeprom import EEPROM, EEPROMConfig, EEPROMError

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
    
    # Write command
    write_parser = subparsers.add_parser("write", help="Write to EEPROM")
    write_parser.add_argument("--serial", "-s", type=str, help="Serial number to write")
    write_parser.add_argument("--json-file", "-j", type=Path, help="JSON file containing custom data to write")
    
    # Reset command
    subparsers.add_parser("reset", help="Reset EEPROM to blank state")
    
    args = parser.parse_args()
    
    setup_logging(args.verbose)
    
    try:
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
        
        if not eeprom.bus_address:
            logger.error("No EEPROM device detected!")
            return 1
            
        # Handle commands
        if args.command == "read":
            if args.device_tree:
                data = eeprom.read_device_tree()
                if data:
                    if args.json:
                        print(json.dumps(data, indent=2))
                    else:
                        for key, value in data.items():
                            print(f"{key}: {value}")
                    return 0
                logger.error("Failed to read from device tree")
                return 1
                
            info = eeprom.read_eeprom_content()
            if info:
                if args.json:
                    print(json.dumps(info, indent=2))
                else:
                    for key, value in info.items():
                        print(f"{key}: {value}")
                return 0
            logger.error("Failed to read EEPROM content")
            return 1
            
        elif args.command == "write":
            if args.json_file:
                try:
                    with open(args.json_file) as f:
                        custom_data = json.load(f)
                    logger.info(f"Loaded custom data from {args.json_file}")
                    
                    # Update EEPROM with custom data
                    eeprom.update_json(custom_data)
                    if eeprom.update_eeprom():
                        logger.info("Successfully updated EEPROM with custom data")
                        return 0
                    logger.error("Failed to update EEPROM")
                    return 1
                except (json.JSONDecodeError, OSError) as e:
                    logger.error(f"Failed to load JSON file: {e}")
                    return 1
                    
            if args.serial:
                if eeprom.update_serial_number(args.serial):
                    logger.info(f"Successfully updated serial number to: {args.serial}")
                    return 0
                return 1
            
            info = eeprom.read_eeprom_content()
            if not info:
                logger.error("Failed to read current EEPROM content")
                return 1
                
            if eeprom.handle_existing_content(info, args.force):
                logger.info("Successfully handled EEPROM content")
                return 0
            return 1
            
        elif args.command == "reset":
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