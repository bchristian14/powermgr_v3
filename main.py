#!/usr/bin/env python3
"""
Power Manager - Main entry point for the power management service.
"""
import sys
import time
import yaml
import signal
import logging
from pathlib import Path
from typing import Dict, Any

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from powermgr.core.manager import PowerManager
from powermgr.services.tesla_api import TeslaAPI
from powermgr.services.honeywell_api import HoneywellAPI
from powermgr.utils.logger import setup_logging
from powermgr.utils.metrics import MetricsRecorder
from powermgr.utils.notifications import NotificationManager


class PowerManagerService:
    """Main service class for the power manager application."""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = None
        self.power_manager = None
        self.running = False
        self.logger = None
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        if self.logger:
            self.logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            config_file = Path(self.config_path)
            if not config_file.exists():
                raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
            
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            # Validate required configuration sections
            required_sections = ['tesla', 'honeywell', 'settings', 'paths', 'notifications']
            for section in required_sections:
                if section not in config:
                    raise ValueError(f"Missing required configuration section: {section}")
            
            return config
            
        except Exception as e:
            print(f"Error loading configuration: {str(e)}")
            sys.exit(1)
    
    def initialize_components(self):
        """Initialize all system components."""
        try:
            # Set up logging
            log_config = self.config.get('logging', {})
            setup_logging(
                level=log_config.get('level', 'INFO'),
                format_string=log_config.get('format')
            )
            self.logger = logging.getLogger('PowerManagerService')
            self.logger.info("Starting Power Manager Service")
            
            # Initialize Tesla API client
            tesla_config = self.config['tesla']
            tesla_client = TeslaAPI(
                api_token=tesla_config['api_token'],
                energy_site_id=tesla_config['energy_site_id']
            )
            self.logger.info("Tesla API client initialized")
            
            # Initialize Honeywell API client
            honeywell_config = self.config['honeywell']
            honeywell_client = HoneywellAPI(
                client_id=honeywell_config['client_id'],
                client_secret=honeywell_config['client_secret'],
                username=honeywell_config['username'],
                password=honeywell_config['password']
            )
            self.logger.info("Honeywell API client initialized")
            
            # Initialize metrics recorder
            paths_config = self.config['paths']
            metrics_recorder = MetricsRecorder(
                ramdisk_state_file=paths_config['ramdisk_state_file'],
                permanent_metrics_dir=paths_config['permanent_metrics_dir']
            )
            self.logger.info("Metrics recorder initialized")
            
            # Initialize notification manager
            notifications_config = self.config['notifications']
            notification_manager = NotificationManager(
                smtp_config=notifications_config['smtp'],
                recipients=notifications_config['recipients']
            )
            self.logger.info("Notification manager initialized")
            
            # Initialize power manager
            self.power_manager = PowerManager(
                config=self.config,
                tesla_client=tesla_client,
                honeywell_client=honeywell_client,
                metrics_recorder=metrics_recorder,
                notification_manager=notification_manager
            )
            self.logger.info("Power manager initialized successfully")
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error initializing components: {str(e)}")
            else:
                print(f"Error initializing components: {str(e)}")
            sys.exit(1)
    
    def run(self):
        """Main service loop."""
        try:
            self.logger.info("Power Manager Service started")
            self.running = True
            
            # Get check interval from configuration
            check_interval = self.config['settings'].get('check_interval_seconds', 300)
            
            while self.running:
                try:
                    # Run the power management check
                    self.power_manager.run_check()
                    
                    # Sleep until next check
                    self.logger.debug(f"Sleeping for {check_interval} seconds until next check")
                    
                    # Use shorter sleep intervals to check for shutdown signals
                    sleep_time = 0
                    while sleep_time < check_interval and self.running:
                        time.sleep(min(10, check_interval - sleep_time))
                        sleep_time += 10
                    
                except KeyboardInterrupt:
                    self.logger.info("Received keyboard interrupt, shutting down...")
                    break
                except Exception as e:
                    self.logger.error(f"Error in main loop: {str(e)}")
                    # Continue running after logging the error
                    time.sleep(60)  # Wait a minute before retrying
            
        except Exception as e:
            self.logger.error(f"Fatal error in service: {str(e)}")
            sys.exit(1)
        finally:
            self.logger.info("Power Manager Service stopped")
    
    def start(self):
        """Start the service."""
        # Load configuration
        self.config = self.load_config()
        
        # Initialize all components
        self.initialize_components()
        
        # Run the service
        self.run()


def main():
    """Main entry point."""
    # Check for config file argument
    config_path = "config.yaml"
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    
    # Create and start the service
    service = PowerManagerService(config_path)
    service.start()


if __name__ == "__main__":
    main()

