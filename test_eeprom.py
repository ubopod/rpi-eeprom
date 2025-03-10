"""EEPROM test module.

This module provides both unit tests for the EEPROM class and a main script
for testing EEPROM hardware. The test script performs the following:

1. Detects EEPROM presence on I2C bus
2. Reads and validates existing content
3. Handles various EEPROM states:
   - Blank EEPROM: Performs full refresh with new serial
   - Valid UUID: Updates or preserves existing content
   - Invalid/corrupt content: Offers refresh option
4. Provides detailed logging of operations

Usage:
    1. Run unit tests (no hardware required):
       ```
       # Run all tests
       pytest test_eeprom.py -v
       
       # Run specific test
       pytest test_eeprom.py -v -k "test_generate_serial_number"
       
       # Run with coverage report
       pytest test_eeprom.py -v --cov=eeprom
       ```
       
    2. Run hardware test (requires physical EEPROM):
       ```
       # Direct execution
       python3 test_eeprom.py
       
       # With verbose output
       python3 test_eeprom.py --verbose
       ```
       
    Requirements:
    - pytest
    - pytest-cov (optional, for coverage reports)
    - Physical EEPROM device (for hardware tests only)
    - Proper I2C configuration
    - Root access for EEPROM operations
"""

import os
import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from eeprom import EEPROM, EEPROMConfig, EEPROMError

# Add parent directory to path for imports
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PARENT_DIR)

# Test Fixtures
@pytest.fixture
def temp_dir(tmp_path):
    """Create temporary directory structure for tests."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "files").mkdir()
    (tmp_path / "json").mkdir()
    return tmp_path

@pytest.fixture
def config(temp_dir):
    """Create test configuration."""
    return EEPROMConfig(
        tools_path=temp_dir / "tools",
        files_path=temp_dir / "files",
        json_path=temp_dir / "json"
    )

@pytest.fixture
def mock_gpio():
    """Mock GPIO device."""
    with patch('gpiozero.DigitalOutputDevice') as mock:
        yield mock

@pytest.fixture
def eeprom(config, mock_gpio):
    """Create EEPROM instance with mocked GPIO."""
    with patch('eeprom.EEPROM._check_i2c'):
        return EEPROM(config)

# Unit Tests
def test_init(eeprom):
    """Test EEPROM initialization."""
    assert eeprom.model == "24c32"
    assert eeprom.size_kbytes == 4
    assert eeprom.serial_number is None
    assert isinstance(eeprom.binary_file, Path)

def test_generate_serial_number(eeprom):
    """Test serial number generation."""
    serial = eeprom.generate_serial_number()
    assert len(serial) == 12
    assert all(c in "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789" for c in serial)

@patch('subprocess.run')
def test_read_raw_eeprom_no_device(mock_run, eeprom):
    """Test reading EEPROM when no device is present."""
    eeprom.bus_address = None
    eeprom._read_raw_eeprom()
    mock_run.assert_not_called()

@patch('subprocess.run')
def test_read_raw_eeprom_with_device(mock_run, eeprom):
    """Test reading EEPROM when device is present."""
    eeprom.bus_address = "0x50"
    mock_run.return_value.returncode = 0
    eeprom._read_raw_eeprom()
    assert mock_run.call_count == 2

def test_generate_summary(eeprom):
    """Test summary generation."""
    summary = eeprom.generate_summary()
    assert "eeprom" in summary
    assert "serial_number" in summary
    assert summary["eeprom"]["model"] == "24c32"

@patch('builtins.open', create=True)
def test_parse_eeprom_text_empty(mock_open, eeprom):
    """Test parsing empty EEPROM."""
    mock_open.side_effect = OSError
    info = eeprom._parse_eeprom_text()
    assert info == {}

@patch('builtins.open')
def test_parse_eeprom_text_valid(mock_file_handler, eeprom):
    """Test parsing valid EEPROM content."""
    mock_file = mock_file_handler.return_value.__enter__.return_value
    mock_file.readline.side_effect = [
        "product_uuid 12345678-1234-5678-1234-567812345678\n",
        "product_id 0x1234\n",
        "product_ver 0x1\n",
        'vendor "Test Vendor"\n',
        'product "Test Product"\n',
        "custom_data\n",
        '{"serial_number": "ABC123"}\n',
        "End of atom\n"
    ]
    info = eeprom._parse_eeprom_text()
    assert info["product_uuid"] == "12345678-1234-5678-1234-567812345678"
    assert info["custom_data"]["serial_number"] == "ABC123"

def test_handle_existing_content_blank(eeprom):
    """Test handling blank EEPROM."""
    with patch.object(eeprom, 'refresh') as mock_refresh:
        mock_refresh.return_value = True
        result = eeprom.handle_existing_content({})
        assert result is True
        mock_refresh.assert_called_once()

def test_handle_existing_content_zero_uuid(eeprom):
    """Test handling EEPROM with zero UUID."""
    with patch.object(eeprom, 'refresh') as mock_refresh:
        mock_refresh.return_value = True
        result = eeprom.handle_existing_content({
            "product_uuid": "00000000-0000-0000-0000-000000000000"
        })
        assert result is True
        mock_refresh.assert_called_once()

# Main Test Script
def run_eeprom_test() -> int:
    """Run EEPROM hardware test.
    
    Returns:
        int: 0 for success, 1 for failure
    """
    print("Starting EEPROM test...")
    
    try:
        eeprom = EEPROM()
        
        if not eeprom.bus_address:
            print("No EEPROM device detected!")
            return 1
            
        print("Reading EEPROM content...")
        info = eeprom.read_eeprom_content()
        if not info:
            print("Failed to read EEPROM content!")
            return 1
            
        print(f"EEPROM info: {json.dumps(info, indent=2)}")
        
        if eeprom.handle_existing_content(info):
            print("EEPROM test passed!")
            return 0
        else:
            print("EEPROM test failed - could not handle content!")
            return 1
            
    except EEPROMError as e:
        print(f"EEPROM Error: {e}")
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        return 130

if __name__ == '__main__':
    sys.exit(run_eeprom_test())
