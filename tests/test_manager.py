"""
Tests for the PowerManager core logic.
"""
import pytest
import json
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, time
import pytz

# Add the parent directory to the path for imports
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from powermgr.core.manager import PowerManager
from powermgr.services.tesla_api import TeslaAPI
from powermgr.services.honeywell_api import HoneywellAPI
from powermgr.utils.metrics import MetricsRecorder
from powermgr.utils.notifications import NotificationManager


@pytest.fixture
def mock_config():
    """Sample configuration for testing."""
    return {
        'settings': {
            'holidays': ['2025-01-01', '2025-07-04'],
            'thermostat_increment_f': 2,
            'precool_adjustment_f': 2,
            'precool_threshold_f': 95,
            'eod_battery_warning_threshold': 20,
            'thermostat_ids': ['THERMO_1', 'THERMO_2'],
            'location': 'America/Phoenix',
            'battery_thresholds': [
                {'time_remaining_minutes': 120, 'level_percent': 75},
                {'time_remaining_minutes': 60, 'level_percent': 50},
                {'time_remaining_minutes': 30, 'level_percent': 25}
            ],
            'seasons': {
                'summer': {
                    'months': [5, 6, 7, 8, 9, 10],
                    'peak_periods': [
                        {'start': '16:00', 'end': '19:00'}
                    ]
                },
                'winter': {
                    'months': [11, 12, 1, 2, 3, 4],
                    'peak_periods': [
                        {'start': '06:00', 'end': '09:00'},
                        {'start': '17:00', 'end': '20:00'}
                    ]
                }
            }
        }
    }


@pytest.fixture
def mock_clients():
    """Create mock clients for testing."""
    tesla_mock = Mock(spec=TeslaAPI)
    honeywell_mock = Mock(spec=HoneywellAPI)
    metrics_mock = Mock(spec=MetricsRecorder)
    notifications_mock = Mock(spec=NotificationManager)
    
    # Set up default return values
    tesla_mock.health_check.return_value = True
    honeywell_mock.health_check.return_value = True
    tesla_mock.get_battery_charge.return_value = 80.0
    tesla_mock.get_battery_reserve_setting.return_value = 100
    tesla_mock.set_reserve_percentage.return_value = True
    honeywell_mock.get_cool_setpoint.return_value = 75
    honeywell_mock.set_thermostat_cool_setpoint.return_value = True
    
    metrics_mock.load_state.return_value = {
        'actions': [],
        'battery_remaining': [],
        'precooling': False,
        'last_updated': datetime.now().isoformat()
    }
    
    return tesla_mock, honeywell_mock, metrics_mock, notifications_mock


@pytest.fixture
def power_manager(mock_config, mock_clients):
    """Create PowerManager instance for testing."""
    tesla_mock, honeywell_mock, metrics_mock, notifications_mock = mock_clients
    
    return PowerManager(
        config=mock_config,
        tesla_client=tesla_mock,
        honeywell_client=honeywell_mock,
        metrics_recorder=metrics_mock,
        notification_manager=notifications_mock
    )


