# AC Agent-Assist Orchestrator Demo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A live voice call on `aetheriacc` where a custom Orchestration AI agent proactively surfaces member-specific backend data (current PCP, provider search, claim status) in the AI Agent panel and executes one approval-gated `change_pcp` write.

**Architecture:** Reuse the existing April-2026 stack (AgentCore gateway `centene-demo-gateway-kioqffwx7x` → Lambda `centene-demo-fulfillment`, MCP integration `centene-demo-mcp`, Customer Profiles domain, SCMedicaid KB). Build only: demo fixtures, an argument-based `member_id` path in the fulfillment Lambda, a session-data Lambda, a custom Orchestration AI prompt + AI agent with MCP tools attached, flow wiring, and a security-profile grant.

**Tech Stack:** AWS CLI (`connect`, `qconnect`, `lambda`, `customer-profiles`, `bedrock-agentcore-control`), Python 3.12 Lambdas, pytest.

## Global Constraints

- AWS profile `default` (account `441700732419`), region `us-east-1` for every command.
- Connect instance: `d232199a-e1f4-4d84-a77e-10f8bfc6468f` (ARN `arn:aws:connect:us-east-1:441700732419:instance/d232199a-e1f4-4d84-a77e-10f8bfc6468f`).
- Q assistant (instance-associated): `64d2c0aa-0a40-4c36-bef5-93cdb40b61da` (SC-Q-Assistant). Do NOT re-point the instance to a different assistant.
- Gateway: `centene-demo-gateway-kioqffwx7x`, target `KJHBUJTBLI`, Lambda `centene-demo-fulfillment`.
- Customer Profiles domain: `amazon-connect-aetheriacc`. SCMedicaid KB: `f06f3177-0e3e-4644-82ed-62e82a65a4af`. Demo DID: `+16084733991`.
- **Kurt's mutation-approval rule is satisfied by his approval of this plan** — each task states its AWS mutations up front; anything beyond the stated list needs fresh approval.
- Fail fast: no fallback data, no `or {}`, tools return explicit errors on unknown members.
- All work on branch `feature/orchestrator-demo-build`; PR + CodeRabbit review before Kurt's rehearsal calls.
- **REQUIRED INPUT before Task 3:** `KURT_CELL` — the E.164 number Kurt will call from (e.g. `+1608XXXXXXX`). Ask Kurt; do not guess.
- Demo member identity used throughout: `member_id 99999100001` (Maria Rodriguez, Medicaid, zip 29201).

---

### Task 1: Branch + vendor the deployed Lambda source into the repo

**Files:**
- Create: `backend/fulfillment/handler.py`, `backend/fulfillment/auth_handler.py`, `backend/fulfillment/fixtures/*.json` (copied from deployed zip)
- Create: `docs/superpowers/plans/2026-07-13-orchestrator-demo-build.md` (this file)

**Interfaces:**
- Produces: repo-tracked copy of the deployed Lambda — the source of truth for Tasks 2's edits.

- [ ] **Step 1: Create the branch**

```bash
cd /home/deltaprism/ACSFV/ac-orchestrator-demo && git checkout -b feature/orchestrator-demo-build
```

- [ ] **Step 2: Download and vendor the deployed code**

```bash
cd /home/deltaprism/ACSFV/ac-orchestrator-demo
curl -s -o /tmp/fulfillment.zip "$(aws lambda get-function --function-name centene-demo-fulfillment --region us-east-1 --query 'Code.Location' --output text)"
mkdir -p backend/fulfillment && unzip -o -q /tmp/fulfillment.zip -d backend/fulfillment
rm -rf backend/fulfillment/lambda_src   # empty artifact dir from old packaging
ls backend/fulfillment/fixtures/
```
Expected: `handler.py`, `auth_handler.py`, `fixtures/` with 8 JSON files (`members`, `claims`, `benefits`, `accumulators`, `providers`, `flex_cards`, `eobs`, `pcp_assignments`).

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "chore: vendor deployed centene-demo-fulfillment Lambda source and plan

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Demo fixtures + argument-based member_id in the fulfillment Lambda

