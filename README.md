# Power Manager v2.0

A robust, maintainable service for managing Tesla Powerwall battery and Honeywell thermostat systems to minimize grid energy usage during expensive peak hours.

## Features

- **Automated Battery Management**: Optimizes Tesla Powerwall settings based on time-of-use periods
- **Smart Thermostat Control**: Adjusts Honeywell thermostats during peak periods to reduce energy consumption
- **Precooling Logic**: Pre-cools homes before peak periods when high temperatures are forecast
- **High Availability**: Active/passive failover between two Raspberry Pi nodes using keepalived
- **Robust Error Handling**: Comprehensive retry logic and graceful error recovery
- **Comprehensive Logging**: Structured logging with journald integration
- **Email Notifications**: Multi-level email alerts for various system events
- **Seasonal Adaptation**: Different peak periods and behavior for summer/winter seasons
- **SD Card Protection**: Uses ramdisk for frequent writes to prevent SD card wear

## Architecture

The system consists of:
- **Main Service**: Continuous daemon managed by systemd
- **Daily Metrics**: Timer-based service for daily reporting and cleanup
- **State Synchronization**: Backup node sync via rsync
- **High Availability**: keepalived manages virtual IP and service failover

## Prerequisites

- Python 3.8+
- Tesla account with Powerwall access
- Honeywell Total Connect Comfort account
- Raspberry Pi (recommended) or Linux system
- Email account for notifications

## Quick Start

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd powermgr
   ```

2. **Run the setup script**:
   ```bash
   sudo ./setup.sh
   ```

3. **Configure your settings**:
   ```bash
   sudo nano /opt/powermgr/config.yaml
   ```

4. **Start the service**:
   ```bash
   sudo systemctl start powermgr
   sudo systemctl enable powermgr
   ```

## Configuration

### Basic Configuration

Edit `/opt/powermgr/config.yaml` with your settings:

```yaml
tesla:
  api_token: "YOUR_TESLA_TOKEN"  # Get from Tesla API
  energy_site_id: "YOUR_SITE_ID"  # Your Powerwall site ID

honeywell:
  client_id: "YOUR_CLIENT_ID"  # From Honeywell developer portal
  client_secret: "YOUR_CLIENT_SECRET"
  username: "YOUR_USERNAME"  # Honeywell account username
  password: "YOUR_PASSWORD"  # Honeywell account password

notifications:
  smtp:
    server: "smtp.gmail.com"
    port: 587
    username: "your_email@gmail.com"
    password: "your_app_password"  # Use app-specific password
  recipients:
    info: ["info@example.com"]
    warning: ["warning@example.com"]
    critical: ["critical@example.com"]

settings:
  thermostat_ids: ["THERMOSTAT_ID_1", "THERMOSTAT_ID_2"]
  # ... other settings
```

### API Credentials Setup

#### Tesla API Token
1. Follow the Tesla API authentication guide: https://tesla-api.timdorr.com/api-basics/authentication
2. Use a tool like `tesla_auth` to get your token
3. Find your energy site ID from the Tesla app or API

#### Honeywell API
1. Register at https://developer.honeywell.com/
2. Create an application to get client_id and client_secret
3. Use your existing Total Connect Comfort credentials

#### Email Notifications
- For Gmail, use an app-specific password
- Configure different recipient lists for each alert level

## Usage

### Service Management

```bash
# Start/stop service
sudo systemctl start powermgr
sudo systemctl stop powermgr

# Enable/disable auto-start
sudo systemctl enable powermgr
sudo systemctl disable powermgr

# View logs
sudo journalctl -u powermgr -f

# Check status
sudo systemctl status powermgr
```

### Daily Metrics

```bash
# Enable daily metrics timer
sudo systemctl enable powermgr-metrics.timer
sudo systemctl start powermgr-metrics.timer

# Run metrics manually
sudo systemctl start powermgr-metrics.service

