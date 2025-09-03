# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
# Activate virtual environment first
source venv/bin/activate

# Run the main service (requires config.yaml)
python3 main.py [config_file]

# Manual testing of components
python3 test_powermgr.py [config_file] <command>
```

### Testing
```bash
# Activate virtual environment first
source venv/bin/activate

# Run pytest tests
python3 -m pytest tests/

# Run specific test file
python3 -m pytest tests/test_manager.py
```

### Configuration
- Copy `config.yaml.example` to `config.yaml` and configure with real values
- Main config requires Tesla token file, Honeywell credentials, and thermostat IDs
- Use `dry_run: true` in settings for testing without making actual changes

## Architecture Overview

This is a Tesla Powerwall and Honeywell thermostat management system that optimizes energy usage during utility peak periods.

### Core Components

**PowerManager** (`powermgr/core/manager.py`): Main state machine that orchestrates all power management decisions based on:
- Current battery level and time remaining
- Peak/off-peak periods (seasonal: summer 4-7PM, winter 6-9AM & 5-8PM)
- Weather-based precooling logic
- Configurable battery thresholds for thermostat adjustments

**API Clients** (`powermgr/services/`):
- `tesla_api.py`: Tesla Powerwall API client with token refresh handling
- `honeywell_api.py`: Honeywell Total Connect Comfort API client using basic auth
- `base_client.py`: Common HTTP client with retry logic

**Support Systems** (`powermgr/utils/`):
- `metrics.py`: State persistence to ramdisk and permanent metrics logging
- `notifications.py`: Multi-level email notification system (info/warning/critical)
- `logger.py`: Structured logging configuration

### Key Patterns

**Dependency Injection**: Main service initializes all clients and injects them into PowerManager
**State Management**: Current state persisted to ramdisk (`/mnt/ramdisk/powermgr_state.json`), metrics archived to permanent storage
**Error Handling**: Comprehensive retry logic in base client, graceful degradation on API failures
**Configuration-Driven**: All behavior controlled via YAML config including seasonal periods, battery thresholds, and thermostat adjustments

### Service Architecture

The system runs as a systemd service with:
- Main daemon that checks every 5 minutes (configurable)
- Daily metrics service for reporting and cleanup
- High availability support with keepalived failover
- Ramdisk usage to protect SD cards from frequent writes

### Token Management

Tesla API uses file-based token storage with automatic refresh. Token file path specified in config, not embedded tokens.