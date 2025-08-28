"""
Honeywell Thermostat API client.
"""
import json
import logging
from typing import Dict, Any, List
from .base_client import BaseAPIClient


class HoneywellAPI(BaseAPIClient):
    """Honeywell Total Connect Comfort API client."""
    
    def __init__(self, client_id: str, client_secret: str, username: str, password: str):
        super().__init__(base_url="https://mytotalconnectcomfort.com")
        self.client_id = client_id
        self.client_secret = client_secret
        self.username = username
        self.password = password
        self.logger = logging.getLogger(self.__class__.__name__)
        self.access_token = None
        
        # Authenticate on initialization
        self._authenticate()
        
    def _authenticate(self) -> None:
        """Authenticate with Honeywell API and get access token."""
        try:
            auth_data = {
                "grant_type": "password",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "username": self.username,
                "password": self.password
            }
            
            response = self.post("/oauth/token", data=auth_data)
            token_data = response.json()
            
            self.access_token = token_data['access_token']
            self.session.headers.update({
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            })
            
            self.logger.info("Successfully authenticated with Honeywell API")
            
        except Exception as e:
            self.logger.error(f"Failed to authenticate with Honeywell: {str(e)}")
            raise
            
    def health_check(self) -> bool:
        """Check if Honeywell API is accessible."""
        try:
            response = self.get("/WebApi/api/locations")
            return response.status_code == 200
        except Exception as e:
            self.logger.warning(f"Honeywell API health check failed: {str(e)}")
            return False
            
    def get_locations(self) -> List[Dict[str, Any]]:
        """
        Get all locations associated with the account.
        
        Returns:
            list: List of location dictionaries
        """
        try:
            response = self.get("/WebApi/api/locations")
            data = response.json()
            
            locations = data.get('Locations', [])
            self.logger.debug(f"Found {len(locations)} locations")
            return locations
            
        except Exception as e:
            self.logger.error(f"Failed to get locations: {str(e)}")
            raise
            
    def get_thermostat_data(self, thermostat_id: str) -> Dict[str, Any]:
        """
        Get thermostat data for a specific thermostat.
        
        Args:
            thermostat_id: Thermostat device ID
            
        Returns:
            dict: Thermostat data including current temperature, setpoints, etc.
        """
        try:
            response = self.get(f"/WebApi/api/thermostats/{thermostat_id}")
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
            
            # Extract cool setpoint from the response
            cool_setpoint = thermostat_data['CoolSetpoint']
            
            self.logger.debug(f"Cool setpoint for {thermostat_id}: {cool_setpoint}°F")
            return int(cool_setpoint)
            
        except Exception as e:
            self.logger.error(f"Failed to get cool setpoint for {thermostat_id}: {str(e)}")
            raise
            
    def set_thermostat_cool_setpoint(self, thermostat_id: str, temperature: int) -> bool:
        """
        Set cooling setpoint for a thermostat.
        
        Args:
            thermostat_id: Thermostat device ID
            temperature: Temperature to set in Fahrenheit
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not 60 <= temperature <= 90:
            raise ValueError(f"Temperature must be between 60-90°F, got {temperature}")
            
        try:
            # Get current thermostat data to preserve other settings
            current_data = self.get_thermostat_data(thermostat_id)
            
            # Prepare the update payload
            update_data = {
                "CoolSetpoint": temperature,
                "HeatSetpoint": current_data.get('HeatSetpoint', 68),
                "ThermostatSetpointStatus": "TemporaryHold",
                "NextPeriodTime": None
            }
            
            response = self.put(
                f"/WebApi/api/thermostats/{thermostat_id}",
                json=update_data
            )
            
            if response.status_code == 200:
                self.logger.info(f"Successfully set cool setpoint to {temperature}°F for {thermostat_id}")
                return True
            else:
                self.logger.error(f"Failed to set setpoint: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to set cool setpoint for {thermostat_id}: {str(e)}")
            raise
            
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
            
            current_temp = thermostat_data['IndoorTemperature']
            
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