# View metrics logs
sudo journalctl -u powermgr-metrics -f
```

### High Availability Setup

For a two-node HA setup:

1. **Primary Node**:
   - Install and configure normally
   - Set up keepalived as MASTER

2. **Backup Node**:
   - Install with `setup.sh` and select "backup node" option
   - Configure SSH key authentication to primary
   - Set up keepalived as BACKUP

## System Behavior

### Peak Period Management

**Summer (May-October)**:
- Peak: 4:00 PM - 7:00 PM weekdays
- Pre-peak precooling at 3:30 PM if high temp ≥ 95°F
- Battery reserve set to 0% during peak
- Thermostat adjustments if battery drops below thresholds

**Winter (November-April)**:
- Peak: 6:00-9:00 AM and 5:00-8:00 PM weekdays
- Battery reserve set to 0% during peak
- Thermostat adjustments if battery drops below thresholds

### Battery Thresholds

Default thresholds for thermostat adjustment:
- 120 minutes remaining + battery ≤ 75% → +2°F
- 60 minutes remaining + battery ≤ 50% → +2°F  
- 30 minutes remaining + battery ≤ 25% → +2°F

### Notifications

- **Info**: Normal operations, daily reports
- **Warning**: Low battery, API issues
- **Critical**: System failures, configuration errors

## Monitoring

### Log Files

- **Service logs**: `journalctl -u powermgr`
- **Daily metrics**: `journalctl -u powermgr-metrics` 
- **Stored metrics**: `/var/log/powermgr/metrics/YYYY-MM-DD.json`
- **Current state**: `/mnt/ramdisk/powermgr_state.json`

### Health Checks

The service performs health checks every cycle:
- Tesla API connectivity
- Honeywell API connectivity  
- Configuration validation

### Daily Reports

Automated daily email reports include:
- Battery usage summary
- Actions taken during the day
- System health status
- End-of-day battery warnings

## Troubleshooting

### Common Issues

**Service won't start**:
```bash
# Check configuration
sudo python3 -c "import yaml; yaml.safe_load(open('/opt/powermgr/config.yaml'))"

# Check permissions
sudo chown -R pi:pi /opt/powermgr
sudo chown -R pi:pi /var/log/powermgr

# Check logs
sudo journalctl -u powermgr --no-pager
```

**API Authentication Fails**:
- Verify Tesla token hasn't expired
- Check Honeywell credentials
- Ensure network connectivity

**Ramdisk Issues**:
```bash
# Check if mounted
mountpoint /mnt/ramdisk

# Remount if needed
sudo mount /mnt/ramdisk
```

**High Availability Issues**:
- Verify keepalived configuration
- Check network connectivity between nodes
- Ensure SSH keys are properly configured

### Debug Mode

Enable debug logging in `config.yaml`:
```yaml
logging:
  level: "DEBUG"
```

Then restart the service to see detailed logs.

## Development

### Running Tests

```bash
cd /opt/powermgr
python3 -m pytest tests/
```

### Code Structure

```
powermgr/
├── core/
│   └── manager.py          # Main state machine logic
├── services/
│   ├── base_client.py      # HTTP client with retry logic
│   ├── tesla_api.py        # Tesla Powerwall API
│   └── honeywell_api.py    # Honeywell thermostat API
└── utils/
    ├── logger.py           # Logging configuration
    ├── metrics.py          # State and metrics management
    └── notifications.py    # Email notification system
```

### Adding New Features

1. Create feature branch
2. Implement changes following existing patterns
3. Add tests for new functionality
4. Update documentation
5. Test in development environment

## Security

- Service runs as non-root user (`pi`)
- API credentials stored in configuration file (protect with proper permissions)
- systemd security hardening enabled
- Network communications use TLS where supported

## License

This project is licensed under the MIT License. See LICENSE file for details.

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review system logs
3. Open an issue on the project repository
4. Include relevant log excerpts and configuration (sanitized)
