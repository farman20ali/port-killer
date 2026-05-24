"""
Unit tests for kport CLI modules and configuration parameters.
Tested via pytest.
"""

import pytest
from kport.exceptions import InvalidPortError
from kport.cli import validate_port, parse_port_range

def test_validate_port_valid():
    """Verify that valid ports pass validation silently."""
    validate_port(80)
    validate_port(8080)
    validate_port(65535)


def test_validate_port_invalid():
    """Verify that invalid ports raise an InvalidPortError."""
    with pytest.raises(InvalidPortError):
        validate_port(0)
    with pytest.raises(InvalidPortError):
        validate_port(65536)
    with pytest.raises(InvalidPortError):
        validate_port(-80)


def test_parse_port_range_single():
    """Test parsing a single port string."""
    assert parse_port_range("80") == [80]
    assert parse_port_range(" 8080  ") == [8080]


def test_parse_port_range_sequence():
    """Test parsing a port range sequence."""
    assert parse_port_range("3000-3005") == [3000, 3001, 3002, 3003, 3004, 3005]
    assert parse_port_range("8080-8080") == [8080]


def test_parse_port_range_invalid():
    """Test parsing invalid range formats."""
    with pytest.raises(InvalidPortError):
        parse_port_range("3000-2999")  # start > end
    with pytest.raises(InvalidPortError):
        parse_port_range("3000-4001")  # too large (> 1000 ports)
    with pytest.raises(InvalidPortError):
        parse_port_range("invalid-format")
    with pytest.raises(InvalidPortError):
        parse_port_range("80-99999")  # out of bounds port
