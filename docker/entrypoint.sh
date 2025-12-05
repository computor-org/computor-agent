#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}  computor-agent${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""

# Show configuration
echo -e "${YELLOW}Configuration:${NC}"
echo "  Provider:  ${LLM_PROVIDER:-ollama}"
echo "  Base URL:  ${LLM_BASE_URL:-http://host.docker.internal:11434/v1}"
echo "  Model:     ${LLM_MODEL:-devstral-small}"
echo ""

# Check if LLM server is reachable
echo -e "${YELLOW}Checking LLM server connection...${NC}"
BASE_URL="${LLM_BASE_URL:-http://host.docker.internal:11434/v1}"
# Remove /v1 suffix for health check
HEALTH_URL="${BASE_URL%/v1}"

if curl -s --connect-timeout 5 "${HEALTH_URL}/api/tags" > /dev/null 2>&1 || \
   curl -s --connect-timeout 5 "${BASE_URL}/models" > /dev/null 2>&1; then
    echo -e "${GREEN}LLM server is reachable!${NC}"
else
    echo -e "${RED}Warning: Cannot reach LLM server at ${BASE_URL}${NC}"
    echo -e "${YELLOW}Make sure your LLM server is running on the host machine.${NC}"
    echo ""
    echo "For Ollama:"
    echo "  ollama serve"
    echo ""
    echo "For LM Studio:"
    echo "  Start the local server in LM Studio"
    echo ""
fi

echo ""
echo -e "${GREEN}Usage:${NC}"
echo "  computor-agent chat                    # Interactive chat"
echo "  computor-agent ask 'your question'     # Single question"
echo "  computor-agent providers               # List providers"
echo ""

# Execute the command passed to docker run
exec "$@"
