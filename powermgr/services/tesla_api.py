"""
Tesla Powerwall API client.
"""
import json
import logging
from typing import Dict, Any, Optional
from .base_client import BaseAPIClient


class TeslaAPI(BaseAPIClient):
    """Tesla Powerwall API client."""
    
    def __init__(self, api_token: str, energy_site_id: str):
        super().__init__(base_url="https://owner-api.teslamotors.com")
        self.api_token = api_token
        self.energy_site_id = energy_site_id
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Set authorization header
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        })
        
    def health_check(self) -> bool:
        """Check if Tesla API is accessible."""
        try:
            response = self.get(f"/api/1/energy_sites/{self.energy_site_id}/status")
            return response.status_code == 200
        except Exception as e:
            self.logger.warning(f"Tesla API health check failed: {str(e)}")
            return False
            
    def get_battery_charge(self) -> float:
        """
        Get current battery charge percentage.
        
        Returns:
            float: Battery charge percentage (0-100)
            
        Raises:
            Exception: If API call fails
        """
        try:
            response = self.get(f"/api/1/energy_sites/{self.energy_site_id}/live_status")
            data = response.json()
            
            # Extract battery percentage from response
            battery_percent = data['response']['percentage_charged']
            
            self.logger.debug(f"Current battery charge: {battery_percent}%")
            return float(battery_percent)
            
        except Exception as e:
            self.logger.error(f"Failed to get battery charge: {str(e)}")
            raise
            
    def get_battery_reserve_setting(self) -> int:
        """
        Get current battery backup reserve percentage setting.
        
        Returns:
            int: Reserve percentage setting (0-100)
            
        Raises:
            Exception: If API call fails
        """
        try:
            response = self.get(f"/api/1/energy_sites/{self.energy_site_id}/site_info")
            data = response.json()
            
            # Extract backup reserve percent from response
            reserve_percent = data['response']['backup_reserve_percent']
            
            self.logger.debug(f"Current reserve setting: {reserve_percent}%")
            return int(reserve_percent)
            
        except Exception as e:
            self.logger.error(f"Failed to get reserve setting: {str(e)}")
            raise
            
    def set_reserve_percentage(self, level: int) -> bool:
        """
        Set battery backup reserve percentage.
        
        Args:
            level: Reserve percentage to set (0-100)
            
        Returns:
            bool: True if successful, False otherwise
            
        Raises:
            Exception: If API call fails
        """
        if not 0 <= level <= 100:
            raise ValueError(f"Reserve level must be between 0 and 100, got {level}")
            
        try:
            data = {"backup_reserve_percent": level}
            response = self.post(
                f"/api/1/energy_sites/{self.energy_site_id}/backup",
                json=data
            )
            
            if response.status_code == 200:
                self.logger.info(f"Successfully set battery reserve to {level}%")
                return True
            else:
                self.logger.error(f"Failed to set reserve: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to set battery reserve: {str(e)}")
            raise
            
    def get_energy_site_info(self) -> Dict[str, Any]:
        """
        Get comprehensive energy site information.
        
        Returns:
            dict: Site information including battery status, grid status, etc.
        """
        try:
            response = self.get(f"/api/1/energy_sites/{self.energy_site_id}/live_status")
            data = response.json()
            
            site_info = data['response']
            self.logger.debug("Retrieved energy site info")
            return site_info
            
        except Exception as e:
            self.logger.error(f"Failed to get energy site info: {str(e)}")
            raise
            
    def get_grid_status(self) -> str:
        """
        Get current grid connection status.
        
        Returns:
            str: Grid status ('SystemGridConnected', 'SystemIslandedActive', etc.)
        """
        try:
            site_info = self.get_energy_site_info()
            grid_status = site_info.get('island_status', 'Unknown')
            
            self.logger.debug(f"Grid status: {grid_status}")
            return grid_status
            
        except Exception as e:
            self.logger.error(f"Failed to get grid status: {str(e)}")
            raise