**AWS mutations:** `aws lambda update-function-code` on `centene-demo-fulfillment` only.

**Files:**
- Modify: `backend/fulfillment/handler.py` (lambda_handler entry, ~line 399)
- Modify: `backend/fulfillment/fixtures/members.json`, `providers.json`, `claims.json`, `pcp_assignments.json`
- Test: `backend/tests/test_handler.py`

**Interfaces:**
- Consumes: vendored source from Task 1.
- Produces: tools callable with `arguments.member_id` (falling back to `session_attributes.member_id`); fixture guarantees — member `99999100001` has PCP "Dr. Elena Alvarez" (retiring), ≥2 Spanish-speaking in-network PCPs accepting new patients in zip 29201, and one denied claim with code `CO-197` (pre-auth missing).

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_handler.py
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "fulfillment"))
import handler

M = "99999100001"

def _call(tool, arguments):
    return handler.lambda_handler({"tool_name": tool, "arguments": arguments, "session_attributes": {}}, None)

def test_member_id_accepted_as_argument():
    r = _call("verify_eligibility", {"member_id": M})
    assert r["ok"] is True
    assert r["data"]["member"]["first_name"] == "Maria"

def test_missing_member_id_fails_fast():
    r = _call("verify_eligibility", {})
    assert r["ok"] is False and r["error_code"] == "not_authenticated"

def test_current_pcp_is_alvarez():
    r = _call("verify_eligibility", {"member_id": M})
    assert "Alvarez" in json.dumps(r["data"])

def test_spanish_pcp_search_finds_candidates():
    r = _call("search_provider_directory", {"member_id": M, "specialty": "Family Medicine", "language": "es", "zip": "29201"})
    assert r["ok"] is True
    hits = r["data"]["providers"]
    assert len(hits) >= 2
    assert all(p["accepting_new_patients"] and p["in_network"] and "es" in p["languages"] for p in hits)

def test_denied_claim_exists():
    r = _call("check_claim_status", {"member_id": M})
    assert any(c["status"] == "denied" and c.get("denial_code") == "CO-197" for c in r["data"]["claims"])

def test_change_pcp_roundtrip():
    r = _call("change_pcp", {"member_id": M, "new_pcp_name": "Sofia Herrera", "confirmed": True})
    assert r["ok"] is True
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
cd /home/deltaprism/ACSFV/ac-orchestrator-demo && python -m pytest backend/tests/ -v
```
Expected: FAILs (arg-based member_id not supported; fixtures lack Alvarez/Spanish providers/denied claim). If `search_provider_directory` has different arg names, read its function in `handler.py` first and adjust the test to the real signature — do not change the Lambda's public arg names.

- [ ] **Step 3: Implement**

In `handler.py` `lambda_handler` (~line 399), replace the session-only member check:

```python
    session = event.get("session_attributes") or {}
    if "member_id" not in session:
        member_id_arg = arguments.get("member_id")
        if not member_id_arg:
            return err("member_id is required (pass as tool argument or session attribute)", code="not_authenticated")
        session = dict(session, member_id=member_id_arg)
```

Fixture edits (adjust to actual JSON shapes seen in the files — the guarantees below are what matters):
- `pcp_assignments.json` (or wherever member 99999100001's PCP lives): current PCP = `{"npi": "1111119999", "name": "Elena Alvarez", "status": "retiring"}`.
- `providers.json`: add Dr. Alvarez (`accepting_new_patients: false`) plus two Spanish-speaking, in-network, accepting PCPs in zip 29201, e.g. `Sofia Herrera` (NPI `1111112222`) and `Carlos Mendez` (NPI `1111113333`), `"languages": ["en","es"]`.
- `claims.json`: add one denied claim for 99999100001: `{"claim_id":"CLM2026061800991","member_id":"99999100001","status":"denied","denial_code":"CO-197","denial_reason":"Precertification/authorization absent","provider_name":"Midlands Imaging","service_date":"2026-06-18","billed_amount":412.00}` (match surrounding field names).

- [ ] **Step 4: Run tests, verify pass**

```bash
python -m pytest backend/tests/ -v
```
Expected: all PASS.

- [ ] **Step 5: Deploy and verify live**

```bash
cd backend/fulfillment && zip -r /tmp/fulfillment-new.zip . -x "__pycache__/*" && cd ../..
aws lambda update-function-code --function-name centene-demo-fulfillment --zip-file fileb:///tmp/fulfillment-new.zip --region us-east-1 --query 'LastUpdateStatus'
aws lambda invoke --function-name centene-demo-fulfillment --region us-east-1 \
  --cli-binary-format raw-in-base64-out \
  --payload '{"tool_name":"verify_eligibility","arguments":{"member_id":"99999100001"},"session_attributes":{}}' /dev/stdout
