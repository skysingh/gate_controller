# Gate Control — Raspberry Pi Zero W + Touchscreen + Blynk + GSM Modem

Raspberry Pi Zero W gate controller with a 3.5" HDMI touchscreen UI **and** Blynk mobile app control.

**Target Hardware:** Raspberry Pi Zero W with Raspberry Pi OS (32-bit)

## What This Does

Sends SMS commands to your gate controller via a USB GSM modem. You can control the gate from:
- **The touchscreen** — tap Open / Close / Status / Momentary buttons
- **The Blynk app** — same controls from your iPhone or Android, anywhere

Both work simultaneously.

## Hardware

| Item | Notes |
|------|-------|
| Raspberry Pi Zero W | Single-core ARM11, WiFi |
| 3.5" HDMI touchscreen | 480x320 resolution |
| Mini-HDMI to HDMI adapter | For Pi Zero W |
| Micro-USB OTG adapter | Micro-USB to USB-A |
| USB GSM modem | Huawei E3531, Waveshare SIM7600, etc. |
| Prepaid SIM card | Any carrier with SMS capability |
| Micro SD card | 16GB+ |
| 5V power supply | Micro-USB, 2.5A+ |

## Touchscreen Layout

```
┌─────────────────────────────────────────────┐
│ Gate Control              12:30 PM  ● MODEM │
├───────────┬───────────┬───────────┬─────────┤
│           │           │           │         │
│   OPEN    │   CLOSE   │  STATUS   │ MOMENT  │
│           │           │           │         │
├─────────────────────────────────────────────┤
│ Opening gate...          Auto-close: 22:00  │
├─────────────────────────────────────────────┤
│ RECENT ACTIVITY                             │
│ [2026-01-31 22:00] SCHEDULED auto-close     │
│ [2026-01-31 18:30] OPEN command triggered   │
│ [2026-01-31 18:25] STATUS check triggered   │
│ [2026-01-31 12:00] CLOSE command triggered  │
└─────────────────────────────────────────────┘
```

- **OPEN** (green) — Opens the gate
- **CLOSE** (red) — Closes the gate
- **STATUS** (blue) — Checks gate status
- **MOMENT** (amber) — Opens gate, auto-closes after 60 seconds with countdown
- **Status bar** — Shows last action result + auto-close time
- **Modem indicator** — Green = connected, Red = disconnected
- **Activity log** — Color-coded recent commands

## Installation

### 1. Flash SD Card
Use Raspberry Pi Imager to flash **Raspberry Pi OS (32-bit, Lite or Desktop)**.

**Note:** Ubuntu is not supported on Pi Zero W (requires ARMv7+).

Enable WiFi and SSH during imaging.

### 2. Connect Hardware
- Plug 3.5" HDMI screen into mini-HDMI (via adapter)
- Plug USB GSM modem into micro-USB (via OTG adapter)
- Insert SIM card into GSM modem
- Power up

### 3. SSH In and Install

```bash
# Copy files to Pi
scp -r ./* vsingh@<pi-ip>:~/gate-control-touch/

# SSH into Pi
ssh vsingh@<pi-ip>

# Go to project folder
cd ~/gate-control-touch

# Run installer
chmod +x install.sh
./install.sh
```

### 4. Configure

```bash
# Edit your settings
nano .env
```

Set these values:
- `BLYNK_AUTH_TOKEN` — Your Blynk auth token
- `MODEM_PORT` — Find with `ls /dev/ttyUSB*`
- `GATE_PHONE_NUMBER` — Your gate's phone number
- `SCREEN_WIDTH` / `SCREEN_HEIGHT` — Match your display (480x320 typical)
- `FULLSCREEN` — Set `false` for testing, `true` for production

### 5. Set Up Blynk

1. Download **Blynk IoT** app (iPhone/Android)
2. Create account at blynk.cloud
3. Create a **Template** with these datastreams:

