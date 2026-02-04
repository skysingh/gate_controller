#!/usr/bin/env python3
"""
Gate Control - Raspberry Pi + Blynk + GSM Modem + Touchscreen UI
Controls SMS gate via 3.5" HDMI touchscreen and/or Blynk app

Features:
- Fullscreen touchscreen UI with Open / Close / Status / Momentary buttons
- Live status display, activity log, modem indicator
- Momentary open with visual countdown
- Daily auto-close at configurable time
- Blynk app control (works simultaneously)
- Activity logging
"""

import os
import sys
import time
import serial
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv
import blynklib as BlynkLib
from blynktimer import Timer as BlynkTimer

# Load environment variables
load_dotenv()

# Configuration
BLYNK_AUTH = os.getenv('BLYNK_AUTH_TOKEN', 'YOUR_BLYNK_AUTH_TOKEN')
MODEM_PORT = os.getenv('MODEM_PORT', '/dev/ttyUSB2')
MODEM_BAUD = int(os.getenv('MODEM_BAUD', '115200'))
GATE_PHONE = os.getenv('GATE_PHONE_NUMBER', '9084321957')
TIMEZONE_OFFSET = int(os.getenv('TIMEZONE_OFFSET', '-5'))
SCREEN_WIDTH = int(os.getenv('SCREEN_WIDTH', '480'))
SCREEN_HEIGHT = int(os.getenv('SCREEN_HEIGHT', '320'))
FULLSCREEN = os.getenv('FULLSCREEN', 'true').lower() == 'true'

# SMS Commands
COMMANDS = {
    'status': '*22#',
    'open': '1234#2#',
    'close': '1234#3#'
}

# Blynk Virtual Pins
VP_OPEN = 0
VP_CLOSE = 1
VP_STATUS = 2
VP_MOMENTARY = 3
VP_STATUS_DISPLAY = 4
VP_LOG_DISPLAY = 5
VP_COUNTDOWN = 6
VP_AUTOCLOSE_HOUR = 7
VP_AUTOCLOSE_MIN = 8
VP_MODEM_STATUS = 9

# Log file
LOG_FILE = 'gate_log.txt'
MAX_LOG_LINES = 100

# Global state
modem = None
modem_ready = False
momentary_active = False
momentary_countdown = 0
auto_close_hour = 22
auto_close_minute = 0
last_auto_close_check = None
gate_status_text = "Ready"
last_gate_reply = ""

# Thread lock for modem access
modem_lock = threading.Lock()

# Initialize Blynk
blynk = BlynkLib.Blynk(BLYNK_AUTH)
timer = BlynkTimer()


# ============================================================
# LOGGING
# ============================================================