```
Expected: `{"ok": true, ...Maria...}`.

- [ ] **Step 6: Commit**

```bash
git add backend/ && git commit -m "feat: demo fixtures + argument-based member_id for agent-assist tools

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Seed Customer Profiles with the test caller

**AWS mutations:** `create-profile` (or `update-profile`) in domain `amazon-connect-aetheriacc`.

**Interfaces:**
- Consumes: `KURT_CELL` (ask Kurt first).
- Produces: profile whose `PhoneNumber = KURT_CELL` and `Attributes.memberId = 99999100001` — the flow (Task 6) reads this.

- [ ] **Step 1: Check for an existing profile on that number**

```bash
aws customer-profiles search-profiles --domain-name amazon-connect-aetheriacc --key-name _phone --values "$KURT_CELL" --region us-east-1 --query 'Items[].ProfileId'
```

- [ ] **Step 2: Create (or update if Step 1 found one)**

If Step 1 found an existing ProfileId, run `aws customer-profiles update-profile --profile-id <id> ...` with the same fields instead of create-profile.

```bash
aws customer-profiles create-profile --domain-name amazon-connect-aetheriacc --region us-east-1 \
  --first-name Maria --last-name Rodriguez --phone-number "$KURT_CELL" \
  --attributes '{"memberId":"99999100001","planName":"Generic Health Plus Medicaid","lob":"Medicaid","zip":"29201","language":"es"}'
```
Expected: a ProfileId.

- [ ] **Step 3: Verify searchable by phone**

Re-run Step 1; expected: exactly one ProfileId. Then `get-profile` and confirm `Attributes.memberId == "99999100001"`. No repo change to commit; record the ProfileId in the PR description notes file `docs/demo-runbook.md` started in Task 8.

---

### Task 4: KB articles (PCP-change policy + CO-197 denial explanation)

**AWS mutations:** `qconnect start-content-upload` + `create-content` ×2 in KB `f06f3177-0e3e-4644-82ed-62e82a65a4af`.

**Files:**
- Create: `kb/pcp-change-policy.html`, `kb/claim-denial-co197.html`

**Interfaces:**
- Produces: two searchable KB articles the orchestrator cites in beats 1 and 3.

- [ ] **Step 1: Author the two articles** (committed to repo)

`kb/pcp-change-policy.html`:
```html
<h1>Changing Your Primary Care Provider (PCP)</h1>
<p>Members may change their PCP at any time at no cost. Rules:</p>
<ul>
<li>The new PCP must be <strong>in-network</strong> for the member's plan and <strong>accepting new patients</strong>.</li>
<li>Changes requested on or before the 20th of the month take effect the <strong>1st of the following month</strong>; after the 20th, the 1st of the second following month.</li>
<li>If the current PCP is retiring or leaving the network, the change takes effect <strong>immediately</strong>.</li>
<li>A new member ID card is mailed automatically within 7–10 business days.</li>
</ul>
```

`kb/claim-denial-co197.html`:
```html
<h1>Claim Denial Code CO-197: Precertification/Authorization Absent</h1>
<p>CO-197 means the service required prior authorization and none was on file. Member is <strong>not liable</strong> when an in-network provider failed to obtain authorization. Next steps for agents:</p>
<ul>
<li>Confirm the servicing provider is in-network. If so, advise the member they should not pay the bill.</li>
<li>Open a claim reprocessing request; the provider may submit a retro-authorization within 60 days of the denial.</li>
</ul>
```

- [ ] **Step 2: Upload both**

