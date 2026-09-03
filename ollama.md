sudo launchctl bootstrap system /Library/LaunchDaemons/com.ollama.server.plist

sudo launchctl print system/com.ollama.server | head -30
  pgrep -lf "ollama serve"
  tail -20 /tmp/ollama.err
