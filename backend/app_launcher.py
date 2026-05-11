"""
MediPath Desktop Launcher
=========================
This file is the ENTRY POINT for the packaged .exe.
It handles:
  - Resolving resource paths when running from a PyInstaller bundle
  - Starting Flask in a background thread (no console window)
  - Auto-opening the browser once the server is ready
  - Writing errors to a log file next to the .exe
"""

import os
import sys
import time
import socket
import logging
import threading
import webbrowser

# ──────────────────────────────────────────────
# 1. Resource path resolver (PyInstaller-safe)
# ──────────────────────────────────────────────
def resource_path(relative_path):
    """
    Return the absolute path to a bundled resource.
    Works both in development and when frozen by PyInstaller.
    """
    if hasattr(sys, '_MEIPASS'):
        # Running inside a PyInstaller bundle
        base = sys._MEIPASS
    else:
        # Running normally in development
        base = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base, relative_path)


# ──────────────────────────────────────────────
# 2. Working directory — writable location next
#    to the .exe for the database & logs
# ──────────────────────────────────────────────
if hasattr(sys, '_MEIPASS'):
    # Place mutable files beside the .exe, not inside the bundle
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.abspath(os.path.dirname(__file__))

os.chdir(APP_DIR)   # Flask's send_from_directory uses CWD

# ──────────────────────────────────────────────
# 3. Logging — errors go to medipath_errors.log
# ──────────────────────────────────────────────
log_file = os.path.join(APP_DIR, 'medipath_errors.log')
logging.basicConfig(
    filename=log_file,
    level=logging.ERROR,
    format='%(asctime)s  %(levelname)s  %(message)s'
)

# ──────────────────────────────────────────────
# 4. Patch sys.path so bundled modules resolve
# ──────────────────────────────────────────────
if hasattr(sys, '_MEIPASS'):
    sys.path.insert(0, sys._MEIPASS)

HOST = '127.0.0.1'
PORT = 5005
URL  = f'http://{HOST}:{PORT}'


# ──────────────────────────────────────────────
# 5. Copy static assets from bundle to APP_DIR
#    so send_from_directory can serve them
# ──────────────────────────────────────────────
def copy_assets_if_needed():
    """
    PyInstaller bundles files into _MEIPASS (read-only temp folder).
    Flask's send_from_directory needs them in the CWD.
    We only copy if they're missing.
    """
    if not hasattr(sys, '_MEIPASS'):
        return   # No need in dev mode

    assets = [
        'index.html', 'styles.css', 'script.js',
        'login.html', 'register.html', 'dashboard.html',
        'doctors.html', 'appointments.html', 'contact.html',
        'emergency.html', 'ai-assistant.html',
        'doctor-login.html', 'doctor-register.html',
        'doctor-dashboard.html', 'doctor-appointments.html',
        'doctor-messages.html', 'doctor-profile.html',
        'doctor-pending.html',
    ]

    for asset in assets:
        src  = resource_path(asset)
        dest = os.path.join(APP_DIR, asset)
        if os.path.exists(src) and not os.path.exists(dest):
            import shutil
            shutil.copy2(src, dest)

    # Copy admin folder
    admin_src  = resource_path('admin')
    admin_dest = os.path.join(APP_DIR, 'admin')
    if os.path.exists(admin_src) and not os.path.exists(admin_dest):
        import shutil
        shutil.copytree(admin_src, admin_dest)


# ──────────────────────────────────────────────
# 6. Check if port is already in use
# ──────────────────────────────────────────────
def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((HOST, port)) == 0


# ──────────────────────────────────────────────
# 7. Wait for Flask to be ready, then open browser
# ──────────────────────────────────────────────
def open_browser():
    """Poll until server is up, then open the browser."""
    for _ in range(30):          # try for ~30 seconds
        time.sleep(1)
        if port_in_use(PORT):
            webbrowser.open(URL)
            return
    logging.error("Timed out waiting for Flask server to start.")


# ──────────────────────────────────────────────
# 8. Start Flask
# ──────────────────────────────────────────────
def start_flask():
    try:
        # Import app AFTER paths are set up
        from app import app, init_db
        init_db()
        # debug=False & use_reloader=False are REQUIRED for PyInstaller
        app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
    except Exception as e:
        logging.exception("Flask failed to start")


# ──────────────────────────────────────────────
# 9. Entry point
# ──────────────────────────────────────────────
if __name__ == '__main__':
    # If port is already in use (double-clicked again), just open browser
    if port_in_use(PORT):
        webbrowser.open(URL)
        sys.exit(0)

    copy_assets_if_needed()

    # Start Flask in a background daemon thread
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    # Open browser once ready (runs in another thread so launcher doesn't block)
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()

    # Keep the main thread alive (required — daemon threads die with main thread)
    flask_thread.join()