For each file (shown for the first; repeat for the second with its name/title):
```bash
KB=f06f3177-0e3e-4644-82ed-62e82a65a4af
UP=$(aws qconnect start-content-upload --knowledge-base-id $KB --content-type text/html --region us-east-1)
curl -s -X PUT -H "Content-Type: text/html" --upload-file kb/pcp-change-policy.html "$(echo $UP | jq -r .url)" -H "$(echo $UP | jq -r '.headersToInclude | to_entries[] | .key+": "+.value' | head -1)"
aws qconnect create-content --knowledge-base-id $KB --name pcp-change-policy --title "Changing Your Primary Care Provider (PCP)" --upload-id "$(echo $UP | jq -r .uploadId)" --region us-east-1 --query 'content.status'
```
Expected: status `CREATE_IN_PROGRESS` → verify `ACTIVE` with `list-contents`. If the KB is MANAGED and rejects `create-content`, fall back to the Connect admin UI (Kurt: Knowledge → Add content) — flag it, don't improvise another API.

- [ ] **Step 3: Verify retrievable + commit**

```bash
aws qconnect search-content --knowledge-base-id $KB --search-expression '{"filters":[{"field":"NAME","operator":"EQUALS","value":"pcp-change-policy"}]}' --region us-east-1 --query 'contentSummaries[].status'
git add kb/ && git commit -m "feat: KB articles for PCP-change policy and CO-197 denial

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Orchestration AI prompt + AI agent with MCP tools

**AWS mutations:** `qconnect create-ai-prompt`, `create-ai-prompt-version`, `create-ai-agent`, `create-ai-agent-version`, `update-assistant-ai-agent` (assistant `64d2c0aa`, ORCHESTRATION slot only).

**Files:**
- Create: `orchestrator/orchestration-prompt.yaml`, `orchestrator/ai-agent-config.json`, `orchestrator/deploy.sh`

**Interfaces:**
- Consumes: tool behavior from Task 2 (tools take `member_id` argument), KB articles from Task 4.
- Produces: the assistant's ORCHESTRATION slot runs our agent; `orchestrator/deploy.sh` re-publishes prompt+agent versions — this is the tuning loop used in Task 8.

- [ ] **Step 1: Write the prompt** (`orchestrator/orchestration-prompt.yaml`)

```yaml
anthropic_version: bedrock-2023-05-31
system: |
  You are a real-time co-pilot for a HUMAN customer-service agent at a health plan.
  You listen to the live call transcript and proactively surface member-specific data
  so the human agent never has to search. You NEVER speak to the member; everything
  you produce is for the human agent's panel.

  The caller was identified before the call reached the agent:
  <member_id>{{$.Custom.memberId}}</member_id>
  If member_id is empty, say so once and only answer from the knowledge base.

  Rules:
  - Always pass member_id as the member_id argument on every tool call.
  - Act on conversation beats WITHOUT being asked:
    * Member mentions their doctor leaving/retiring or wanting a new doctor ->
      call verify_eligibility to show current PCP and plan, and summarize the
      PCP-change policy from the knowledge base (effective dates, in-network rule).
    * Member states location/language/gender preferences for a doctor ->
      call search_provider_directory with those filters plus the member's zip;
      present up to 3 candidates: name, practice, distance, languages, accepting-new status.
    * Member mentions a bill, denied claim, or EOB -> call check_claim_status;
      if a claim is denied, explain the denial code in plain language using the
      knowledge base and state whether the member is liable.
    * Member chooses a specific new doctor -> propose change_pcp with that
      provider. Do NOT execute it without the human agent's confirmation.
  - Be terse: the agent is on a live call. Lead with the data, one short takeaway line.
  - Never invent member data. If a tool returns an error, show the error to the agent.
messages:
  - role: user
    content: |
      Live conversation so far:
      <conversation>
      {{$.transcript}}
      </conversation>
      Based on the newest customer turn, decide whether to call a tool, answer, or stay silent.
