"""
Metrics and state management for the power manager.
Handles writing to ramdisk and daily persistence.
"""
import json
import os
import logging
import shutil
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from pathlib import Path


class MetricsRecorder:
    """Handles recording events to ramdisk and daily metrics persistence."""
    
    def __init__(self, ramdisk_state_file: str, permanent_metrics_dir: str):
        self.ramdisk_state_file = Path(ramdisk_state_file)
        self.permanent_metrics_dir = Path(permanent_metrics_dir)
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Ensure directories exist
        self.ramdisk_state_file.parent.mkdir(parents=True, exist_ok=True)
        self.permanent_metrics_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize state file if it doesn't exist
        self._initialize_state_file()
        
    def _initialize_state_file(self) -> None:
        """Initialize the state file with default structure if it doesn't exist."""
        if not self.ramdisk_state_file.exists():
            default_state = {
                "actions": [],
                "battery_remaining": [],
                "precooling": False,
                "last_updated": datetime.now().isoformat()
            }
            self._save_state(default_state)
            self.logger.info("Initialized new state file")
    
    def _save_state(self, state: Dict[str, Any]) -> None:
        """Save state to ramdisk file."""
        try:
            with open(self.ramdisk_state_file, 'w') as f:
                json.dump(state, f, indent=2)
            self.logger.debug("State saved to ramdisk")
        except Exception as e:
            self.logger.error(f"Failed to save state: {str(e)}")
            raise
    
    def load_state(self) -> Dict[str, Any]:
        """
        Load current state from ramdisk file.
        
        Returns:
            dict: Current state data
        """
        try:
            if self.ramdisk_state_file.exists():
                with open(self.ramdisk_state_file, 'r') as f:
                    state = json.load(f)
                self.logger.debug("State loaded from ramdisk")
                return state
            else:
                self.logger.warning("State file not found, returning default state")
                return {
                    "actions": [],
                    "battery_remaining": [],
                    "precooling": False,
                    "last_updated": datetime.now().isoformat()
                }
        except Exception as e:
            self.logger.error(f"Failed to load state: {str(e)}")
            # Return default state on error
            return {
                "actions": [],
                "battery_remaining": [],
                "precooling": False,
                "last_updated": datetime.now().isoformat()
            }
    
    def record_event(self, event_data: Dict[str, Any]) -> None:
        """
        Record an event by appending it to the current state.
        
        Args:
            event_data: Dictionary containing event information
        """
        try:
            state = self.load_state()
            
            # Add timestamp to event data
            event_data['timestamp'] = datetime.now().isoformat()
            
            # Determine event type and add to appropriate list
            if 'action' in event_data:
                state['actions'].append(event_data)
                self.logger.info(f"Recorded action: {event_data['action']}")
            elif 'battery_percent' in event_data:
                state['battery_remaining'].append({
                    'timestamp': event_data['timestamp'],
                    'battery_percent': event_data['battery_percent']
                })
                self.logger.debug(f"Recorded battery level: {event_data['battery_percent']}%")
            
            # Update last_updated timestamp
            state['last_updated'] = event_data['timestamp']
            
            self._save_state(state)
            
        except Exception as e:
            self.logger.error(f"Failed to record event: {str(e)}")
            raise
    
    def record_battery_level(self, battery_percent: float) -> None:
        """
        Record battery level measurement.
        
        Args:
            battery_percent: Current battery percentage
        """
        self.record_event({'battery_percent': battery_percent})
    
    def record_action(self, action_type: str, details: Dict[str, Any]) -> None:
        """
        Record an action taken by the system.
        
        Args:
            action_type: Type of action (e.g., 'set_battery_reserve', 'adjust_thermostat')
            details: Additional details about the action
        """
        event_data = {
            'action': action_type,
            **details
        }
        self.record_event(event_data)
    
    def set_precooling_status(self, precooling: bool) -> None:
        """
        Update precooling status in state.
        
        Args:
            precooling: Whether precooling is active
        """
        try:
            state = self.load_state()
            state['precooling'] = precooling
            state['last_updated'] = datetime.now().isoformat()
            self._save_state(state)
            
            self.logger.info(f"Precooling status set to: {precooling}")
            
        except Exception as e:
            self.logger.error(f"Failed to set precooling status: {str(e)}")
            raise
    
    def finalize_daily_metrics(self) -> str:
        """
        Move daily metrics from ramdisk to permanent storage and reset state.
        
        Returns:
            str: Path to the saved daily metrics file
        """
        try:
            # Load current state
            state = self.load_state()
            
            # Create filename with current date
            today = date.today()
            filename = f"{today.isoformat()}.json"
            permanent_file = self.permanent_metrics_dir / filename
            
            # Add summary information to state
            state['date'] = today.isoformat()
            state['finalized_at'] = datetime.now().isoformat()
            
            # Calculate daily summary
            if state['battery_remaining']:
                battery_levels = [entry['battery_percent'] for entry in state['battery_remaining']]
                state['summary'] = {
                    'min_battery_percent': min(battery_levels),
                    'max_battery_percent': max(battery_levels),
                    'avg_battery_percent': sum(battery_levels) / len(battery_levels),
                    'total_measurements': len(battery_levels),
                    'total_actions': len(state['actions'])
                }
            else:
                state['summary'] = {
                    'min_battery_percent': None,
                    'max_battery_percent': None,
                    'avg_battery_percent': None,
                    'total_measurements': 0,
                    'total_actions': len(state['actions'])
                }
            
            # Save to permanent storage
            with open(permanent_file, 'w') as f:
                json.dump(state, f, indent=2)
            
            self.logger.info(f"Daily metrics saved to {permanent_file}")
            
            # Reset state for new day
            self._reset_daily_state()
            
            return str(permanent_file)
            
        except Exception as e:
            self.logger.error(f"Failed to finalize daily metrics: {str(e)}")
            raise
    
    def _reset_daily_state(self) -> None:
        """Reset state file for a new day."""
        fresh_state = {
            "actions": [],
            "battery_remaining": [],
            "precooling": False,
            "last_updated": datetime.now().isoformat()
        }
        self._save_state(fresh_state)
        self.logger.info("State reset for new day")
    
    def get_eod_battery_level(self) -> Optional[float]:
        """
        Get the most recent battery level for end-of-day reporting.
        
        Returns:
            float or None: Most recent battery percentage, or None if no data
        """
        try:
            state = self.load_state()
            
            if state['battery_remaining']:
                # Return the most recent battery measurement
                latest_entry = state['battery_remaining'][-1]
                return latest_entry['battery_percent']
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to get EOD battery level: {str(e)}")
            return None
    
    def get_daily_summary(self) -> Dict[str, Any]:
        """
        Get summary of current day's metrics.
        
        Returns:
            dict: Summary of actions and battery levels for the day
        """
        try:
            state = self.load_state()
            
            summary = {
                'date': date.today().isoformat(),
                'total_actions': len(state['actions']),
                'total_battery_measurements': len(state['battery_remaining']),
                'precooling_active': state['precooling'],
                'last_updated': state.get('last_updated')
            }
            
            if state['battery_remaining']:
                battery_levels = [entry['battery_percent'] for entry in state['battery_remaining']]
                summary.update({
                    'current_battery_percent': battery_levels[-1],
                    'min_battery_percent': min(battery_levels),
                    'max_battery_percent': max(battery_levels),
                    'avg_battery_percent': sum(battery_levels) / len(battery_levels)
                })
            
            # Recent actions (last 5)
            summary['recent_actions'] = state['actions'][-5:] if state['actions'] else []
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Failed to get daily summary: {str(e)}")
            return {}

