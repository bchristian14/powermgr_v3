"""
Tesla Powerwall API client with token file management and refresh logic.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import requests
from .base_client import BaseAPIClient


class TeslaTokenError(Exception):
    """Raised when token operations fail."""
    pass


class TeslaAPI(BaseAPIClient):
    """Tesla Powerwall API client with automatic token refresh."""
    
    def __init__(self, token_file_path: str, energy_site_id: str, client_id: str = None):
        """
        Initialize Tesla Powerwall API client.
        
        Args:
            token_file_path: Path to the tesla_token.json file
            energy_site_id: Tesla energy site ID
            client_id: Tesla app client ID (optional, for refresh)
        """
        super().__init__(base_url="https://owner-api.teslamotors.com")
        
        self.token_file_path = Path(token_file_path)
        self.energy_site_id = energy_site_id
        self.client_id = client_id
        self._token_data: Optional[Dict] = None
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Load initial token
        self._load_token()
        
        # Set initial authorization header
        self._update_auth_header()
        
    def _load_token(self) -> None:
        """Load token from file."""
        try:
            if not self.token_file_path.exists():
                raise TeslaTokenError(f"Token file not found: {self.token_file_path}")
            
            with open(self.token_file_path, 'r') as f:
                self._token_data = json.load(f)
            
            # Validate required fields
            required_fields = ['access_token', 'token_type']
            for field in required_fields:
                if field not in self._token_data:
                    raise TeslaTokenError(f"Missing required token field: {field}")
            
            self.logger.info("Loaded Tesla token from file")
            
        except (json.JSONDecodeError, KeyError) as e:
            raise TeslaTokenError(f"Invalid token file format: {e}")
        except Exception as e:
            raise TeslaTokenError(f"Failed to load token: {e}")
    
    def _save_token(self) -> None:
        """Save token to file."""
        try:
            # Write atomically using a temporary file
            temp_file = self.token_file_path.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(self._token_data, f, indent=2)
            
            temp_file.replace(self.token_file_path)
            self.logger.info("Tesla token saved to file")
            
        except Exception as e:
            raise TeslaTokenError(f"Failed to save token: {e}")
    
    def _update_auth_header(self) -> None:
        """Update the authorization header with current token."""
        if not self._token_data:
            raise TeslaTokenError("No token data available")
            
        self.session.headers.update({
            "Authorization": f"{self._token_data['token_type']} {self._token_data['access_token']}",
            "Content-Type": "application/json"
        })
    
    def _refresh_token(self) -> None:
        """Refresh the access token using the refresh token."""
        if not self._token_data or 'refresh_token' not in self._token_data:
            raise TeslaTokenError("No refresh token available")
        
        if not self.client_id:
            raise TeslaTokenError("Client ID required for token refresh")
        
        self.logger.info("Refreshing Tesla token...")
        
        refresh_data = {
            'grant_type': 'refresh_token',
            'client_id': self.client_id,
            'refresh_token': self._token_data['refresh_token']
        }
        
        try:
            # Use a separate session for token refresh to avoid circular calls
            refresh_session = requests.Session()
            response = refresh_session.post(
                "https://auth.tesla.com/oauth2/v3/token",
                data=refresh_data,
                timeout=30
            )
            response.raise_for_status()
            
            new_token_data = response.json()
            
            # Update token data with new values
            self._token_data.update({
                'access_token': new_token_data['access_token'],
                'token_type': new_token_data.get('token_type', 'Bearer'),
                'expires_in': new_token_data.get('expires_in', 28800)
            })
            
            # Update refresh token if provided (Tesla may rotate it)
            if 'refresh_token' in new_token_data:
                self._token_data['refresh_token'] = new_token_data['refresh_token']
            
            # Update id_token if provided
            if 'id_token' in new_token_data:
                self._token_data['id_token'] = new_token_data['id_token']
            
            # Save updated token to file
            self._save_token()
            
            # Update auth header with new token
            self._update_auth_header()
            
            self.logger.info("Tesla token refreshed successfully")
            
        except requests.RequestException as e:
            raise TeslaTokenError(f"Failed to refresh token: {e}")
        except (KeyError, json.JSONDecodeError) as e:
            raise TeslaTokenError(f"Invalid refresh token response: {e}")
    
    def _make_authenticated_request(self, method: str, url: str, **kwargs):
        """
        Make an authenticated request with automatic token refresh on 401.
        
        This overrides the base client's behavior to handle token refresh.
        """
        # Make the initial request
        response = getattr(self.session, method.lower())(url, **kwargs)
        
        # Handle token expiration with one retry
        if response.status_code == 401:
            self.logger.warning("Received 401 response, attempting token refresh")
            self._refresh_token()
            
            # Retry the request with refreshed token
            response = getattr(self.session, method.lower())(url, **kwargs)
        
        return response
    
    def get(self, endpoint: str, **kwargs):
        """Override base get method to use token refresh logic."""
        url = f"{self.base_url}{endpoint}"
        return self._make_authenticated_request('GET', url, **kwargs)
    
    def post(self, endpoint: str, **kwargs):
        """Override base post method to use token refresh logic."""
        url = f"{self.base_url}{endpoint}"
        return self._make_authenticated_request('POST', url, **kwargs)
    
    def put(self, endpoint: str, **kwargs):
        """Override base put method to use token refresh logic."""
        url = f"{self.base_url}{endpoint}"
        return self._make_authenticated_request('PUT', url, **kwargs)
        
    def health_check(self) -> bool:
        """Check if Tesla API is accessible."""
        try:
            response = self.get(f"/api/1/energy_sites/{self.energy_site_id}/live_status")
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
            response.raise_for_status()
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
            response.raise_for_status()
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
            response.raise_for_status()
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
    
    def get_power_flow(self) -> Dict[str, float]:
        """
        Get current power flow data.
        
        Returns:
            dict: Power flow data with keys like 'battery_power', 'grid_power', 'load_power'
        """
        try:
            site_info = self.get_energy_site_info()
            
            power_flow = {
                'battery_power': site_info.get('battery_power', 0.0),
                'grid_power': site_info.get('grid_power', 0.0),
                'load_power': site_info.get('load_power', 0.0),
                'solar_power': site_info.get('solar_power', 0.0)
            }
            
            self.logger.debug(f"Power flow: {power_flow}")
            return power_flow
            
        except Exception as e:
            self.logger.error(f"Failed to get power flow: {str(e)}")
            raise
    
    def get_operation_mode(self) -> str:
        """
        Get current operation mode.
        
        Returns:
            str: Operation mode ('self_consumption', 'backup', etc.)
        """
        try:
            response = self.get(f"/api/1/energy_sites/{self.energy_site_id}/site_info")
            response.raise_for_status()
            data = response.json()
            
            operation_mode = data['response'].get('default_real_mode', 'unknown')
            
            self.logger.debug(f"Operation mode: {operation_mode}")
            return operation_mode
            
        except Exception as e:
            self.logger.error(f"Failed to get operation mode: {str(e)}")
            raise