```

- [ ] **Step 2: Write the agent config** (`orchestrator/ai-agent-config.json`) — `PROMPT_ID` placeholder is substituted by deploy.sh

```json
{
  "orchestrationAIAgentConfiguration": {
    "orchestrationAIPromptId": "PROMPT_ID",
    "connectInstanceArn": "arn:aws:connect:us-east-1:441700732419:instance/d232199a-e1f4-4d84-a77e-10f8bfc6468f",
    "locale": "en_US",
    "toolConfigurations": [
      {"toolName": "verify_eligibility", "toolType": "MODEL_CONTEXT_PROTOCOL",
       "instruction": {"instruction": "Use when the member's coverage, plan, or current PCP is relevant. Always pass member_id."}},
      {"toolName": "search_provider_directory", "toolType": "MODEL_CONTEXT_PROTOCOL",
       "instruction": {"instruction": "Use when the member wants to find or switch to a provider. Filter by the member's zip and any stated language/gender/specialty preferences. Always pass member_id."}},
      {"toolName": "check_claim_status", "toolType": "MODEL_CONTEXT_PROTOCOL",
       "instruction": {"instruction": "Use when the member mentions a bill, claim, or EOB. Always pass member_id."}},
      {"toolName": "change_pcp", "toolType": "MODEL_CONTEXT_PROTOCOL",
       "instruction": {"instruction": "Propose only after the member has chosen a specific provider. Always pass member_id."},
       "annotations": {"destructiveHint": true},
       "userInteractionConfiguration": {"isUserConfirmationRequired": true}}
    ]
  }
}
```

- [ ] **Step 3: Write `orchestrator/deploy.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
ASSISTANT=64d2c0aa-0a40-4c36-bef5-93cdb40b61da
REGION=us-east-1
DIR="$(dirname "$0")"

PROMPT_ID=$(aws qconnect create-ai-prompt --assistant-id $ASSISTANT --region $REGION \
  --name centene-agent-assist-orchestration --type ORCHESTRATION --visibility-status PUBLISHED \
  --api-format ANTHROPIC_CLAUDE_MESSAGES --template-type TEXT --model-id anthropic.claude-3-5-sonnet-20241022-v2:0 \
  --template-configuration "{\"textFullAIPromptEditTemplateConfiguration\":{\"text\":$(jq -Rs . < "$DIR/orchestration-prompt.yaml")}}" \
  --query 'aiPrompt.aiPromptId' --output text)
PV=$(aws qconnect create-ai-prompt-version --assistant-id $ASSISTANT --ai-prompt-id "$PROMPT_ID" --region $REGION --query 'versionNumber' --output text)

CONFIG=$(sed "s/PROMPT_ID/${PROMPT_ID}:${PV}/" "$DIR/ai-agent-config.json")
AGENT_ID=$(aws qconnect create-ai-agent --assistant-id $ASSISTANT --region $REGION \
  --name centene-agent-assist-orchestrator --type ORCHESTRATION --visibility-status PUBLISHED \
  --configuration "$CONFIG" --query 'aiAgent.aiAgentId' --output text)
AV=$(aws qconnect create-ai-agent-version --assistant-id $ASSISTANT --ai-agent-id "$AGENT_ID" --region $REGION --query 'versionNumber' --output text)

aws qconnect update-assistant-ai-agent --assistant-id $ASSISTANT --region $REGION \
  --ai-agent-type ORCHESTRATION --configuration "{\"aiAgentId\":\"${AGENT_ID}:${AV}\"}"