| Name | Pin | Data Type | Min | Max |
|------|-----|-----------|-----|-----|
| Open | V0 | Integer | 0 | 1 |
| Close | V1 | Integer | 0 | 1 |
| Status | V2 | Integer | 0 | 1 |
| Momentary | V3 | Integer | 0 | 1 |
| Status Display | V4 | String | - | - |
| Log Display | V5 | String | - | - |
| Countdown | V6 | String | - | - |
| AutoClose Hour | V7 | Integer | 0 | 23 |
| AutoClose Min | V8 | Integer | 0 | 59 |
| Modem Status | V9 | Integer | 0 | 255 |

4. Create a **Device** from the template
5. Copy the **Auth Token** into your `.env` file

### 6. Test

```bash
# Log out and back in (for serial permissions)
logout

# SSH back in
ssh vsingh@<pi-ip>
cd ~/gate-control-touch

# Activate environment
source venv/bin/activate

# Test in windowed mode first
FULLSCREEN=false python3 gate_control_touch.py
```

Press **ESC** or **Q** to exit.

### 7. Enable Auto-Start

```bash
# Edit service file if your username isn't 'ubuntu'
sudo nano /etc/systemd/system/gate-control-touch.service

# Enable and start
sudo systemctl enable gate-control-touch
sudo systemctl start gate-control-touch
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| BLYNK_AUTH_TOKEN | — | Your Blynk auth token |
| MODEM_PORT | /dev/ttyUSB2 | Serial port for GSM modem |
| MODEM_BAUD | 115200 | Modem baud rate |
| GATE_PHONE_NUMBER | 9084321957 | Gate controller phone number |
| TIMEZONE_OFFSET | -5 | UTC offset (Eastern = -5) |
| SCREEN_WIDTH | 480 | Display width in pixels |
| SCREEN_HEIGHT | 320 | Display height in pixels |
| FULLSCREEN | true | Fullscreen mode (true/false) |

## Troubleshooting

### Screen is black / UI doesn't show
- Check HDMI connection and adapter
- Try `FULLSCREEN=false` first to test in a window
- Ensure `DISPLAY=:0` is set (the service file does this)
- Some screens need `hdmi_force_hotplug=1` in `/boot/config.txt`

### Touch not working
- Check if touch input shows up: `cat /dev/input/event0`
- Install touch calibration: `sudo apt install xinput-calibrator`
- Ensure user is in `input` group

### Modem not found
- Run `ls /dev/ttyUSB*` to find the port
- Try each ttyUSB port — modems often create 3-4 ports
- The AT command port is usually ttyUSB2 or ttyUSB0
- Check with: `screen /dev/ttyUSB2 115200` then type `AT` (should return OK)

### Screen resolution wrong
- Edit `.env` to match your actual screen resolution
- Common 3.5" sizes: 480x320, 640x480
- Add to `/boot/config.txt`:
  ```
  hdmi_group=2
  hdmi_mode=87
  hdmi_cvt=480 320 60
  ```

## Files

| File | Purpose |
|------|---------|
| gate_control_touch.py | Main script — touchscreen UI + Blynk + GSM |
| install.sh | Automated installer |
| gate-control-touch.service | Systemd auto-start service |
| .env.example | Configuration template |
| requirements.txt | Python dependencies |
| gate_log.txt | Activity log (created at runtime) |

## Comparison with Non-Touchscreen Version

| Feature | GateControl-Blynk | GateControl-Touchscreen |
|---------|-------------------|------------------------|
| Blynk app control | ✅ | ✅ |
| Physical screen | ❌ | ✅ 3.5" HDMI |
| Touch buttons | ❌ | ✅ |
| Status display | Blynk only | Screen + Blynk |
| Activity log | Blynk only | Screen + Blynk |
| Auto-close | ✅ | ✅ |
| Momentary | ✅ | ✅ with countdown bar |
| Dependencies | Python only | Python + PyGame |
| Headless operation | ✅ | Needs display connected |
