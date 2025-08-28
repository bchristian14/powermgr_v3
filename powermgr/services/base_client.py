"""
Base API client with retry logic and error handling.
"""
import time
import logging
import requests
from typing import Dict, Any, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class BaseAPIClient:
    """Base class for API clients with built-in retry logic and error handling."""
    
    def __init__(self, base_url: str = "", timeout: int = 30, max_retries: int = 3):
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Configure session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            status_forcelist=[429, 500, 502, 503, 504],
            backoff_factor=1,
            respect_retry_after_header=True
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """
        Make HTTP request with error handling and logging.
        
        Args:
            method: HTTP method (GET, POST, PUT, etc.)
            endpoint: API endpoint
            **kwargs: Additional arguments for requests
            
        Returns:
            requests.Response object
            
        Raises:
            requests.RequestException: If request fails after retries
        """
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}" if self.base_url else endpoint
        
        # Set default timeout if not provided
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout
            
        self.logger.debug(f"Making {method} request to {url}")
        
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            
            self.logger.debug(f"Request successful: {response.status_code}")
            return response
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed: {method} {url} - {str(e)}")
            raise
            
    def get(self, endpoint: str, **kwargs) -> requests.Response:
        """Make GET request."""
        return self._make_request("GET", endpoint, **kwargs)
        
    def post(self, endpoint: str, **kwargs) -> requests.Response:
        """Make POST request."""
        return self._make_request("POST", endpoint, **kwargs)
        
    def put(self, endpoint: str, **kwargs) -> requests.Response:
        """Make PUT request."""
        return self._make_request("PUT", endpoint, **kwargs)
        
    def delete(self, endpoint: str, **kwargs) -> requests.Response:
        """Make DELETE request."""
        return self._make_request("DELETE", endpoint, **kwargs)
        
    def health_check(self) -> bool:
        """
        Perform a basic health check of the API.
        Should be overridden by subclasses.
        
        Returns:
            bool: True if API is healthy, False otherwise
        """
        try:
            response = self.get("/")
            return response.status_code == 200
        except Exception as e:
            self.logger.warning(f"Health check failed: {str(e)}")
            return False