echo "Deployed orchestrator ${AGENT_ID}:${AV} with prompt ${PROMPT_ID}:${PV}"
```
Note: parameter names above (`--api-format`, `--template-configuration`, tool config keys) must be validated against `aws qconnect create-ai-prompt help` and the `create-ai-agent` skeleton before first run; fix the script to the real shapes, don't force it. If `toolConfigurations` requires `toolId`, list tool IDs from the MCP integration (`aws qconnect list-*` / gateway target `KJHBUJTBLI`) and add them.

- [ ] **Step 4: Run and verify**

```bash
bash orchestrator/deploy.sh
aws qconnect get-assistant --assistant-id 64d2c0aa-0a40-4c36-bef5-93cdb40b61da --region us-east-1 | jq '.assistant.aiAgentConfiguration.ORCHESTRATION'
```
Expected: our agent id (not `66a1efe5...`). If tool attachment is rejected by the API, stop and hand Kurt the exact console path (Connect admin → AI agent designer → AI agents → our agent → Tools) — do not silently ship without tools.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/ && git commit -m "feat: custom orchestration AI prompt + agent with MCP tools

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Session-data Lambda (memberId → Q session)

**AWS mutations:** `lambda create-function` (`centene-demo-session-data`), IAM role `centene-demo-session-data-role`, `aws connect associate-lambda-function`.

**Files:**
- Create: `backend/session-data/handler.py`
- Test: `backend/tests/test_session_data.py`

**Interfaces:**
- Consumes: contact attribute `memberId` (set by the flow from the Customer Profiles lookup, Task 7).
- Produces: Q session for the contact carries `{"key":"memberId"}` so `{{$.Custom.memberId}}` interpolates in the prompt.

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_session_data.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "session-data"))
from handler import parse_session_arn

def test_parse_session_arn():
    arn = "arn:aws:wisdom:us-east-1:441700732419:session/64d2c0aa-0a40-4c36-bef5-93cdb40b61da/11111111-2222-3333-4444-555555555555"
    assert parse_session_arn(arn) == ("64d2c0aa-0a40-4c36-bef5-93cdb40b61da", "11111111-2222-3333-4444-555555555555")

def test_parse_session_arn_rejects_garbage():
    import pytest
    with pytest.raises(ValueError):
        parse_session_arn("not-an-arn")
```

- [ ] **Step 2: Run, expect FAIL** — `python -m pytest backend/tests/test_session_data.py -v` → import error.

- [ ] **Step 3: Implement** (`backend/session-data/handler.py`)

```python
"""Flow Lambda: push memberId contact attribute into the contact's Q in Connect session.

Placed AFTER the Connect assistant block in the inbound flow. Fails loudly:
a missing memberId or session means the flow is miswired — surface it, don't mask it.
"""
import logging
import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)
connect = boto3.client("connect")
qconnect = boto3.client("qconnect")

INSTANCE_ID = "d232199a-e1f4-4d84-a77e-10f8bfc6468f"


def parse_session_arn(arn: str):
    parts = arn.split(":session/")
    if len(parts) != 2 or "/" not in parts[1]:
        raise ValueError(f"unexpected Wisdom session ARN: {arn}")
    assistant_id, session_id = parts[1].split("/", 1)
    return assistant_id, session_id


def lambda_handler(event, context):
    details = event["Details"]
    contact_id = details["ContactData"]["ContactId"]
    member_id = details["Parameters"].get("memberId") or details["ContactData"]["Attributes"].get("memberId")
    if not member_id:
        raise ValueError("memberId missing: profile lookup did not run or found no match")

    contact = connect.describe_contact(InstanceId=INSTANCE_ID, ContactId=contact_id)["Contact"]
    session_arn = contact["WisdomInfo"]["SessionArn"]
    assistant_id, session_id = parse_session_arn(session_arn)

    qconnect.update_session_data(
        assistantId=assistant_id, sessionId=session_id,
        data=[{"key": "memberId", "value": {"stringValue": member_id}}],
    )
    logger.info("memberId=%s pushed to session %s", member_id, session_id)
    return {"status": "ok", "memberId": member_id}
```

- [ ] **Step 4: Run tests, expect PASS** — `python -m pytest backend/tests/test_session_data.py -v`

- [ ] **Step 5: Deploy**

```bash
ROLE=$(aws iam create-role --role-name centene-demo-session-data-role \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' \
  --query 'Role.Arn' --output text)
aws iam attach-role-policy --role-name centene-demo-session-data-role --policy-arn arn:aws:iam::aws:policies/service-role/AWSLambdaBasicExecutionRole 2>/dev/null || \
aws iam attach-role-policy --role-name centene-demo-session-data-role --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam put-role-policy --role-name centene-demo-session-data-role --policy-name qconnect-session \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["connect:DescribeContact","wisdom:UpdateSessionData","wisdom:GetSession"],"Resource":"*"}]}'
sleep 10
cd backend/session-data && zip -q /tmp/session-data.zip handler.py && cd ../..
aws lambda create-function --function-name centene-demo-session-data --runtime python3.12 \
  --handler handler.lambda_handler --role "$ROLE" --zip-file fileb:///tmp/session-data.zip \
  --timeout 10 --region us-east-1 --query 'State'
aws connect associate-lambda-function --instance-id d232199a-e1f4-4d84-a77e-10f8bfc6468f \
  --function-arn arn:aws:lambda:us-east-1:441700732419:function:centene-demo-session-data --region us-east-1
```
Expected: function Active; association succeeds (this also adds the Connect invoke permission).

