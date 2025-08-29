#!/usr/bin/env python3
"""
Power Manager Test Tool - Manual testing of power management actions.

Usage:
    python test_powermgr.py [config_file] <command> [options]

Place this file in your project root directory alongside main.py and config.yaml
"""
import sys
import yaml
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# Import directly from the powermgr package
from powermgr.core.manager import PowerManager
from powermgr.services.tesla_api import TeslaAPI
from powermgr.services.honeywell_api import HoneywellAPI
from powermgr.utils.logger import setup_logging
from powermgr.utils.metrics import MetricsRecorder
from powermgr.utils.notifications import NotificationManager


class PowerManagerTester:
    """Test tool for manually triggering power management actions."""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        self._setup_logging()
        self._initialize_components()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        config_file = Path(self.config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    
    def _setup_logging(self):
        """Set up logging for the test tool."""
        log_config = self.config.get('logging', {})
        setup_logging(
            level=log_config.get('level', 'INFO'),
            format_string=log_config.get('format')
        )
        
    def _initialize_components(self):
        """Initialize all system components."""
        # Initialize Tesla API client using token file approach
        tesla_config = self.config['tesla']
        self.tesla_client = TeslaAPI(
            token_file_path=tesla_config['token_file'],
            energy_site_id=tesla_config['energy_site_id'],
            client_id=tesla_config.get('client_id')  # Optional for refresh
        )
        
        # Initialize Honeywell API client
        honeywell_config = self.config['honeywell']
        self.honeywell_client = HoneywellAPI(
            username=honeywell_config['username'],
            password=honeywell_config['password']
        )
        
        # Initialize metrics recorder
        paths_config = self.config['paths']
        self.metrics_recorder = MetricsRecorder(
            ramdisk_state_file=paths_config['ramdisk_state_file'],
            permanent_metrics_dir=paths_config['permanent_metrics_dir']
        )
        
        # Initialize notification manager
        notifications_config = self.config['notifications']
        self.notification_manager = NotificationManager(
            smtp_config=notifications_config['smtp'],
            recipients=notifications_config['recipients']
        )
        
        # Initialize power manager
        self.power_manager = PowerManager(
            config=self.config,
            tesla_client=self.tesla_client,
            honeywell_client=self.honeywell_client,
            metrics_recorder=self.metrics_recorder,
            notification_manager=self.notification_manager
        )
        
        print(f"✓ Initialized with dry-run mode: {'ON' if self.config['settings'].get('dry_run', False) else 'OFF'}")
    
    def health_check(self):
        """Test API connectivity."""
        print("🔍 Running health checks...")
        
        try:
            tesla_healthy = self.tesla_client.health_check()
            print(f"Tesla API: {'✓ OK' if tesla_healthy else '✗ FAILED'}")
        except Exception as e:
            tesla_healthy = False
            print(f"Tesla API: ✗ FAILED - {str(e)}")
        
        try:
            honeywell_healthy = self.honeywell_client.health_check()
            print(f"Honeywell API: {'✓ OK' if honeywell_healthy else '✗ FAILED'}")
        except Exception as e:
            honeywell_healthy = False
            print(f"Honeywell API: ✗ FAILED - {str(e)}")
        
        overall = tesla_healthy and honeywell_healthy
        print(f"Overall: {'✓ HEALTHY' if overall else '✗ UNHEALTHY'}")
        
        return overall
    
    def battery_status(self):
        """Get current battery status."""
        print("🔋 Getting battery status...")
        
        try:
            battery_percent = self.tesla_client.get_battery_charge()
            reserve_setting = self.tesla_client.get_battery_reserve_setting()
            grid_status = self.tesla_client.get_grid_status()
            power_flow = self.tesla_client.get_power_flow()
            
            print(f"Battery Charge: {battery_percent:.1f}%")
            print(f"Reserve Setting: {reserve_setting}%")
            print(f"Grid Status: {grid_status}")
            print("Power Flow:")
            for key, value in power_flow.items():
                print(f"  {key.replace('_', ' ').title()}: {value:.1f}W")
                
        except Exception as e:
            print(f"✗ Error getting battery status: {e}")
            return False
            
        return True
    
    def thermostat_status(self):
        """Get all thermostat statuses."""
        print("🌡️  Getting thermostat status...")
        
        thermostat_ids = self.config['settings']['thermostat_ids']
        
        for thermostat_id in thermostat_ids:
            try:
                data = self.honeywell_client.get_thermostat_data(thermostat_id)
                current_temp = data['latestData']['uiData']['DispTemperature']
                cool_setpoint = data['latestData']['uiData']['CoolSetpoint']
                heat_setpoint = data['latestData']['uiData']['HeatSetpoint']
                
                print(f"Thermostat {thermostat_id}:")
                print(f"  Current Temp: {current_temp}°F")
                print(f"  Cool Setpoint: {cool_setpoint}°F")
                print(f"  Heat Setpoint: {heat_setpoint}°F")
                
            except Exception as e:
                print(f"✗ Error getting thermostat {thermostat_id}: {e}")
                continue
    
    def run_full_check(self):
        """Run complete power management check."""
        print("🔄 Running full power management check...")
        
        try:
            current_phase = self.power_manager._get_current_phase()
            print(f"Current phase: {current_phase}")
            
            self.power_manager.run_check()
            print("✓ Full check completed successfully")
            
        except Exception as e:
            print(f"✗ Error during full check: {e}")
            return False
            
        return True
    
    def show_state(self):
        """Show current system state."""
        print("📊 Current system state:")
        
        try:
            state = self.metrics_recorder.load_state()
            
            # Pretty print the state
            print(json.dumps(state, indent=2, default=str))
            
        except Exception as e:
            print(f"✗ Error loading state: {e}")
            return False
            
        return True


def main():
    """Main entry point for the test tool."""
    if len(sys.argv) == 1:
        print(__doc__)
        print("\nAvailable commands:")
        print("  health-check      - Test API connectivity")
        print("  battery-status    - Get current battery status") 
        print("  thermostat-status - Get all thermostat statuses")
        print("  run-full-check    - Run complete power management check")
        print("  show-state        - Show current system state")
        return
    
    # Simple argument parsing
    config_path = "config.yaml"
    command = sys.argv[1]
    
    # Check if first arg is a config file
    if command.endswith('.yaml') or command.endswith('.yml'):
        config_path = command
        command = sys.argv[2] if len(sys.argv) > 2 else None
        if not command:
            print("Error: No command specified")
            return
    
    try:
        tester = PowerManagerTester(config_path)
        
        # Execute command
        if command == 'health-check':
            tester.health_check()
        elif command == 'battery-status':
            tester.battery_status()
        elif command == 'thermostat-status':
            tester.thermostat_status()
        elif command == 'run-full-check':
            tester.run_full_check()
        elif command == 'show-state':
            tester.show_state()
        else:
            print(f"✗ Unknown command: {command}")
            print("Available commands: health-check, battery-status, thermostat-status, run-full-check, show-state")
            
    except FileNotFoundError as e:
        print(f"✗ Configuration error: {e}")
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
