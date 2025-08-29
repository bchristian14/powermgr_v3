"""
Honeywell Thermostat API client using username/password authentication.
"""
import json
import logging
from typing import Dict, Any, List
from .base_client import BaseAPIClient


class HoneywellAPI(BaseAPIClient):
    """Honeywell Total Connect Comfort API client with username/password auth."""
    
    def __init__(self, username: str, password: str):
        super().__init__(base_url="https://www.mytotalconnectcomfort.com/portal")
        self.username = username
        self.password = password
        self.logger = logging.getLogger(self.__class__.__name__)
        self.authenticated = False
        
        # Set required headers
        self.session.headers.update({
            'X-Requested-With': 'XMLHttpRequest'
        })
        
        # Authenticate on initialization
        self._authenticate()
        
    def _authenticate(self) -> None:
        """Authenticate with Honeywell using username/password."""
        try:
            # First, get the base page to establish session
            self.session.get(self.base_url, timeout=60)
            
            # Login parameters matching your working script
            params = {
                'UserName': self.username,
                'Password': self.password,
                'RememberMe': 'false',
                'timeOffset': 0
            }
            
            # Login using POST with params (not data)
            response = self.session.post(self.base_url, params=params, timeout=60)
            response.raise_for_status()
            
            # Check if login was successful by parsing JSON response
            login_result = response.json()
            
            # If we get here without exception, assume success
            self.authenticated = True
            self.logger.info("Successfully authenticated with Honeywell API")
            
        except Exception as e:
            self.logger.error(f"Failed to authenticate with Honeywell: {str(e)}")
            self.authenticated = False
            raise
            
    def health_check(self) -> bool:
        """Check if Honeywell API is accessible and we're authenticated."""
        return self.authenticated
            
    def get_thermostat_data(self, thermostat_id: str) -> Dict[str, Any]:
        """
        Get thermostat data for a specific thermostat using CheckDataSession endpoint.
        
        Args:
            thermostat_id: Thermostat device ID
            
        Returns:
            dict: Thermostat data including current temperature, setpoints, etc.
        """
        try:
            if not self.authenticated:
                self._authenticate()
                
            # Use the CheckDataSession endpoint like in your working script
            endpoint = f"/Device/CheckDataSession/{thermostat_id}"
            response = self.get(endpoint)
            response.raise_for_status()
            
            data = response.json()
            
            self.logger.debug(f"Retrieved thermostat data for {thermostat_id}")
            return data
            
        except Exception as e:
            self.logger.error(f"Failed to get thermostat data for {thermostat_id}: {str(e)}")
            raise
            
    def get_cool_setpoint(self, thermostat_id: str) -> int:
        """
        Get current cooling setpoint for a thermostat.
        
        Args:
            thermostat_id: Thermostat device ID
            
        Returns:
            int: Current cool setpoint in Fahrenheit
        """
        try:
            thermostat_data = self.get_thermostat_data(thermostat_id)
            
            # Extract cool setpoint from the latestData.uiData structure
            cool_setpoint = thermostat_data['latestData']['uiData']['CoolSetpoint']
            
            self.logger.debug(f"Cool setpoint for {thermostat_id}: {cool_setpoint}°F")
            return int(cool_setpoint)
            
        except Exception as e:
            self.logger.error(f"Failed to get cool setpoint for {thermostat_id}: {str(e)}")
            raise
            
    def set_thermostat_cool_setpoint(self, thermostat_id: str, temperature: int) -> bool:
        """
        Set cooling setpoint for a thermostat using the SubmitControlScreenChanges endpoint.
        
        Args:
            thermostat_id: Thermostat device ID
            temperature: Temperature to set in Fahrenheit
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not 60 <= temperature <= 90:
            raise ValueError(f"Temperature must be between 60-90°F, got {temperature}")
            
        try:
            if not self.authenticated:
                self._authenticate()
                
            # Prepare the data payload matching your working script format
            data = {
                'SystemSwitch': None,
                'HeatSetpoint': None,
                'CoolSetpoint': temperature,
                'HeatNextPeriod': None,
                'CoolNextPeriod': 81,  # Default value from your script
                'StatusHeat': None,
                'StatusCool': 1,
                'DeviceID': thermostat_id,
            }
            
            # Use the SubmitControlScreenChanges endpoint
            endpoint = "/Device/SubmitControlScreenChanges"
            response = self.post(endpoint, data=data)
            response.raise_for_status()
            
            # Verify the change by getting the new setpoint
            new_setpoint = self.get_cool_setpoint(thermostat_id)
            
            if new_setpoint == temperature:
                self.logger.info(f"Successfully set cool setpoint to {temperature}°F for {thermostat_id}")
                return True
            else:
                self.logger.warning(f"Setpoint verification failed: requested {temperature}°F, got {new_setpoint}°F")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to set cool setpoint for {thermostat_id}: {str(e)}")
            return False
            
    def get_current_temperature(self, thermostat_id: str) -> float:
        """
        Get current temperature reading from thermostat.
        
        Args:
            thermostat_id: Thermostat device ID
            
        Returns:
            float: Current temperature in Fahrenheit
        """
        try:
            thermostat_data = self.get_thermostat_data(thermostat_id)
            
            # Extract current temperature from the latestData.uiData structure
            current_temp = thermostat_data['latestData']['uiData']['DispTemperature']
            
            self.logger.debug(f"Current temperature for {thermostat_id}: {current_temp}°F")
            return float(current_temp)
            
        except Exception as e:
            self.logger.error(f"Failed to get current temperature for {thermostat_id}: {str(e)}")
            raise
            
    def get_all_thermostats_data(self, thermostat_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get data for multiple thermostats.
        
        Args:
            thermostat_ids: List of thermostat device IDs
            
        Returns:
            dict: Dictionary mapping thermostat_id to thermostat data
        """
        thermostats_data = {}
        
        for thermostat_id in thermostat_ids:
            try:
                data = self.get_thermostat_data(thermostat_id)
                thermostats_data[thermostat_id] = data
            except Exception as e:
                self.logger.error(f"Failed to get data for thermostat {thermostat_id}: {str(e)}")
                # Continue with other thermostats
                continue
                
        return thermostats_data
    
    def _re_authenticate_if_needed(self):
        """Re-authenticate if session has expired."""
        try:
            # Try a simple operation to test if we're still authenticated
            # This is a simple way to check without making assumptions about response format
            response = self.session.get(f"{self.base_url}/", timeout=30)
            
            # If we get a login page or redirect, we need to re-authenticate
            if 'login' in response.url.lower() or response.status_code != 200:
                self.logger.info("Session expired, re-authenticating...")
                self._authenticate()
                
        except Exception as e:
            self.logger.warning(f"Authentication check failed, attempting re-auth: {e}")
            self._authenticate()
