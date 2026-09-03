# Stop
sudo launchctl kill SIGTERM system/com.computor.tutor-agent

# Restart
sudo launchctl kickstart -k system/com.computor.tutor-agent

# Unload completely (stop + remove from launchd)
sudo launchctl bootout system/com.computor.tutor-agent

# Load again
sudo launchctl bootstrap system /Library/LaunchDaemons/com.computor.tutor-agent.plist



# 1. Stop & unload the existing primary
sudo launchctl bootout system/com.computor.tutor-agent

# 2. Replace its plist with the updated draft, then load
sudo cp /Users/theta/computor/computor-agent/deploy/launchd/com.computor.tutor-agent.plist /Library/LaunchDaemons/
sudo launchctl bootstrap system /Library/LaunchDaemons/com.computor.tutor-agent.plist

# 3. Make the secondary log directory and install the secondary plist
sudo mkdir -p /var/log/computor-agent-c2
sudo cp /Users/theta/computor/computor-agent/deploy/launchd/com.computor.tutor-agent-c2.plist /Library/LaunchDaemons/
sudo launchctl bootstrap system /Library/LaunchDaemons/com.computor.tutor-agent-c2.plist

sudo mkdir -p /var/log/computor-agent-c3
sudo cp /Users/theta/computor/computor-agent/deploy/launchd/com.computor.tutor-agent-c3.plist /Library/LaunchDaemons/
sudo launchctl bootstrap system /Library/LaunchDaemons/com.computor.tutor-agent-c3.plist


# 4. Verify
sudo launchctl print system/com.computor.tutor-agent | head -20
sudo launchctl print system/com.computor.tutor-agent-c2 | head -20
sudo launchctl print system/com.computor.tutor-agent-c3 | head -20


# Primary (com.computor.tutor-agent — now on port 8081)
sudo launchctl kill SIGTERM system/com.computor.tutor-agent     # stop (KeepAlive will relaunch)
sudo launchctl bootout system/com.computor.tutor-agent          # stop & unload (won't relaunch)

# Secondary (com.computor.tutor-agent-c2 — port 8082)
sudo launchctl kill SIGTERM system/com.computor.tutor-agent-c2  # stop (relaunches)
sudo launchctl bootout system/com.computor.tutor-agent-c2       # stop & unload

# Tertiary (com.computor.tutor-agent-c3 — port 8083)
sudo launchctl kill SIGTERM system/com.computor.tutor-agent-c3  # stop (relaunches)
sudo launchctl bootout system/com.computor.tutor-agent-c3       # stop & unload


sudo launchctl kickstart -k system/com.computor.tutor-agent
sudo launchctl kickstart -k system/com.computor.tutor-agent-c2
sudo launchctl kickstart -k system/com.computor.tutor-agent-c3
