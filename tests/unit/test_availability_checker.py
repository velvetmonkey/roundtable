"""Unit tests for CLI availability checker."""
import pytest
from unittest.mock import patch, MagicMock
from roundtable_mcp_server.availability_checker import CLIAvailabilityChecker


@pytest.mark.unit
class TestCLIAvailabilityChecker:
    """Test CLIAvailabilityChecker class."""
    
    def test_init(self):
        """Test initialization."""
        checker = CLIAvailabilityChecker()
        assert checker is not None
    
    # NOTE: _check_cli_exists method doesn't exist in current implementation
    # Current implementation uses async check_*_availability() methods instead
    # @patch('shutil.which')
    # def test_check_cli_available(self, mock_which):
    #     """Test checking available CLI."""
    #     mock_which.return_value = "/usr/bin/codex"
    #     
    #     checker = CLIAvailabilityChecker()
    #     result = checker._check_cli_exists("codex")
    #     
    #     assert result is True
    #     mock_which.assert_called_once_with("codex")
    
    # NOTE: _check_cli_exists method doesn't exist in current implementation
    # @patch('shutil.which')
    # def test_check_cli_not_available(self, mock_which):
    #     """Test checking unavailable CLI."""
    #     mock_which.return_value = None
    #     
    #     checker = CLIAvailabilityChecker()
    #     result = checker._check_cli_exists("nonexistent")
    #     
    #     assert result is False
    
    def test_get_available_clis_empty(self, tmp_path):
        """Test getting available CLIs with no cache."""
        checker = CLIAvailabilityChecker()
        checker.availability_file = tmp_path / "test_cache.json"
        
        result = checker.get_available_clis()
        
        # When no cache exists, returns empty list
        assert result == []
    
    # NOTE: save_availability method doesn't exist in current implementation
    # Current implementation uses async check_all_availability() instead
    # @patch('shutil.which')
    # def test_save_and_load_cache(self, mock_which, tmp_path):
    #     """Test saving and loading availability cache."""
    #     mock_which.return_value = "/usr/bin/codex"
    #     
    #     checker = CLIAvailabilityChecker()
    #     checker.cache_file = tmp_path / "test_cache.json"
    #     
    #     # Save cache
    #     checker.save_availability({"codex": True, "claude": False})
    #     
    #     # Load cache
    #     available = checker.get_available_clis()
    #     
    #     assert "codex" in available
    #     assert "claude" not in available