def log_event(event):
    """Log an event with timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_line = f"[{timestamp}] {event}"
    print(log_line)
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(log_line + '\n')
        trim_log_file()
    except Exception as e:
        print(f"Log error: {e}")


def trim_log_file():
    """Keep only the last MAX_LOG_LINES"""
    try:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
        if len(lines) > MAX_LOG_LINES:
            with open(LOG_FILE, 'w') as f:
                f.writelines(lines[-MAX_LOG_LINES:])
    except FileNotFoundError:
        pass


def get_log_lines(count=8):
    """Get last N log lines for display"""
    try:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
        return [l.strip() for l in lines[-count:]][::-1]
    except FileNotFoundError:
        return ["No log entries yet."]


def get_log_content():
    """Get log content for Blynk display"""
    try:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
        return ''.join(reversed(lines[-20:]))
    except FileNotFoundError:
        return "No log entries yet."


# ============================================================
# MODEM
# ============================================================

def init_modem():
    """Initialize the GSM modem"""
    global modem, modem_ready
    try:
        with modem_lock:
            modem = serial.Serial(MODEM_PORT, MODEM_BAUD, timeout=1)
            time.sleep(2)
            send_at_command_raw('AT')
            time.sleep(0.5)
            send_at_command_raw('AT+CMGF=1')
            time.sleep(0.5)
            send_at_command_raw('AT+CNMI=2,2,0,0,0')
            time.sleep(0.5)
            modem_ready = True
        log_event("Modem initialized successfully")
        return True
    except Exception as e:
        log_event(f"Modem initialization failed: {e}")
        modem_ready = False
        return False


def send_at_command_raw(command):
    """Send AT command (must hold modem_lock)"""
    global modem
    if modem and modem.is_open:
        modem.write((command + '\r\n').encode())
        time.sleep(0.1)
        return modem.read(modem.in_waiting or 1).decode(errors='ignore')
    return None


def send_sms(phone_number, message):
    """Send SMS via GSM modem"""
    global modem, modem_ready
    if not modem_ready:
        log_event("SMS failed: Modem not ready")
        return False
    try:
        with modem_lock:
            send_at_command_raw('AT+CMGF=1')
            time.sleep(0.5)
            modem.write(f'AT+CMGS="{phone_number}"\r\n'.encode())
            time.sleep(0.5)
            modem.write((message + chr(26)).encode())
            time.sleep(3)
            response = modem.read(modem.in_waiting or 1).decode(errors='ignore')
        if 'OK' in response or '+CMGS' in response:
            log_event(f"SMS sent: {message}")
            return True
        else:
            log_event(f"SMS may have failed: {response}")
            return True
    except Exception as e:
        log_event(f"SMS error: {e}")
        return False


def check_incoming_sms():
    """Check for incoming SMS messages"""
    global modem, modem_ready, last_gate_reply
    if not modem_ready or not modem or not modem.is_open:
        return None
    try:
        with modem_lock:
            if modem.in_waiting > 0:
                data = modem.read(modem.in_waiting).decode(errors='ignore')
                if '+CMT:' in data:
                    lines = data.split('\n')
                    for i, line in enumerate(lines):
                        if '+CMT:' in line and i + 1 < len(lines):
                            message = lines[i + 1].strip()
                            if message:
                                log_event(f"SMS received: {message}")
                                last_gate_reply = message
                                return message
    except Exception as e:
        print(f"SMS read error: {e}")
    return None


# ============================================================
# GATE COMMANDS
# ============================================================

def cmd_open():
    """Open gate"""
    global gate_status_text
    log_event("OPEN command triggered")
    if send_sms(GATE_PHONE, COMMANDS['open']):
        gate_status_text = "Opening gate..."
    else:
        gate_status_text = "Failed to send open"
    update_blynk_status()


def cmd_close():
    """Close gate"""
    global gate_status_text
    log_event("CLOSE command triggered")
    if send_sms(GATE_PHONE, COMMANDS['close']):
        gate_status_text = "Closing gate..."
    else:
        gate_status_text = "Failed to send close"
    update_blynk_status()


def cmd_status():
    """Check status"""
    global gate_status_text
    log_event("STATUS check triggered")
    if send_sms(GATE_PHONE, COMMANDS['status']):
        gate_status_text = "Checking status..."
    else:
        gate_status_text = "Failed to check status"
    update_blynk_status()


def cmd_momentary():
    """Momentary open"""
    global momentary_active, momentary_countdown, gate_status_text
    if not momentary_active:
        log_event("MOMENTARY open triggered")
        if send_sms(GATE_PHONE, COMMANDS['open']):
            momentary_active = True
            momentary_countdown = 60
            gate_status_text = "Momentary - closing in 60s"
        else:
            gate_status_text = "Failed to send open"
        update_blynk_status()


def update_blynk_status():
    """Sync status to Blynk"""
    try:
        blynk.virtual_write(VP_STATUS_DISPLAY, gate_status_text)
    except:
        pass


# ============================================================
# BLYNK HANDLERS
# ============================================================

@blynk.handle_event("connect")
def blynk_connected():
    log_event("Connected to Blynk")
    blynk.sync_virtual(VP_AUTOCLOSE_HOUR)
    blynk.sync_virtual(VP_AUTOCLOSE_MIN)
    try:
        blynk.virtual_write(VP_MODEM_STATUS, 255 if modem_ready else 0)
        blynk.virtual_write(VP_LOG_DISPLAY, get_log_content())
        blynk.virtual_write(VP_STATUS_DISPLAY, gate_status_text)
    except:
        pass


@blynk.handle_event("write v0")
def v0_handler(pin, value):
    if int(value[0]) == 1:
        threading.Thread(target=cmd_open, daemon=True).start()

@blynk.handle_event("write v1")
def v1_handler(pin, value):
    if int(value[0]) == 1:
        threading.Thread(target=cmd_close, daemon=True).start()

@blynk.handle_event("write v2")
def v2_handler(pin, value):
    if int(value[0]) == 1:
        threading.Thread(target=cmd_status, daemon=True).start()

@blynk.handle_event("write v3")
def v3_handler(pin, value):
    if int(value[0]) == 1:
        threading.Thread(target=cmd_momentary, daemon=True).start()

@blynk.handle_event("write v7")
def v7_handler(pin, value):
    global auto_close_hour
    try:
        auto_close_hour = int(value[0])
        log_event(f"Auto-close hour set to {auto_close_hour}")
    except:
        pass

@blynk.handle_event("write v8")
def v8_handler(pin, value):
    global auto_close_minute
    try:
        auto_close_minute = int(value[0])
        log_event(f"Auto-close minute set to {auto_close_minute}")
    except:
        pass


# ============================================================
# TIMERS (run in Blynk thread)
# ============================================================

@timer.register(interval=1)
def momentary_timer():
    global momentary_active, momentary_countdown, gate_status_text
    if momentary_active:
        momentary_countdown -= 1
        try:
            blynk.virtual_write(VP_COUNTDOWN, f"{momentary_countdown}s")
        except:
            pass
        if momentary_countdown <= 0:
            momentary_active = False
            log_event("MOMENTARY auto-close triggered")
            if send_sms(GATE_PHONE, COMMANDS['close']):
                gate_status_text = "Gate closed (momentary)"
            else:
                gate_status_text = "Failed to auto-close!"
            try:
                blynk.virtual_write(VP_COUNTDOWN, "")
            except:
                pass
            update_blynk_status()


@timer.register(interval=30)
def check_auto_close():
    global last_auto_close_check, gate_status_text
    now = datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET)
    today = now.date()
    if (now.hour == auto_close_hour and
        now.minute == auto_close_minute and
        last_auto_close_check != today):
        last_auto_close_check = today
        log_event(f"SCHEDULED auto-close ({auto_close_hour}:{auto_close_minute:02d})")
        if send_sms(GATE_PHONE, COMMANDS['close']):
            gate_status_text = f"Scheduled close ({auto_close_hour}:{auto_close_minute:02d})"
        else:
            gate_status_text = "Scheduled close failed!"
        update_blynk_status()


@timer.register(interval=2)
def check_sms_replies():
    global gate_status_text
    message = check_incoming_sms()
    if message:
        gate_status_text = f"Gate: {message}"
        update_blynk_status()


@timer.register(interval=10)
def update_blynk_displays():
    try:
        blynk.virtual_write(VP_MODEM_STATUS, 255 if modem_ready else 0)
        blynk.virtual_write(VP_LOG_DISPLAY, get_log_content())
    except:
        pass


@timer.register(interval=60)
def reconnect_modem():
    if not modem_ready:
        log_event("Attempting modem reconnection...")
        init_modem()


# ============================================================
# BLYNK THREAD
# ============================================================

def blynk_thread():
    """Run Blynk in a separate thread"""
    while True:
        try:
            blynk.run()
            timer.run()
        except Exception as e:
            log_event(f"Blynk error: {e}")
            time.sleep(5)


# ============================================================
# PYGAME TOUCHSCREEN UI
# ============================================================

def run_ui():
    """Main touchscreen UI using PyGame"""
    import pygame

    pygame.init()

    # Display setup
    if FULLSCREEN:
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.FULLSCREEN)
        pygame.mouse.set_visible(False)
    else:
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))

    pygame.display.set_caption("Gate Control")
    clock = pygame.time.Clock()

    # Colors
    BG = (22, 20, 18)
    CARD_BG = (32, 30, 26)
    BORDER = (55, 50, 42)
    TEXT = (200, 192, 178)
    TEXT_DIM = (120, 112, 98)
    TEXT_BRIGHT = (230, 224, 212)
    GREEN = (80, 140, 80)
    GREEN_HOVER = (95, 160, 95)
    RED = (150, 70, 65)
    RED_HOVER = (170, 85, 78)
    BLUE = (70, 100, 150)
    BLUE_HOVER = (85, 115, 165)
    AMBER = (170, 140, 60)
    AMBER_HOVER = (190, 158, 72)
    MODEM_ON = (80, 160, 80)
    MODEM_OFF = (160, 70, 60)
    LOG_BG = (26, 24, 20)
    COUNTDOWN_BG = (50, 45, 30)

    # Fonts
    try:
        font_lg = pygame.font.SysFont('dejavusans', 18, bold=True)
        font_md = pygame.font.SysFont('dejavusans', 14)
        font_sm = pygame.font.SysFont('dejavusans', 11)
        font_xs = pygame.font.SysFont('dejavusans', 10)
        font_title = pygame.font.SysFont('dejavusans', 22, bold=True)
    except:
        font_lg = pygame.font.Font(None, 24)
        font_md = pygame.font.Font(None, 18)
        font_sm = pygame.font.Font(None, 15)
        font_xs = pygame.font.Font(None, 13)
        font_title = pygame.font.Font(None, 28)

    # Button class
    class TouchButton:
        def __init__(self, x, y, w, h, label, color, hover_color, action):
            self.rect = pygame.Rect(x, y, w, h)
            self.label = label
            self.color = color
            self.hover_color = hover_color
            self.action = action
            self.pressed = False
            self.press_time = 0

        def draw(self, surface):
            now = time.time()
            # Brief flash effect on press
            if self.pressed and now - self.press_time < 0.15:
                col = self.hover_color
            else:
                col = self.color
                self.pressed = False

            # Button body with rounded corners
            pygame.draw.rect(surface, col, self.rect, border_radius=8)
            pygame.draw.rect(surface, BORDER, self.rect, 1, border_radius=8)

            # Label
            txt = font_lg.render(self.label, True, TEXT_BRIGHT)
            tx = self.rect.x + (self.rect.width - txt.get_width()) // 2
            ty = self.rect.y + (self.rect.height - txt.get_height()) // 2
            surface.blit(txt, (tx, ty))

        def handle_touch(self, pos):
            if self.rect.collidepoint(pos):
                self.pressed = True
                self.press_time = time.time()
                threading.Thread(target=self.action, daemon=True).start()
                return True
            return False

    # Layout — 480x320 (landscape 3.5")
    # Top bar: 40px
    # Buttons: 4 across, ~100px tall
    # Status: 40px
    # Log: remaining

    PAD = 8
    TOP_H = 38
    BTN_Y = TOP_H + PAD
    BTN_H = 80
    BTN_W = (SCREEN_WIDTH - PAD * 5) // 4
    STATUS_Y = BTN_Y + BTN_H + PAD
    STATUS_H = 36
    LOG_Y = STATUS_Y + STATUS_H + PAD
    LOG_H = SCREEN_HEIGHT - LOG_Y - PAD

    buttons = [
        TouchButton(PAD, BTN_Y, BTN_W, BTN_H,
                    "OPEN", GREEN, GREEN_HOVER, cmd_open),
        TouchButton(PAD * 2 + BTN_W, BTN_Y, BTN_W, BTN_H,
                    "CLOSE", RED, RED_HOVER, cmd_close),
        TouchButton(PAD * 3 + BTN_W * 2, BTN_Y, BTN_W, BTN_H,
                    "STATUS", BLUE, BLUE_HOVER, cmd_status),
        TouchButton(PAD * 4 + BTN_W * 3, BTN_Y, BTN_W, BTN_H,
                    "MOMENT", AMBER, AMBER_HOVER, cmd_momentary),
    ]

    running = True
    last_log_update = 0
    cached_log = []

    while running:
        # Events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                    running = False

            elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
                if event.type == pygame.FINGERDOWN:
                    pos = (int(event.x * SCREEN_WIDTH), int(event.y * SCREEN_HEIGHT))
                else:
                    pos = event.pos
                for btn in buttons:
                    btn.handle_touch(pos)

        # Update log cache every 2 seconds
        now = time.time()
        if now - last_log_update > 2:
            cached_log = get_log_lines(6)
            last_log_update = now

        # ---- DRAW ----
        screen.fill(BG)

        # Top bar
        pygame.draw.rect(screen, CARD_BG, (0, 0, SCREEN_WIDTH, TOP_H))
        pygame.draw.line(screen, BORDER, (0, TOP_H), (SCREEN_WIDTH, TOP_H))

        # Title
        title_txt = font_title.render("Gate Control", True, TEXT_BRIGHT)
        screen.blit(title_txt, (PAD + 4, (TOP_H - title_txt.get_height()) // 2))

        # Modem indicator
        modem_col = MODEM_ON if modem_ready else MODEM_OFF
        modem_label = "MODEM OK" if modem_ready else "MODEM OFF"
        pygame.draw.circle(screen, modem_col, (SCREEN_WIDTH - 70, TOP_H // 2), 5)
        mt = font_xs.render(modem_label, True, modem_col)
        screen.blit(mt, (SCREEN_WIDTH - 60, (TOP_H - mt.get_height()) // 2))

        # Time display
        local_now = datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET)
        time_str = local_now.strftime('%I:%M %p')
        time_txt = font_sm.render(time_str, True, TEXT_DIM)
        screen.blit(time_txt, (SCREEN_WIDTH - 160, (TOP_H - time_txt.get_height()) // 2))

        # Buttons
        for btn in buttons:
            btn.draw(screen)

        # Status bar
        pygame.draw.rect(screen, CARD_BG, (PAD, STATUS_Y, SCREEN_WIDTH - PAD * 2, STATUS_H), border_radius=6)
        pygame.draw.rect(screen, BORDER, (PAD, STATUS_Y, SCREEN_WIDTH - PAD * 2, STATUS_H), 1, border_radius=6)

        # Status text
        status_str = gate_status_text
        if momentary_active:
            status_str = f"MOMENTARY — closing in {momentary_countdown}s"
            # Countdown highlight
            pygame.draw.rect(screen, COUNTDOWN_BG, (PAD + 1, STATUS_Y + 1, SCREEN_WIDTH - PAD * 2 - 2, STATUS_H - 2), border_radius=5)

        st = font_md.render(status_str, True, TEXT_BRIGHT if not momentary_active else AMBER)
        screen.blit(st, (PAD + 10, STATUS_Y + (STATUS_H - st.get_height()) // 2))

        # Auto-close info on right side of status bar
        ac_str = f"Auto-close: {auto_close_hour}:{auto_close_minute:02d}"
        ac_txt = font_xs.render(ac_str, True, TEXT_DIM)
        screen.blit(ac_txt, (SCREEN_WIDTH - PAD - 10 - ac_txt.get_width(), STATUS_Y + (STATUS_H - ac_txt.get_height()) // 2))

        # Log area
        pygame.draw.rect(screen, LOG_BG, (PAD, LOG_Y, SCREEN_WIDTH - PAD * 2, LOG_H), border_radius=6)
        pygame.draw.rect(screen, BORDER, (PAD, LOG_Y, SCREEN_WIDTH - PAD * 2, LOG_H), 1, border_radius=6)

        # Log header
        lh = font_xs.render("RECENT ACTIVITY", True, TEXT_DIM)
        screen.blit(lh, (PAD + 8, LOG_Y + 4))

        # Log entries
        ly = LOG_Y + 18
        for i, line in enumerate(cached_log):
            if ly + 14 > LOG_Y + LOG_H - 4:
                break
            # Truncate long lines
            display_line = line if len(line) < 65 else line[:62] + "..."
            # Color code
            col = TEXT_DIM
            if "OPEN" in line:
                col = GREEN
            elif "CLOSE" in line:
                col = RED
            elif "STATUS" in line:
                col = BLUE
            elif "MOMENTARY" in line:
                col = AMBER
            elif "error" in line.lower() or "failed" in line.lower():
                col = (180, 80, 70)

            lt = font_xs.render(display_line, True, col)
            screen.blit(lt, (PAD + 8, ly))
            ly += 15

        pygame.display.flip()
        clock.tick(10)  # 10 FPS for Pi Zero W single-core

    pygame.quit()


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 50)
    print("  Gate Control - Touchscreen + Blynk")
    print("=" * 50)
    print(f"Gate Phone: {GATE_PHONE}")
    print(f"Modem Port: {MODEM_PORT}")
    print(f"Screen: {SCREEN_WIDTH}x{SCREEN_HEIGHT} {'fullscreen' if FULLSCREEN else 'windowed'}")
    print(f"Auto-close: {auto_close_hour}:{auto_close_minute:02d}")
    print("=" * 50)

    # Initialize modem
    log_event("Starting Gate Control (Touchscreen)")
    init_modem()

    # Start Blynk in background thread
    blynk_t = threading.Thread(target=blynk_thread, daemon=True)
    blynk_t.start()
    log_event("Blynk thread started")

    # Run the touchscreen UI on main thread (PyGame requirement)
    run_ui()


if __name__ == '__main__':
    main()
