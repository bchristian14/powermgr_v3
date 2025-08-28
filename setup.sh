#!/bin/bash
# Power Manager Setup Script
# This script automates the installation and configuration of the Power Manager service

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/opt/powermgr"
# Auto-detect the user who invoked sudo
if [ -n "$SUDO_USER" ]; then
    SERVICE_USER="$SUDO_USER"
    SERVICE_GROUP=$(id -gn "$SUDO_USER")
else
    SERVICE_USER="pi"  # fallback
    SERVICE_GROUP="pi"
fi
RAMDISK_SIZE="10M"
RAMDISK_MOUNT="/mnt/ramdisk"
METRICS_DIR="/var/log/powermgr/metrics"
VENV_DIR="$INSTALL_DIR/venv"
PYTHON_BIN="$VENV_DIR/bin/python"
PIP_BIN="$VENV_DIR/bin/pip"

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Check system requirements
check_requirements() {
    log_info "Checking system requirements..."
    
    # Check Python 3
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is required but not installed"
        exit 1
    fi
    
    # Check Python version (minimum 3.7)
    python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)'; then
        log_error "Python 3.7 or higher is required, found $python_version"
        exit 1
    fi
    
    # Check if venv module is available
    if ! python3 -m venv --help &> /dev/null; then
        log_error "Python venv module is required but not available"
        log_info "Try: apt install python3-venv"
        exit 1
    fi
    
    # Check rsync (for HA sync)
    if ! command -v rsync &> /dev/null; then
        log_warning "rsync not found, installing..."
        apt update && apt install -y rsync
    fi
    
    log_success "System requirements checked (Python $python_version)"
}

# Install system dependencies
install_system_dependencies() {
    log_info "Installing system dependencies..."
    
    # Install system packages
    apt update
    apt install -y python3-pip python3-venv python3-dev build-essential
    
    log_success "System dependencies installed"
}

# Create and setup virtual environment
setup_virtual_environment() {
    log_info "Setting up Python virtual environment..."
    
    # Create virtual environment
    python3 -m venv "$VENV_DIR"
    
    # Upgrade pip in virtual environment
    "$PIP_BIN" install --upgrade pip setuptools wheel
    
    # Set ownership
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$VENV_DIR"
    
    log_success "Virtual environment created at $VENV_DIR"
}

# Install Python dependencies
install_python_dependencies() {
    log_info "Installing Python dependencies in virtual environment..."
    
    # Check if requirements.txt exists
    if [ ! -f "requirements.txt" ]; then
        log_error "requirements.txt not found in current directory"
        exit 1
    fi
    
    # Install Python packages in virtual environment
    "$PIP_BIN" install -r requirements.txt
    
    # Set ownership
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$VENV_DIR"
    
    log_success "Python dependencies installed in virtual environment"
}

# Create directories
setup_directories() {
    log_info "Setting up directories..."
    
    # Create install directory
    mkdir -p "$INSTALL_DIR"
    
    # Create ramdisk mount point
    mkdir -p "$RAMDISK_MOUNT"
    
    # Create metrics directory
    mkdir -p "$METRICS_DIR"
    
    # Set ownership
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$METRICS_DIR"
    
    log_success "Directories created"
}

# Setup ramdisk
setup_ramdisk() {
    log_info "Setting up ramdisk..."
    
    # Add ramdisk entry to /etc/fstab if not already present
    if ! grep -q "$RAMDISK_MOUNT" /etc/fstab; then
        echo "tmpfs $RAMDISK_MOUNT tmpfs defaults,size=$RAMDISK_SIZE,uid=$SERVICE_USER,gid=$SERVICE_GROUP 0 0" >> /etc/fstab
        log_info "Added ramdisk entry to /etc/fstab"
    fi
    
    # Mount ramdisk
    if ! mountpoint -q "$RAMDISK_MOUNT"; then
        mount "$RAMDISK_MOUNT"
        log_info "Mounted ramdisk"
    fi
    
    log_success "Ramdisk configured"
}

# Install application files
install_application() {
    log_info "Installing application files..."
    
    # Copy application files (excluding .git, __pycache__, etc.)
    rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
          --exclude='setup.sh' --exclude='README.md' --exclude='venv' \
          ./ "$INSTALL_DIR/"
    
    # Set ownership (excluding venv which is already set)
    find "$INSTALL_DIR" -not -path "$VENV_DIR*" -exec chown "$SERVICE_USER:$SERVICE_GROUP" {} \;
    
    # Make scripts executable
    chmod +x "$INSTALL_DIR/main.py"
    chmod +x "$INSTALL_DIR/daily_metrics.py"
    
    log_success "Application files installed"
}

# Install systemd services
install_systemd_services() {
    log_info "Installing systemd services..."
    
    # Copy service files
    cp systemd/powermgr.service /etc/systemd/system/
    cp systemd/powermgr-metrics.service /etc/systemd/system/
    cp systemd/powermgr-metrics.timer /etc/systemd/system/
    
    # Update paths in service files to use virtual environment
    sed -i "s|/opt/powermgr|$INSTALL_DIR|g" /etc/systemd/system/powermgr*.service
    sed -i "s|ExecStart=python3|ExecStart=$PYTHON_BIN|g" /etc/systemd/system/powermgr*.service
    sed -i "s|ExecStart=/opt/powermgr/main.py|ExecStart=$PYTHON_BIN $INSTALL_DIR/main.py|g" /etc/systemd/system/powermgr.service
    sed -i "s|ExecStart=/opt/powermgr/daily_metrics.py|ExecStart=$PYTHON_BIN $INSTALL_DIR/daily_metrics.py|g" /etc/systemd/system/powermgr-metrics.service
    
    # Reload systemd
    systemctl daemon-reload
    
    # Enable services
    systemctl enable powermgr.service
    systemctl enable powermgr-metrics.timer
    
    log_success "Systemd services installed and enabled"
}

