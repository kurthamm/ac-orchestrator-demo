#!/usr/bin/env bash
set -euo pipefail

ASSISTANT=64d2c0aa-0a40-4c36-bef5-93cdb40b61da
REGION=us-east-1
DIR="$(dirname "$0")"

# Get or create prompt
PROMPT_NAME="centene-agent-assist-orchestration"
EXISTING_PROMPT=$(aws qconnect list-ai-prompts \
  --assistant-id "$ASSISTANT" \
  --origin CUSTOMER \
  --region "$REGION" \
  --query "aiPromptSummaries[?name=='$PROMPT_NAME'].aiPromptId" \
  --output text 2>/dev/null || echo "")

if [ -n "$EXISTING_PROMPT" ]; then
  PROMPT_ID="$EXISTING_PROMPT"
  echo "Found existing prompt: $PROMPT_ID"
else
  PROMPT_ID=$(aws qconnect create-ai-prompt \
    --assistant-id "$ASSISTANT" \
    --region "$REGION" \
    --name "$PROMPT_NAME" \
    --type ORCHESTRATION \
    --visibility-status PUBLISHED \
    --api-format MESSAGES \
    --template-type TEXT \
    --model-id "us.anthropic.claude-sonnet-4-5-20250929-v1:0" \
    --template-configuration "{\"textFullAIPromptEditTemplateConfiguration\":{\"text\":$(jq -Rs . < "$DIR/orchestration-prompt.yaml")}}" \
    --query 'aiPrompt.aiPromptId' \
    --output text)
  echo "Created new prompt: $PROMPT_ID"
fi

# Create new prompt version
PV=$(aws qconnect create-ai-prompt-version \
  --assistant-id "$ASSISTANT" \
  --ai-prompt-id "$PROMPT_ID" \
  --region "$REGION" \
  --query 'versionNumber' \
  --output text)
echo "Created prompt version: $PV"

# Get or create agent
AGENT_NAME="centene-agent-assist-orchestrator"
EXISTING_AGENT=$(aws qconnect list-ai-agents \
  --assistant-id "$ASSISTANT" \
  --origin CUSTOMER \
  --region "$REGION" \
  --query "aiAgentSummaries[?name=='$AGENT_NAME'].aiAgentId" \
  --output text 2>/dev/null || echo "")

CONFIG=$(sed "s/PROMPT_ID/${PROMPT_ID}:${PV}/" "$DIR/ai-agent-config-no-tools.json")

if [ -n "$EXISTING_AGENT" ]; then
  AGENT_ID="$EXISTING_AGENT"
  echo "Found existing agent: $AGENT_ID"
else
  AGENT_ID=$(aws qconnect create-ai-agent \
    --assistant-id "$ASSISTANT" \
    --region "$REGION" \
    --name "$AGENT_NAME" \
    --type ORCHESTRATION \
    --visibility-status PUBLISHED \
    --configuration "$CONFIG" \
    --query 'aiAgent.aiAgentId' \
    --output text)
  echo "Created new agent: $AGENT_ID"
fi

# Create new agent version
AV=$(aws qconnect create-ai-agent-version \
  --assistant-id "$ASSISTANT" \
  --ai-agent-id "$AGENT_ID" \
  --region "$REGION" \
  --query 'versionNumber' \
  --output text)
echo "Created agent version: $AV"

# Update assistant orchestration slot
aws qconnect update-assistant-ai-agent \
  --assistant-id "$ASSISTANT" \
  --region "$REGION" \
  --ai-agent-type ORCHESTRATION \
  --configuration "{\"aiAgentId\":\"${AGENT_ID}:${AV}\"}" \
  --orchestrator-configuration-list "[{\"aiAgentId\":\"${AGENT_ID}:${AV}\",\"orchestratorUseCase\":\"Connect.AgentAssistance\"}]"

echo "✓ Deployed orchestrator ${AGENT_ID}:${AV} with prompt ${PROMPT_ID}:${PV}"
