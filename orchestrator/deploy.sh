#!/usr/bin/env bash
set -euo pipefail

# Orchestrator tuning loop: update prompt and agent, then wire into session registration
# Usage: ./deploy.sh [--with-tools]

ASSISTANT=64d2c0aa-0a40-4c36-bef5-93cdb40b61da
AGENT_ID=62f706c6-f5e8-4580-ab7d-5d5669751376
PROMPT_ID=d1ca1e04-e772-4530-bba1-d401608c5542
REGION=us-east-1
DIR="$(dirname "$0")"

WITH_TOOLS=false
if [[ "${1:-}" == "--with-tools" ]]; then
  WITH_TOOLS=true
fi

# Verify that tuning-loop resources exist before mutations
echo "Verifying tuning-loop resources exist..."
if ! aws qconnect get-ai-prompt \
  --assistant-id "$ASSISTANT" \
  --ai-prompt-id "$PROMPT_ID" \
  --region "$REGION" \
  &>/dev/null; then
  echo "ERROR: AI prompt $PROMPT_ID not found in assistant $ASSISTANT" >&2
  echo "This script only UPDATES pre-existing tuning-loop resources." >&2
  exit 1
fi

if ! aws qconnect get-ai-agent \
  --assistant-id "$ASSISTANT" \
  --ai-agent-id "$AGENT_ID" \
  --region "$REGION" \
  &>/dev/null; then
  echo "ERROR: AI agent $AGENT_ID not found in assistant $ASSISTANT" >&2
  echo "This script only UPDATES pre-existing tuning-loop resources." >&2
  exit 1
fi

echo "✓ Resources verified"
echo ""

# (a) Update AI prompt
echo "Updating AI prompt $PROMPT_ID..."
PROMPT_TEXT=$(cat "$DIR/orchestration-prompt.yaml")

aws qconnect update-ai-prompt \
  --assistant-id "$ASSISTANT" \
  --ai-prompt-id "$PROMPT_ID" \
  --region "$REGION" \
  --template-configuration "{\"textFullAIPromptEditTemplateConfiguration\":{\"text\":$(echo -n "$PROMPT_TEXT" | jq -Rs .)}}" \
  --output text > /dev/null

# Create new prompt version
PV=$(aws qconnect create-ai-prompt-version \
  --assistant-id "$ASSISTANT" \
  --ai-prompt-id "$PROMPT_ID" \
  --region "$REGION" \
  --query 'versionNumber' \
  --output text)
echo "✓ Created prompt version: $PV"

# (b) Update AI agent
echo "Updating AI agent $AGENT_ID..."

# Determine which config to use
if [ "$WITH_TOOLS" = true ]; then
  CONFIG_FILE="$DIR/ai-agent-config.json"
else
  CONFIG_FILE="$DIR/ai-agent-config-no-tools.json"
fi

CONFIG=$(sed "s/PROMPT_ID/${PROMPT_ID}:${PV}/" "$CONFIG_FILE")

aws qconnect update-ai-agent \
  --assistant-id "$ASSISTANT" \
  --ai-agent-id "$AGENT_ID" \
  --region "$REGION" \
  --configuration "$CONFIG" \
  --output text > /dev/null

# Create new agent version
AV=$(aws qconnect create-ai-agent-version \
  --assistant-id "$ASSISTANT" \
  --ai-agent-id "$AGENT_ID" \
  --region "$REGION" \
  --query 'versionNumber' \
  --output text)
echo "✓ Created agent version: $AV"

# (c) Update Lambda environment with new agent version
echo "Updating Lambda environment with agent $AGENT_ID:$AV..."
aws lambda update-function-configuration \
  --function-name centene-demo-session-data \
  --environment "Variables={ORCHESTRATOR_AI_AGENT_ID=${AGENT_ID}:${AV}}" \
  --region us-east-1 \
  --output text > /dev/null
echo "✓ Lambda environment updated"

echo ""
echo "✓ Deployment complete:"
echo "  Orchestrator: ${AGENT_ID}:${AV}"
echo "  Prompt: ${PROMPT_ID}:${PV}"
if [ "$WITH_TOOLS" = true ]; then
  echo "  Tools: ENABLED (experimental)"
else
  echo "  Tools: disabled (knowledge base only)"
fi