# Setup configuration
setup_configuration() {
    log_info "Setting up configuration..."
    
    if [ ! -f "$INSTALL_DIR/config.yaml" ]; then
        if [ -f "$INSTALL_DIR/config.yaml.example" ]; then
            cp "$INSTALL_DIR/config.yaml.example" "$INSTALL_DIR/config.yaml"
            log_warning "Created config.yaml from example. Please edit with your settings!"
        else
            log_error "config.yaml.example not found!"
            exit 1
        fi
    fi
    
    # Set ownership
    chown "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR/config.yaml"
    
    log_success "Configuration setup complete"
}

# Configure keepalived (if requested)
setup_keepalived() {
    read -p "Do you want to install and configure keepalived for HA? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Installing keepalived..."
        
        apt install -y keepalived
        
        log_info "Keepalived installed. Please configure /etc/keepalived/keepalived.conf manually."
        log_info "See documentation for example configuration."
    fi
}

# Install sync services for backup node
install_sync_services() {
    read -p "Is this a backup node for HA? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Installing sync services for backup node..."
        
        # Get primary node IP
        read -p "Enter primary node IP address: " PRIMARY_IP
        
        # Update sync service with primary IP
        sed "s/PRIMARY_NODE_IP/$PRIMARY_IP/g" systemd/powermgr-sync-state.service > /etc/systemd/system/powermgr-sync-state.service
        cp systemd/powermgr-sync-state.timer /etc/systemd/system/
        
        # Reload and enable
        systemctl daemon-reload
        systemctl enable powermgr-sync-state.timer
        
        log_success "Sync services installed for backup node"
        log_warning "Make sure SSH key authentication is set up between nodes!"
    fi
}

# Test installation
test_installation() {
    log_info "Testing installation..."
    
    # Test virtual environment
    if [ ! -f "$PYTHON_BIN" ]; then
        log_error "Virtual environment Python binary not found at $PYTHON_BIN"
        exit 1
    fi
    
    # Test configuration loading
    if sudo -u "$SERVICE_USER" "$PYTHON_BIN" -c "
import sys
sys.path.insert(0, '$INSTALL_DIR')
import yaml
with open('$INSTALL_DIR/config.yaml') as f:
    yaml.safe_load(f)
print('Configuration loads successfully')
" 2>/dev/null; then
        log_success "Configuration test passed"
    else
        log_error "Configuration test failed"
        exit 1
    fi
    
    # Test Python imports
    if sudo -u "$SERVICE_USER" "$PYTHON_BIN" -c "
import sys
sys.path.insert(0, '$INSTALL_DIR')
from powermgr.core.manager import PowerManager
from powermgr.services.tesla_api import TeslaAPI
from powermgr.services.honeywell_api import HoneywellAPI
print('Python imports successful')
" 2>/dev/null; then
        log_success "Python import test passed"
    else
        log_error "Python import test failed - check dependencies in virtual environment"
        exit 1
    fi
    
    # Test virtual environment activation script
    if [ -f "$VENV_DIR/bin/activate" ]; then
        log_success "Virtual environment activation script found"
    else
        log_warning "Virtual environment activation script not found"
    fi
    
    log_success "Installation tests passed"
}

# Create virtual environment activation helper
create_activation_helper() {
    log_info "Creating virtual environment helper script..."
    
    cat > "$INSTALL_DIR/activate_venv.sh" << EOF
#!/bin/bash
# Helper script to activate the Power Manager virtual environment
# Usage: source /opt/powermgr/activate_venv.sh

if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
    echo "Virtual environment activated"
    echo "Python: \$(which python)"
    echo "Pip: \$(which pip)"
else
    echo "Virtual environment not found at $VENV_DIR"
fi
EOF
    
    chmod +x "$INSTALL_DIR/activate_venv.sh"
    chown "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR/activate_venv.sh"
    
    log_success "Virtual environment helper created at $INSTALL_DIR/activate_venv.sh"
}

# Main installation function
main() {
    log_info "Starting Power Manager installation with virtual environment..."
    log_info "Detected user: $SERVICE_USER, group: $SERVICE_GROUP"
    
    check_root
    check_requirements
    install_system_dependencies
    setup_directories
    setup_virtual_environment
    install_python_dependencies
    setup_ramdisk
    install_application
    install_systemd_services
    setup_configuration
    create_activation_helper
    setup_keepalived
    install_sync_services
    test_installation
    
    log_success "Power Manager installation completed!"
    echo
    log_info "Next steps:"
    echo "  1. Edit $INSTALL_DIR/config.yaml with your API credentials and settings"
    echo "  2. Test the configuration: sudo systemctl start powermgr"
    echo "  3. Check logs: sudo journalctl -u powermgr -f"
    echo "  4. Enable auto-start: sudo systemctl enable powermgr"
    echo "  5. Start metrics timer: sudo systemctl start powermgr-metrics.timer"
    echo
    log_info "Virtual Environment:"
    echo "  - Location: $VENV_DIR"
    echo "  - Python: $PYTHON_BIN"
    echo "  - Activate: source $INSTALL_DIR/activate_venv.sh"
    echo
    log_warning "Remember to configure your Tesla API tokens and Honeywell credentials!"
}

# Run main function
main "$@"
