"""
Core power management logic and state machine.
"""
import logging
from datetime import datetime, time, timedelta
from typing import Dict, Any, List, Optional, Tuple
from ..services.tesla_api import TeslaAPI
from ..services.honeywell_api import HoneywellAPI
from ..utils.metrics import MetricsRecorder
from ..utils.notifications import NotificationManager


class PowerManager:
    """Core power management system with state machine logic."""
    
    def __init__(self, config: Dict[str, Any], tesla_client: TeslaAPI, 
                 honeywell_client: HoneywellAPI, metrics_recorder: MetricsRecorder,
                 notification_manager: NotificationManager):
        """
        Initialize PowerManager with dependency injection.
        
        Args:
            config: Configuration dictionary
            tesla_client: Tesla API client
            honeywell_client: Honeywell API client
            metrics_recorder: Metrics recording system
            notification_manager: Notification system
        """
        self.config = config
        self.tesla = tesla_client
        self.honeywell = honeywell_client
        self.metrics = metrics_recorder
        self.notifications = notification_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Extract configuration values
        self.settings = config['settings']
        self.holidays = set(self.settings['holidays'])
        self.thermostat_increment = self.settings['thermostat_increment_f']
        self.precool_adjustment = self.settings['precool_adjustment_f']
        self.precool_threshold = self.settings['precool_threshold_f']
        self.eod_battery_threshold = self.settings['eod_battery_warning_threshold']
        self.thermostat_ids = self.settings['thermostat_ids']
        self.battery_thresholds = self.settings['battery_thresholds']
        
        # Note: All datetime operations use system local timezone
        
        self.logger.info("PowerManager initialized successfully")
    
    def run_check(self) -> None:
        """Main method called in the service loop - executes the state machine."""
        try:
            self.logger.debug("Starting power management check cycle")
            
            # Perform health check first
            if not self._run_health_check():
                self.logger.error("Health check failed, skipping this cycle")
                return
            
            # Determine current operational phase
            current_phase = self._get_current_phase()
            self.logger.info(f"Current phase: {current_phase}")
            
            # Execute phase-specific logic
            if current_phase == "NON_PEAK":
                self._handle_non_peak_period()
            elif current_phase == "PRE_PEAK":
                self._handle_pre_peak_period()
            elif current_phase in ["PEAK_START", "PEAK_MONITOR"]:
                self._handle_peak_period()
            elif current_phase == "PEAK_END":
                self._handle_peak_end()
            
            self.logger.debug("Power management check cycle completed")
            
        except Exception as e:
            self.logger.error(f"Error in run_check: {str(e)}")
            self.notifications.notify('critical', 'api_error', {
                'Error': str(e),
                'Phase': 'run_check',
                'Action': 'Check logs and system status'
            })
            raise
    
    def _run_health_check(self) -> bool:
        """
        Verify API connectivity and system health.
        
        Returns:
            bool: True if all systems are healthy
        """
        try:
            tesla_healthy = self.tesla.health_check()
            honeywell_healthy = self.honeywell.health_check()
            
            if not tesla_healthy:
                self.logger.warning("Tesla API health check failed")
                
            if not honeywell_healthy:
                self.logger.warning("Honeywell API health check failed")
            
            overall_health = tesla_healthy and honeywell_healthy
            
            if not overall_health:
                self.notifications.notify('warning', 'api_error', {
                    'Tesla API': 'OK' if tesla_healthy else 'FAILED',
                    'Honeywell API': 'OK' if honeywell_healthy else 'FAILED'
                })
            
            return overall_health
            
        except Exception as e:
            self.logger.error(f"Health check error: {str(e)}")
            return False
    
    def _get_current_phase(self) -> str:
        """
        Determine current operational phase based on time and season.
        
        Returns:
            str: Current phase (NON_PEAK, PRE_PEAK, PEAK_START, PEAK_MONITOR, PEAK_END)
        """
        now = datetime.now()
        current_date = now.date()
        current_time = now.time()
        
        # Check if today is a weekend or holiday
        if current_date.weekday() >= 5 or current_date.isoformat() in self.holidays:
            return "NON_PEAK"
        
        # Determine current season
        current_month = now.month
        season = None
        
        for season_name, season_config in self.settings['seasons'].items():
            if current_month in season_config['months']:
                season = season_config
                break
        
        if not season:
            self.logger.error(f"No season configuration found for month {current_month}")
            return "NON_PEAK"
        
        # Check if we're in any peak period
        for peak_period in season['peak_periods']:
            peak_start = datetime.strptime(peak_period['start'], '%H:%M').time()
            peak_end = datetime.strptime(peak_period['end'], '%H:%M').time()
            
            # Calculate pre-peak time (30 minutes before peak)
            pre_peak_start = (datetime.combine(current_date, peak_start) - timedelta(minutes=30)).time()
            
            # Determine phase within this peak period
            if pre_peak_start <= current_time < peak_start:
                return "PRE_PEAK"
            elif peak_start <= current_time <= peak_end:
                # Check if we're at the very start of peak (first 5 minutes)
                peak_start_window = (datetime.combine(current_date, peak_start) + timedelta(minutes=5)).time()
                if current_time <= peak_start_window:
                    return "PEAK_START"
                else:
                    return "PEAK_MONITOR"
            elif peak_end < current_time <= (datetime.combine(current_date, peak_end) + timedelta(minutes=30)).time():
                return "PEAK_END"
        
        return "NON_PEAK"
    
    def _handle_non_peak_period(self) -> None:
        """Handle non-peak period operations."""
        try:
            # Set battery reserve to 100% during non-peak hours
            current_reserve = self.tesla.get_battery_reserve_setting()
            
            if current_reserve != 100:
                self.tesla.set_reserve_percentage(100)
                self.metrics.record_action('set_battery_reserve', {
                    'previous_reserve': current_reserve,
                    'new_reserve': 100,
                    'reason': 'non_peak_period'
                })
                self.logger.info("Set battery reserve to 100% for non-peak period")
            
        except Exception as e:
            self.logger.error(f"Error in non-peak handling: {str(e)}")
            raise
    
    def _handle_pre_peak_period(self) -> None:
        """Handle pre-peak period operations (precooling logic)."""
        try:
            # Load current state to check precooling status
            state = self.metrics.load_state()
            
            # Check if precooling is needed and not already active
            if not state.get('precooling', False):
                # For now, we'll skip weather API integration and use a simple time-based approach
                # In a full implementation, you'd check weather forecast here
                high_temp_forecast = 100  # Placeholder - would come from weather API
                
                if high_temp_forecast >= self.precool_threshold:
                    self._activate_precooling()
            
        except Exception as e:
            self.logger.error(f"Error in pre-peak handling: {str(e)}")
            raise
    
    def _handle_peak_period(self) -> None:
        """Handle peak period operations (main battery management logic)."""
        try:
            # Get current battery status
            battery_percent = self.tesla.get_battery_charge()
            current_reserve = self.tesla.get_battery_reserve_setting()
            
            # Record battery level
            self.metrics.record_battery_level(battery_percent)
            
            # Set reserve to 0% during peak if not already set
            if current_reserve != 0:
                self.tesla.set_reserve_percentage(0)
                self.metrics.record_action('set_battery_reserve', {
                    'previous_reserve': current_reserve,
                    'new_reserve': 0,
                    'reason': 'peak_period',
                    'battery_level': battery_percent
                })
                self.logger.info("Set battery reserve to 0% for peak period")
            
            # Check if battery adjustment is needed
            if self._is_battery_low():
                self._adjust_thermostats_for_battery_conservation()
            
        except Exception as e:
            self.logger.error(f"Error in peak period handling: {str(e)}")
            raise
    
    def _handle_peak_end(self) -> None:
        """Handle end of peak period operations."""
        try:
            # Reset precooling status for next day
            self.metrics.set_precooling_status(False)
            self.logger.info("Peak period ended, reset precooling status")
            
        except Exception as e:
            self.logger.error(f"Error in peak-end handling: {str(e)}")
            raise
    
    def _is_battery_low(self) -> bool:
        """
        Determine if battery level is low based on time remaining in peak period.
        
        Returns:
            bool: True if battery is considered low for current conditions
        """
        try:
            # Get current battery level
            battery_percent = self.tesla.get_battery_charge()
            
            # Calculate time remaining in current peak period
            time_remaining = self._get_peak_time_remaining()
            
            if time_remaining is None:
                return False
            
            # Check against configured thresholds
            for threshold in self.battery_thresholds:
                if time_remaining <= threshold['time_remaining_minutes']:
                    if battery_percent <= threshold['level_percent']:
                        self.logger.warning(f"Battery low: {battery_percent}% with {time_remaining} minutes remaining")
                        return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking battery level: {str(e)}")
            return False
    
    def _get_peak_time_remaining(self) -> Optional[int]:
        """
        Calculate minutes remaining in current peak period.
        
        Returns:
            int or None: Minutes remaining in peak period, None if not in peak
        """
        try:
            now = datetime.now()
            current_time = now.time()
            current_month = now.month
            
            # Find current season
            for season_config in self.settings['seasons'].values():
                if current_month in season_config['months']:
                    # Check each peak period
                    for peak_period in season_config['peak_periods']:
                        peak_start = datetime.strptime(peak_period['start'], '%H:%M').time()
                        peak_end = datetime.strptime(peak_period['end'], '%H:%M').time()
                        
                        if peak_start <= current_time <= peak_end:
                            # Calculate time remaining
                            end_datetime = datetime.combine(now.date(), peak_end)
                            time_remaining = (end_datetime - now).total_seconds() / 60
                            return int(time_remaining)
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error calculating peak time remaining: {str(e)}")
            return None
    
    def _adjust_thermostats_for_battery_conservation(self) -> None:
        """Adjust all thermostats to conserve battery during peak periods."""
        for thermostat_id in self.thermostat_ids:
            try:
                current_setpoint = self.honeywell.get_cool_setpoint(thermostat_id)
                new_setpoint = current_setpoint + self.thermostat_increment
                
                # Safety check - don't set too high
                if new_setpoint <= 85:  # Max reasonable indoor temperature
                    success = self.honeywell.set_thermostat_cool_setpoint(thermostat_id, new_setpoint)
                    
                    if success:
                        self.metrics.record_action('adjust_thermostat', {
                            'thermostat_id': thermostat_id,
                            'previous_setpoint': current_setpoint,
                            'new_setpoint': new_setpoint,
                            'reason': 'battery_conservation'
                        })
                        
                        self.logger.info(f"Adjusted thermostat {thermostat_id}: {current_setpoint}°F → {new_setpoint}°F")
                    else:
                        self.logger.error(f"Failed to adjust thermostat {thermostat_id}")
                else:
                    self.logger.warning(f"Skipped thermostat {thermostat_id} - new setpoint {new_setpoint}°F too high")
                    
            except Exception as e:
                self.logger.error(f"Error adjusting thermostat {thermostat_id}: {str(e)}")
                continue
        
        # Send notification
        self.notifications.notify('info', 'battery_adjusted', {
            'Thermostats Adjusted': len(self.thermostat_ids),
            'Adjustment': f"+{self.thermostat_increment}°F",
            'Reason': 'Battery conservation during peak period'
        })
    
    def _activate_precooling(self) -> None:
        """Activate precooling by lowering thermostat setpoints."""
        try:
            for thermostat_id in self.thermostat_ids:
                try:
                    current_setpoint = self.honeywell.get_cool_setpoint(thermostat_id)
                    new_setpoint = current_setpoint - self.precool_adjustment
                    
                    # Safety check - don't set too low
                    if new_setpoint >= 68:  # Min reasonable indoor temperature
                        success = self.honeywell.set_thermostat_cool_setpoint(thermostat_id, new_setpoint)
                        
                        if success:
                            self.metrics.record_action('adjust_thermostat', {
                                'thermostat_id': thermostat_id,
                                'previous_setpoint': current_setpoint,
                                'new_setpoint': new_setpoint,
                                'reason': 'precooling'
                            })
                            
                            self.logger.info(f"Precool thermostat {thermostat_id}: {current_setpoint}°F → {new_setpoint}°F")
                        else:
                            self.logger.error(f"Failed to precool thermostat {thermostat_id}")
                    else:
                        self.logger.warning(f"Skipped precool thermostat {thermostat_id} - new setpoint {new_setpoint}°F too low")
                        
                except Exception as e:
                    self.logger.error(f"Error precooling thermostat {thermostat_id}: {str(e)}")
                    continue
            
            # Set precooling status
            self.metrics.set_precooling_status(True)
            
            # Send notification
            self.notifications.notify('info', 'precool_activated', {
                'Thermostats Adjusted': len(self.thermostat_ids),
                'Adjustment': f"-{self.precool_adjustment}°F",
                'Trigger': f"High temperature forecast (≥{self.precool_threshold}°F)"
            })
            
        except Exception as e:
            self.logger.error(f"Error activating precooling: {str(e)}")
            raise

