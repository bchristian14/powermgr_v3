#!/usr/bin/env python3
"""
Daily metrics processing script.
This script is run by systemd timer to process daily metrics and send reports.
"""
import sys
import yaml
import logging
from pathlib import Path
from typing import Dict, Any

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from powermgr.utils.logger import setup_logging
from powermgr.utils.metrics import MetricsRecorder
from powermgr.utils.notifications import NotificationManager


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Load configuration from YAML file."""
    try:
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        return config
        
    except Exception as e:
        print(f"Error loading configuration: {str(e)}")
        sys.exit(1)


def process_daily_metrics():
    """Process daily metrics and send reports."""
    try:
        # Load configuration
        config = load_config()
        
        # Set up logging
        log_config = config.get('logging', {})
        setup_logging(
            level=log_config.get('level', 'INFO'),
            format_string=log_config.get('format')
        )
        logger = logging.getLogger('DailyMetrics')
        logger.info("Starting daily metrics processing")
        
        # Initialize components
        paths_config = config['paths']
        metrics_recorder = MetricsRecorder(
            ramdisk_state_file=paths_config['ramdisk_state_file'],
            permanent_metrics_dir=paths_config['permanent_metrics_dir']
        )
        
        notifications_config = config['notifications']
        notification_manager = NotificationManager(
            smtp_config=notifications_config['smtp'],
            recipients=notifications_config['recipients']
        )
        
        # Get daily summary before finalizing
        daily_summary = metrics_recorder.get_daily_summary()
        logger.info(f"Daily summary: {daily_summary}")
        
        # Check end-of-day battery level
        eod_battery_level = metrics_recorder.get_eod_battery_level()
        eod_threshold = config['settings']['eod_battery_warning_threshold']
        
        if eod_battery_level is not None and eod_battery_level <= eod_threshold:
            logger.warning(f"End-of-day battery level {eod_battery_level}% is below threshold {eod_threshold}%")
            notification_manager.send_eod_battery_warning(eod_battery_level, eod_threshold)
        
        # Finalize daily metrics (save to permanent storage and reset state)
        saved_file = metrics_recorder.finalize_daily_metrics()
        logger.info(f"Daily metrics finalized and saved to: {saved_file}")
        
        # Send daily report
        notification_manager.send_daily_report(daily_summary)
        logger.info("Daily report sent")
        
        logger.info("Daily metrics processing completed successfully")
        
    except Exception as e:
        logger.error(f"Error processing daily metrics: {str(e)}")
        
        # Try to send error notification
        try:
            notification_manager.notify('critical', 'api_error', {
                'Error': str(e),
                'Script': 'daily_metrics.py',
                'Action': 'Check system logs and fix the issue'
            })
        except:
            pass  # Don't fail if notification also fails
        
        sys.exit(1)


def main():
    """Main entry point."""
    # Check for config file argument
    config_path = "config.yaml"
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    
    process_daily_metrics()


if __name__ == "__main__":
    main()