- [ ] **Step 6: Commit**

```bash
git add backend/session-data backend/tests/test_session_data.py && git commit -m "feat: session-data Lambda pushes memberId into Q session

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Agent-assist inbound flow + phone number

**AWS mutations:** `connect create-contact-flow`, `connect update-phone-number` (point `+16084733991` at the new flow).

**Files:**
- Create: `flows/agent-assist-inbound.json`, `flows/export-reference.sh`

**Interfaces:**
- Consumes: session-data Lambda (Task 6), Customer Profiles domain (Task 3).
- Produces: calling `+16084733991` runs: profile lookup by ANI → set `memberId` contact attribute → Connect assistant block → session-data Lambda → queue to Kurt's agent.

- [ ] **Step 1: Export references** — read before writing; the existing flow shows the exact block JSON this instance uses.

```bash
aws connect describe-contact-flow --instance-id d232199a-e1f4-4d84-a77e-10f8bfc6468f \
  --contact-flow-id 5879312c-f1c4-4d35-a62e-55f8bdc8d3a1 --region us-east-1 --query 'ContactFlow.Content' --output text | jq . > flows/reference-centene-demo-flow.json
jq '[.Actions[].Type]' flows/reference-centene-demo-flow.json
```
Expected: action types including the assistant/Wisdom block (`CreateWisdomSession` or `UpdateWisdomAssistant`) and Customer Profiles (`GetCustomerProfile`/`UpdateContactAttributes`) to copy verbatim into our flow.

- [ ] **Step 2: Author `flows/agent-assist-inbound.json`** using the reference's exact block schemas, sequence: GetCustomerProfile(by `$.CustomerEndpoint.Address`) → UpdateContactAttributes(`memberId` from profile attribute) → Wisdom/assistant block (assistant `64d2c0aa...`) → InvokeLambdaFunction (`centene-demo-session-data`) → SetWorkingQueue(BasicQueue) → TransferContactToQueue. Error branches: any failure → PlayPrompt "Demo flow error: <step>" then Disconnect (loud failure, no silent fallthrough).

- [ ] **Step 3: Create and wire**

```bash
aws connect create-contact-flow --instance-id d232199a-e1f4-4d84-a77e-10f8bfc6468f \
  --name centene-agent-assist-inbound --type CONTACT_FLOW \
  --content file://flows/agent-assist-inbound.json --region us-east-1 --query 'ContactFlowId'
PN_ID=$(aws connect list-phone-numbers-v2 --instance-id arn:aws:connect:us-east-1:441700732419:instance/d232199a-e1f4-4d84-a77e-10f8bfc6468f --region us-east-1 --query "ListPhoneNumbersSummaryList[?PhoneNumber=='+16084733991'].PhoneNumberId" --output text)
aws connect update-phone-number ... # associate PN_ID with the new flow via associate-phone-number-contact-flow
aws connect associate-phone-number-contact-flow --phone-number-id "$PN_ID" --instance-id d232199a-e1f4-4d84-a77e-10f8bfc6468f --contact-flow-id <NEW_FLOW_ID> --region us-east-1
```
Note: check whether `+16084733991` currently routes to a flow another demo depends on (`describe-phone-number`); if so, ask Kurt before re-pointing.

- [ ] **Step 4: Verify wiring end-to-end (Kurt calls)** — Kurt calls `+16084733991` from `KURT_CELL`, accepts in Agent Workspace. Verify without eyes-on-panel:

```bash
aws logs tail /aws/lambda/centene-demo-session-data --region us-east-1 --since 10m
```
Expected: `memberId=99999100001 pushed to session ...`.

- [ ] **Step 5: Commit**

```bash
git add flows/ && git commit -m "feat: agent-assist inbound flow with profile lookup and session data

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Security profile grant + demo runbook + rehearsal loop