class TestPowerManager:
    """Test cases for PowerManager class."""
    
    def test_initialization(self, power_manager):
        """Test PowerManager initializes correctly."""
        assert power_manager is not None
        assert power_manager.thermostat_increment == 2
        assert power_manager.precool_adjustment == 2
        assert len(power_manager.thermostat_ids) == 2
    
    @patch('powermgr.core.manager.datetime')
    def test_get_current_phase_weekend(self, mock_datetime, power_manager):
        """Test phase detection returns NON_PEAK for weekends."""
        # Mock Saturday
        mock_datetime.now.return_value = datetime(2025, 8, 30, 17, 0)  # Saturday 5 PM
        mock_datetime.now.return_value.date.return_value.weekday.return_value = 5
        
        phase = power_manager._get_current_phase()
        assert phase == "NON_PEAK"
    
    @patch('powermgr.core.manager.datetime')
    def test_get_current_phase_holiday(self, mock_datetime, power_manager):
        """Test phase detection returns NON_PEAK for holidays."""
        # Mock New Year's Day (in config holidays)
        mock_datetime.now.return_value = datetime(2025, 1, 1, 17, 0)  # Wednesday 5 PM
        mock_datetime.now.return_value.date.return_value.weekday.return_value = 2
        mock_datetime.now.return_value.date.return_value.isoformat.return_value = "2025-01-01"
        
        phase = power_manager._get_current_phase()
        assert phase == "NON_PEAK"
    
    @patch('powermgr.core.manager.datetime')
    def test_get_current_phase_summer_peak(self, mock_datetime, power_manager):
        """Test phase detection for summer peak period."""
        # Mock summer weekday during peak (5 PM in August)
        mock_now = Mock()
        mock_now.month = 8
        mock_now.time.return_value = time(17, 0)  # 5:00 PM
        mock_now.date.return_value.weekday.return_value = 2  # Wednesday
        mock_now.date.return_value.isoformat.return_value = "2025-08-27"
        
        mock_datetime.now.return_value = mock_now
        
        # Mock timezone
        with patch.object(power_manager, 'timezone') as mock_tz:
            mock_tz.localize = Mock(return_value=mock_now)
            phase = power_manager._get_current_phase()
        
        assert phase == "PEAK_MONITOR"
    
    def test_health_check_success(self, power_manager, mock_clients):
        """Test successful health check."""
        tesla_mock, honeywell_mock, metrics_mock, notifications_mock = mock_clients
        
        result = power_manager._run_health_check()
        
        assert result is True
        tesla_mock.health_check.assert_called_once()
        honeywell_mock.health_check.assert_called_once()
    
    def test_health_check_failure(self, power_manager, mock_clients):
        """Test health check failure handling."""
        tesla_mock, honeywell_mock, metrics_mock, notifications_mock = mock_clients
        
        # Make Tesla API fail
        tesla_mock.health_check.return_value = False
        
        result = power_manager._run_health_check()
        
        assert result is False
        notifications_mock.notify.assert_called_once()
    
    def test_handle_non_peak_period(self, power_manager, mock_clients):
        """Test non-peak period handling."""
        tesla_mock, honeywell_mock, metrics_mock, notifications_mock = mock_clients
        
        # Set current reserve to something other than 100%
        tesla_mock.get_battery_reserve_setting.return_value = 0
        
        power_manager._handle_non_peak_period()
        
        # Should set reserve to 100%
        tesla_mock.set_reserve_percentage.assert_called_once_with(100)
        metrics_mock.record_action.assert_called_once()
    
    def test_handle_peak_period(self, power_manager, mock_clients):
        """Test peak period handling."""
        tesla_mock, honeywell_mock, metrics_mock, notifications_mock = mock_clients
        
        # Set current reserve to 100% (non-peak setting)
        tesla_mock.get_battery_reserve_setting.return_value = 100
        tesla_mock.get_battery_charge.return_value = 85.0
        
        power_manager._handle_peak_period()
        
        # Should set reserve to 0%
        tesla_mock.set_reserve_percentage.assert_called_once_with(0)
        metrics_mock.record_battery_level.assert_called_once_with(85.0)
        metrics_mock.record_action.assert_called_once()
    
    def test_battery_low_detection(self, power_manager, mock_clients):
        """Test battery low detection logic."""
        tesla_mock, honeywell_mock, metrics_mock, notifications_mock = mock_clients
        
        # Mock battery at 70% with 120 minutes remaining (should trigger threshold)
        tesla_mock.get_battery_charge.return_value = 70.0
        
        with patch.object(power_manager, '_get_peak_time_remaining', return_value=120):
            result = power_manager._is_battery_low()
        
        assert result is True
    
    def test_thermostat_adjustment(self, power_manager, mock_clients):
        """Test thermostat adjustment for battery conservation."""
        tesla_mock, honeywell_mock, metrics_mock, notifications_mock = mock_clients
        
        # Mock current setpoint
        honeywell_mock.get_cool_setpoint.return_value = 75
        honeywell_mock.set_thermostat_cool_setpoint.return_value = True
        
        power_manager._adjust_thermostats_for_battery_conservation()
        
        # Should adjust both thermostats by increment (2 degrees)
        expected_calls = [
            ((power_manager.thermostat_ids[0], 77), {}),
            ((power_manager.thermostat_ids[1], 77), {})
        ]
        assert honeywell_mock.set_thermostat_cool_setpoint.call_count == 2
        
        # Should record actions and send notification
        assert metrics_mock.record_action.call_count == 2
        notifications_mock.notify.assert_called_once_with('info', 'battery_adjusted', {
            'Thermostats Adjusted': 2,
            'Adjustment': '+2°F',
            'Reason': 'Battery conservation during peak period'
        })
    
    def test_precooling_activation(self, power_manager, mock_clients):
        """Test precooling activation."""
        tesla_mock, honeywell_mock, metrics_mock, notifications_mock = mock_clients
        
        # Mock current setpoint
        honeywell_mock.get_cool_setpoint.return_value = 75
        honeywell_mock.set_thermostat_cool_setpoint.return_value = True
        
        power_manager._activate_precooling()
        
        # Should lower both thermostats by precool adjustment (2 degrees)
        expected_calls = [
            ((power_manager.thermostat_ids[0], 73), {}),
            ((power_manager.thermostat_ids[1], 73), {})
        ]
        assert honeywell_mock.set_thermostat_cool_setpoint.call_count == 2
        
        # Should set precooling status and send notification
        metrics_mock.set_precooling_status.assert_called_once_with(True)
        notifications_mock.notify.assert_called_once()
    
    @patch('powermgr.core.manager.datetime')
    def test_peak_time_remaining_calculation(self, mock_datetime, power_manager):
        """Test calculation of time remaining in peak period."""
        # Mock current time as 5:30 PM (30 minutes into summer peak)
        mock_now = Mock()
        mock_now.month = 8  # August (summer)
        mock_now.time.return_value = time(17, 30)  # 5:30 PM
        mock_now.date.return_value = datetime(2025, 8, 27).date()
        
        mock_datetime.now.return_value = mock_now
        
        # Mock datetime.combine and calculations
        mock_end = Mock()
        mock_end.total_seconds.return_value = 5400  # 90 minutes in seconds
        
        with patch('powermgr.core.manager.datetime') as mock_dt:
            mock_dt.combine.return_value = Mock()
            mock_dt.strptime.return_value.time.return_value = time(19, 0)  # 7:00 PM end
            mock_dt.now.return_value = mock_now
            
            # Mock the subtraction to return our mock timedelta
            mock_dt.combine.return_value.__sub__.return_value = mock_end
            
            result = power_manager._get_peak_time_remaining()
        
        assert result == 90  # 90 minutes remaining


if __name__ == "__main__":
    pytest.main([__file__])
