#!/bin/bash

# Gate Control Touchscreen - Raspberry Pi Installation Script
# For Pi Zero W with 3.5" HDMI touchscreen

echo "========================================"
echo "  Gate Control - Touchscreen Install"
echo "  Raspberry Pi OS (32-bit)"
echo "========================================"
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "Please run without sudo (script will ask for sudo when needed)"
    exit 1
fi

# Update system
echo "[1/7] Updating system..."
sudo apt update && sudo apt upgrade -y

# Install Python and pip
echo "[2/7] Installing Python..."
sudo apt install -y python3 python3-pip python3-venv

# Install serial port dependencies
echo "[3/7] Installing serial port dependencies..."
sudo apt install -y python3-serial

# Install PyGame system dependencies
echo "[4/7] Installing display dependencies..."
sudo apt install -y python3-pygame libsdl2-dev libsdl2-image-dev \
    libsdl2-mixer-dev libsdl2-ttf-dev libfreetype6-dev \
    libportmidi-dev python3-dev

# Add user to dialout group and video/input for touchscreen
echo "[5/7] Setting up permissions..."
sudo usermod -a -G dialout $USER
sudo usermod -a -G video $USER
sudo usermod -a -G input $USER

# Create virtual environment and install packages
echo "[6/7] Setting up Python environment..."
python3 -m venv venv --system-site-packages
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Create .env file if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "Created .env file - you MUST edit it with your Blynk token!"
fi

# Set up auto-start on boot
echo "[7/7] Setting up auto-start..."
sudo cp gate-control-touch.service /etc/systemd/system/
sudo systemctl daemon-reload
echo "Auto-start service installed (not enabled yet)"

echo ""
echo "========================================"
echo "  Installation Complete!"
echo "========================================"
echo ""
echo "IMPORTANT: Log out and log back in for permissions"
echo ""
echo "Next steps:"
echo "  1. Set up Blynk (see README.md)"
echo "  2. Edit .env with your Blynk token and modem port"
echo "  3. Find modem port: ls /dev/ttyUSB* /dev/ttyAMA*"
echo "  4. Test windowed first:"
echo "       Edit .env and set FULLSCREEN=false"
echo "       source venv/bin/activate"
echo "       python3 gate_control_touch.py"
echo "  5. Once working, set FULLSCREEN=true"
echo "  6. Enable auto-start:"
echo "       sudo systemctl enable gate-control-touch"
echo "       sudo systemctl start gate-control-touch"
echo ""
echo "Press ESC or Q to exit the touchscreen UI"
echo ""