**AWS mutations:** `connect update-security-profile` (Kurt's agent profile: add `centene-demo-mcp` application/tools).

**Files:**
- Create: `docs/demo-runbook.md` (call sheet + resource IDs; this is allowed — it's the repo README/runbook, not a status doc)

**Interfaces:**
- Consumes: everything above.
- Produces: demo-ready system + scripted call sheet; tuning loop = edit `orchestrator/orchestration-prompt.yaml` → `bash orchestrator/deploy.sh` → Kurt re-calls.

- [ ] **Step 1: Grant tools** — find Kurt's security profile (`list-security-profiles`, the one on his agent user via `describe-user`), then:

```bash
aws connect update-security-profile --instance-id d232199a-e1f4-4d84-a77e-10f8bfc6468f \
  --security-profile-id <KURT_PROFILE_ID> --region us-east-1 \
  --applications '[{"Namespace":"centene-demo-gateway-kioqffwx7x","ApplicationPermissions":["ACCESS"]}]'
```
CAUTION: `--applications` REPLACES the list — first `describe-security-profile` and include all existing applications (e.g. Pega Claims, Salesforce) in the new list. If tool-level grants aren't expressible here, hand Kurt the console path (Users → Security profiles → profile → Agent applications / AI tools).

- [ ] **Step 2: Write `docs/demo-runbook.md`** — all resource IDs created, the call sheet with exact member lines per beat:

1. "Hi — I got a letter that my doctor, Dr. Alvarez, is retiring. I need a new primary care doctor." → panel: current PCP + policy (immediate effective date — retiring provider).
2. "Somewhere near downtown Columbia, and honestly I'd prefer someone who speaks Spanish." → panel: Herrera + Mendez cards.
3. "Oh, and one more thing — I got a bill for $400 from an imaging place, I thought that was covered?" → panel: CO-197 denied claim, member not liable.
4. "Let's go with Dr. Herrera." → panel: change_pcp proposal → agent clicks Approve.
5. Agent: Generate Notes.

- [ ] **Step 3: Rehearsal + tuning loop (with Kurt)** — Kurt calls and reads the sheet; after each call check `aws logs tail /aws/lambda/centene-demo-fulfillment --since 10m` for the expected tool invocations in order. Beats that didn't fire → sharpen that rule in the prompt YAML → `bash orchestrator/deploy.sh` → repeat. Exit when all 5 beats fire on two consecutive calls.

- [ ] **Step 4: Commit runbook**

```bash
git add docs/demo-runbook.md && git commit -m "docs: demo runbook and rehearsal call sheet

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: PR + CodeRabbit + merge

- [ ] **Step 1: Push and open PR**

```bash
git push origin feature/orchestrator-demo-build
gh pr create --title "Agent-assist orchestrator demo build" --body "Implements docs/superpowers/plans/2026-07-13-orchestrator-demo-build.md: demo fixtures + arg-based member_id, session-data Lambda, orchestration AI prompt/agent with MCP tools, inbound flow, KB articles, runbook.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

- [ ] **Step 2: Watch CodeRabbit** — `gh pr checks --watch` (background); address ALL feedback (security/correctness first), push fixes.

- [ ] **Step 3: Merge after clean review** — `gh pr merge --squash`.

---

## Self-review notes

- Spec coverage: mock backend (T1–2), profiles/ANI (T3), KB (T4), orchestrator+tools+approval gate (T5), session plumbing (T6), flow (T7), security profile + rehearsal/call-sheet resilience (T8), success criterion exercised in T8 Step 3.
- Known API-shape risks are flagged inline where they occur (T4 Step 2 managed-KB upload, T5 Step 3 prompt/agent parameter names, T7 Step 3 phone-flow association, T8 Step 1 applications replace-not-append) with explicit stop-and-ask fallbacks rather than improvisation.
- `KURT_CELL` is the single external input; requested before Task 3.
