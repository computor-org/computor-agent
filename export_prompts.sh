#!/bin/bash

# Export default prompts to ~/.computor/prompts

echo "Exporting default prompts to markdown files..."

source .venv/bin/activate

python -m computor_agent.tutor.prompts.export_defaults

echo ""
echo "Done! You can now:"
echo "1. Edit the prompt files in ~/.computor/prompts/"
echo "2. Run 'computor-agent tutor --dev' to test with hot reload"
echo "3. Changes to .md files will reload automatically"