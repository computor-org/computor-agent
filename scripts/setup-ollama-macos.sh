#!/bin/bash
#
# Setup Ollama as a persistent launchd service on macOS.
#
# This script:
# 1. Checks if Ollama is installed (installs via Homebrew if not)
# 2. Creates a launchd plist to keep Ollama running persistently
# 3. Loads the service so it starts automatically on login
# 4. Ensures Ollama survives reboots, logouts, and crashes
#
# Usage:
#   chmod +x scripts/setup-ollama-macos.sh
#   ./scripts/setup-ollama-macos.sh
#
# To uninstall the service later:
#   launchctl unload ~/Library/LaunchAgents/com.ollama.serve.plist
#   rm ~/Library/LaunchAgents/com.ollama.serve.plist

set -euo pipefail

PLIST_PATH="$HOME/Library/LaunchAgents/com.ollama.serve.plist"
LABEL="com.ollama.serve"
LOG_DIR="$HOME/Library/Logs/Ollama"

echo "=== Ollama macOS Persistent Service Setup ==="
echo ""

# 1. Check if running on macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERROR: This script is only for macOS. On Linux, use:"
    echo "  sudo systemctl enable ollama && sudo systemctl start ollama"
    exit 1
fi

# 2. Find or install Ollama
OLLAMA_BIN=""
if command -v ollama &>/dev/null; then
    OLLAMA_BIN="$(command -v ollama)"
    echo "Found Ollama at: $OLLAMA_BIN"
elif [[ -f /usr/local/bin/ollama ]]; then
    OLLAMA_BIN="/usr/local/bin/ollama"
    echo "Found Ollama at: $OLLAMA_BIN"
elif [[ -f /opt/homebrew/bin/ollama ]]; then
    OLLAMA_BIN="/opt/homebrew/bin/ollama"
    echo "Found Ollama at: $OLLAMA_BIN"
else
    echo "Ollama not found. Installing via Homebrew..."
    if ! command -v brew &>/dev/null; then
        echo "ERROR: Homebrew is not installed. Install it first:"
        echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        exit 1
    fi
    brew install ollama
    OLLAMA_BIN="$(command -v ollama)"
    echo "Installed Ollama at: $OLLAMA_BIN"
fi

echo "Ollama version: $($OLLAMA_BIN --version)"

# 3. Stop any existing Ollama processes and unload old plist
echo ""
echo "Stopping any running Ollama instances..."
if launchctl list "$LABEL" &>/dev/null 2>&1; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    echo "Unloaded existing launchd service"
fi
pkill -f "ollama serve" 2>/dev/null || true
sleep 1

# 4. Create log directory
mkdir -p "$LOG_DIR"

# 5. Create the launchd plist
echo "Creating launchd service at: $PLIST_PATH"
mkdir -p "$(dirname "$PLIST_PATH")"

cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${OLLAMA_BIN}</string>
        <string>serve</string>
    </array>

    <!-- Start automatically on login -->
    <key>RunAtLoad</key>
    <true/>

    <!-- Restart automatically if Ollama crashes or exits -->
    <key>KeepAlive</key>
    <true/>

    <!-- Wait 5 seconds before restarting after a crash -->
    <key>ThrottleInterval</key>
    <integer>5</integer>

    <!-- Log stdout and stderr -->
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/ollama.out.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/ollama.err.log</string>

    <!-- Set environment variables -->
    <key>EnvironmentVariables</key>
    <dict>
        <!-- Bind to all interfaces so remote machines can access if needed -->
        <key>OLLAMA_HOST</key>
        <string>0.0.0.0:11434</string>
        <!-- Keep only 1 model loaded to save memory (adjust as needed) -->
        <key>OLLAMA_MAX_LOADED_MODELS</key>
        <string>1</string>
    </dict>

    <!-- Increase open file limit for large models -->
    <key>SoftResourceLimits</key>
    <dict>
        <key>NumberOfFiles</key>
        <integer>65536</integer>
    </dict>
    <key>HardResourceLimits</key>
    <dict>
        <key>NumberOfFiles</key>
        <integer>65536</integer>
    </dict>
</dict>
</plist>
EOF

# 6. Load and start the service
echo "Loading launchd service..."
launchctl load "$PLIST_PATH"

# 7. Wait and verify
echo "Waiting for Ollama to start..."
sleep 3

if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo ""
    echo "=== Ollama is running! ==="
    echo ""
    echo "Service details:"
    echo "  Plist:    $PLIST_PATH"
    echo "  Logs:     $LOG_DIR/ollama.{out,err}.log"
    echo "  API:      http://localhost:11434"
    echo ""
    echo "Installed models:"
    $OLLAMA_BIN list 2>/dev/null || echo "  (none - run 'ollama pull <model>' to download one)"
    echo ""
    echo "The service will:"
    echo "  - Start automatically on login"
    echo "  - Restart automatically if it crashes (after 5s)"
    echo "  - Listen on all interfaces (0.0.0.0:11434)"
    echo ""
    echo "To manage the service:"
    echo "  View logs:    tail -f $LOG_DIR/ollama.err.log"
    echo "  Stop:         launchctl unload $PLIST_PATH"
    echo "  Start:        launchctl load $PLIST_PATH"
    echo "  Uninstall:    launchctl unload $PLIST_PATH && rm $PLIST_PATH"
else
    echo ""
    echo "WARNING: Ollama does not seem to be responding yet."
    echo "Check logs: tail -f $LOG_DIR/ollama.err.log"
    echo "You may need to wait a moment for the model to load."
fi
