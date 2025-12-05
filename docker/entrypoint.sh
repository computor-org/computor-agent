#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}       Computor Agent${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""

# =============================================================================
# Git Configuration
# =============================================================================

echo -e "${YELLOW}Configuring Git...${NC}"

# Set Git user identity (required for commits)
git config --global user.name "${GIT_USER_NAME:-Computor Agent}"
git config --global user.email "${GIT_USER_EMAIL:-agent@computor.local}"

# Configure Git for better compatibility
git config --global init.defaultBranch main
git config --global core.autocrlf input
git config --global pull.rebase false

echo "  Name:  $(git config --global user.name)"
echo "  Email: $(git config --global user.email)"
echo ""

# =============================================================================
# LLM Configuration
# =============================================================================

echo -e "${YELLOW}LLM Configuration:${NC}"
echo "  Provider:    ${LLM_PROVIDER:-ollama}"
echo "  Base URL:    ${LLM_BASE_URL:-http://host.docker.internal:11434/v1}"
echo "  Model:       ${LLM_MODEL:-devstral-small}"
echo "  Temperature: ${LLM_TEMPERATURE:-0.7}"
if [ -n "$LLM_API_KEY" ]; then
    echo "  API Key:     ***configured***"
fi
echo ""

# Check if LLM server is reachable
echo -e "${YELLOW}Checking LLM server connection...${NC}"
BASE_URL="${LLM_BASE_URL:-http://host.docker.internal:11434/v1}"
HEALTH_URL="${BASE_URL%/v1}"

if curl -s --connect-timeout 5 "${HEALTH_URL}/api/tags" > /dev/null 2>&1 || \
   curl -s --connect-timeout 5 "${BASE_URL}/models" > /dev/null 2>&1; then
    echo -e "${GREEN}  LLM server is reachable!${NC}"
else
    echo -e "${RED}  Warning: Cannot reach LLM server at ${BASE_URL}${NC}"
    echo -e "${YELLOW}  Make sure your LLM server is running.${NC}"
fi
echo ""

# =============================================================================
# Backend Configuration
# =============================================================================

echo -e "${YELLOW}Backend Configuration:${NC}"
if [ -n "$COMPUTOR_BACKEND_URL" ]; then
    echo "  URL:      ${COMPUTOR_BACKEND_URL}"
    echo "  Username: ${COMPUTOR_BACKEND_USERNAME:-not set}"
    if [ -n "$COMPUTOR_BACKEND_PASSWORD" ]; then
        echo "  Password: ***configured***"
    else
        echo -e "  ${RED}Password: NOT SET${NC}"
    fi
    echo "  Timeout:  ${COMPUTOR_BACKEND_TIMEOUT:-30}s"
else
    echo -e "  ${RED}Backend not configured!${NC}"
    echo "  Set COMPUTOR_BACKEND_URL, COMPUTOR_BACKEND_USERNAME, COMPUTOR_BACKEND_PASSWORD"
fi
echo ""

# =============================================================================
# Agent Configuration
# =============================================================================

echo -e "${YELLOW}Agent Configuration:${NC}"
echo "  Name:        ${COMPUTOR_AGENT_NAME:-Tutor AI}"
echo "  Description: ${COMPUTOR_AGENT_DESCRIPTION:-not set}"
echo ""

# =============================================================================
# Tutor Configuration
# =============================================================================

echo -e "${YELLOW}Tutor Configuration:${NC}"
echo "  Personality: ${TUTOR_PERSONALITY_TONE:-friendly_professional}"
echo "  Language:    ${TUTOR_LANGUAGE:-en}"
echo ""
echo "  Security:"
echo "    Enabled:      ${TUTOR_SECURITY_ENABLED:-true}"
echo "    Confirmation: ${TUTOR_SECURITY_REQUIRE_CONFIRMATION:-true}"
echo "    Block:        ${TUTOR_SECURITY_BLOCK_ON_THREAT:-true}"
echo ""
echo "  Context:"
echo "    Prev msgs:    ${TUTOR_CONTEXT_PREVIOUS_MESSAGES:-3}"
echo "    Comments:     ${TUTOR_CONTEXT_INCLUDE_COMMENTS:-true}"
echo "    Reference:    ${TUTOR_CONTEXT_INCLUDE_REFERENCE:-false}"
echo "    Max lines:    ${TUTOR_CONTEXT_MAX_CODE_LINES:-1000}"
echo "    Notes:        ${TUTOR_CONTEXT_STUDENT_NOTES_ENABLED:-false}"
echo ""
echo "  Grading:"
echo "    Enabled:      ${TUTOR_GRADING_ENABLED:-false}"
echo "    Auto submit:  ${TUTOR_GRADING_AUTO_SUBMIT:-false}"
echo ""
echo "  Scheduler:"
echo "    Enabled:      ${TUTOR_SCHEDULER_ENABLED:-true}"
echo "    Poll:         ${TUTOR_SCHEDULER_POLL_INTERVAL:-30}s"
echo "    Concurrent:   ${TUTOR_SCHEDULER_MAX_CONCURRENT:-5}"
echo "    Cooldown:     ${TUTOR_SCHEDULER_COOLDOWN:-60}s"
echo ""

# =============================================================================
# Git Credentials
# =============================================================================

echo -e "${YELLOW}Git Credentials:${NC}"
CRED_FILE="${CONFIG_DIR:-/data/config}/credentials.yaml"
if [ -f "$CRED_FILE" ]; then
    echo -e "  ${GREEN}Credentials file: $CRED_FILE${NC}"
else
    echo -e "  ${RED}No credentials file found${NC}"
    echo "  Create: $CRED_FILE"
fi
echo ""

# =============================================================================
# Workspace
# =============================================================================

echo -e "${YELLOW}Workspace:${NC}"
echo "  Root:   ${WORKSPACE_ROOT:-/data/workspace}"
echo "  Config: ${CONFIG_DIR:-/data/config}"
echo "  Notes:  ${TUTOR_CONTEXT_STUDENT_NOTES_DIR:-/data/notes}"
echo "  Logs:   ${LOG_DIR:-/data/logs}"
echo ""

# =============================================================================
# Usage
# =============================================================================

echo -e "${CYAN}======================================${NC}"
echo -e "${CYAN}Usage:${NC}"
echo "  computor-agent --help              # Show help"
echo "  computor-agent chat                # Interactive chat"
echo "  computor-agent ask 'question'      # Single question"
echo "  computor-agent providers           # List providers"
echo ""
echo "  # Tutor agent (when backend is configured)"
echo "  python -m computor_agent.tutor     # Start tutor agent"
echo -e "${CYAN}======================================${NC}"
echo ""

# Execute the command passed to docker run
exec "$@"
