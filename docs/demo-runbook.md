# AC Agent-Assist Orchestrator Demo Runbook

## Resource Inventory

**AWS Accounts**
- Account: 441700732419 (Personal AWS, us-east-1)
- Profile: `default`

**Connect Instance**
- Instance: `aetheriacc` (d232199a-e1f4-4d84-a77e-10f8bfc6468f)
- URL: https://aetheriacc.my.connect.aws

**Q in Connect (Wisdom)**
- Assistant: `64d2c0aa-0a40-4c36-bef5-93cdb40b61da`
- AI Prompt: `d1ca1e04-e772-4530-bba1-d401608c5542` (Orchestration)
- AI Agent: `62f706c6-f5e8-4580-ab7d-5d5669751376` (Orchestration type, published version :4+)
- Use Case: `Connect.AgentAssistance`

**Backend Lambdas**
- Profile Lookup: `centene-demo-profile-lookup` (ANI → Customer Profiles member ID lookup)
- Session Data: `centene-demo-session-data` (memberId → session contact attribute, orchestrator registration)
  - Role: `centene-demo-session-data-role`
  - IAM Policy: `qconnect-session` (allows: connect:DescribeContact, wisdom:UpdateSessionData, wisdom:GetSession, wisdom:UpdateSession)
  - Environment: `ORCHESTRATOR_AI_AGENT_ID=62f706c6-f5e8-4580-ab7d-5d5669751376:4`

**Connect Flow**
- Inbound: `ca9c3f9b-7024-40cf-a595-8a6fc8b7724e` (on DID +16084733991)
  - Triggers: Customer Profiles lookup → Connect assistant block → Session Data Lambda → Queue

**Member Data**
- Profile: `3ecab426f5fa441c9240d035eeafa57f` (in Customer Profiles)
- Phone: +18036060039
- Member ID: 99999100001

**Knowledge Base**
- Knowledge Base: `SCMedicaid`
- Articles (MANAGED KB, uploaded via Connect admin website):
  - `pcp-change-policy.html` — PCP change eligibility and process
  - `claim-denial-co197.html` — CO-197 denial reason (non-emergency services require referral)

**AgentCore Gateway**
- Gateway: `centene-aa-gw-22wohsfqqp` (CUSTOM_JWT)
- Discovery URL: Instance URL
- MCP App: `centene-agentassist-mcp` (ApplicationType MCP_SERVER)
  - ARN: arn:aws:appintegrations:us-east-1:441700732419:application/f7dccf84-daf9-4e23-a971-f3034f13cea6
  - Integration Association: d232199a-e1f4-4d84-a77e-10f8bfc6468f (on Connect instance)
  - Tools: verify_eligibility, search_provider_directory, check_claim_status, change_pcp

---

## Kurt's Console Checklist

**Before demo: Run this 4-step setup.**

### Step 1: Re-register MCP Gateway in Connect Console

**Why:** Tool discovery happens via console action; the API cannot trigger it.

1. Open AWS Console → Amazon Connect → Instances → aetheriacc → Third-party applications
2. Find `centene-agentassist-mcp` → Delete it
3. Create new: Click "+ Add" → Choose Integration type **MCP server**
4. Select gateway: `centene-aa-gw-22wohsfqqp`
5. Save
6. **Wait 1-2 min** for discovery to complete (no UI feedback; check Connect admin website)

### Step 2: Grant Tool Permissions

**Why:** Agents cannot call tools without security profile permission.

1. Open Connect admin website → Security profiles → **Agent** profile
2. Scroll to Application permissions → Find `centene-agentassist-mcp` → Grant access
3. Repeat for **Admin** profile
4. Save

### Step 3: Verify Tools Appear in AI Agent Designer

1. Connect admin website → AI agent designer → Select orchestrator agent `62f706c6...`
2. Check Tools tab → Verify all 4 tools appear:
   - verify_eligibility
   - search_provider_directory
   - check_claim_status
   - change_pcp
3. If tools don't appear: repeat Step 1 and wait longer

### Step 4: Confirm KB Articles Are Attached

1. Admin website → Knowledge → SCMedicaid
2. Verify both articles are listed:
   - PCP Change Policy
   - CO-197 Denial (non-emergency services)
3. If missing: upload via admin website (MANAGED KB, no API upload)

---

## Rehearsal Call Sheet

**Scenario:** Member calls with three questions. Agent uses orchestrator panel to find answers.

**Member Phone:** +18036060039  
**Member ID:** 99999100001  
**Expected PCP:** Dr. Alvarez (note: retired → current-PCP card shown)  
**Available Providers:** Herrera, Mendez (Spanish-speaking, downtown Columbia area)  
**Pending Claim:** $400 imaging bill → CO-197 denied (non-emergency requires referral)

### 5-Beat Flow

**1. Member introduces issue**
- **Member says:** "I need to talk to someone about my doctor. He retired, and I haven't seen anyone in a while."
- **Agent action:** Read the orchestrator panel
- **Expected panel card:** "Current PCP: Dr. Alvarez (member's existing data)"
- **Agent response:** "I can definitely help with that. Let me find you an available provider."

**2. Member requests Spanish-speaking provider**
- **Member says:** "Do you have anyone who speaks Spanish? I prefer to stay close to downtown Columbia."
- **Agent action:** Wait for panel to trigger provider search
- **Expected panel card:** "Recommended providers: Dr. Herrera (Spanish, downtown), Dr. Mendez (Spanish, midtown)"
- **Agent response:** "I found two providers who fit what you're looking for. How about Dr. Herrera?"

**3. Member mentions a bill**
- **Member says:** "Actually, before we switch doctors, can you explain this $400 bill I got? It's for an imaging scan."
- **Agent action:** Watch panel trigger claim lookup
- **Expected panel card:** "Claim status: CO-197 denied. Reason: Non-emergency services require a specialist referral."
- **Agent response (from KB):** "That imaging wasn't covered because it didn't have a referral from your doctor first. You'll need to ask for a referral next time."

**4. Member approves doctor change**
- **Member says:** "Okay, let's switch to Dr. Herrera."
- **Agent action:** Orchestrator shows approval card for `change_pcp`
- **Expected panel card:** "Change PCP to Dr. Herrera — [Approve] [Decline]"
- **Agent clicks:** Approve button
- **Expected result:** "PCP changed successfully"
- **Agent response:** "Done! Dr. Herrera is now your primary care doctor. You'll get a confirmation in the mail."

**5. Agent generates notes**
- **Agent action:** Click "Generate Notes" button
- **Expected result:** Panel displays auto-generated summary of call:
  - "Member changed PCP from Dr. Alvarez to Dr. Herrera"
  - "Discussed non-emergency imaging denial (CO-197)"
  - "Member prefers Spanish-speaking providers"
- **System:** Notes are saved to contact record

---

## Tuning Loop

**Goal:** Iterate on orchestrator prompt and agent behavior without full redeploy.

### Quick Iteration

1. **Edit prompt:**
   ```bash
   # Edit orchestrator/orchestration-prompt.yaml with new instructions
   vim orchestrator/orchestration-prompt.yaml
   ```

2. **Deploy:**
   ```bash
   # From repo root:
   cd orchestrator
   bash deploy.sh
   # Creates new prompt version + new agent version, updates Lambda env
   ```

3. **Test:**
   - Call member phone +18036060039 via Connect
   - Follow rehearsal call sheet
   - Watch panel for changes in orchestrator behavior
   - Check logs: `aws logs tail /aws/lambda/centene-demo-session-data --follow`

4. **Iterate:**
   - Repeat step 1–3 until satisfied

### With Tools (Once Upstream Unblocks)

```bash
cd orchestrator
bash deploy.sh --with-tools
```

This uses `ai-agent-config.json` (with tool calls) instead of `ai-agent-config-no-tools.json`.

---

## Troubleshooting

**Panel shows no cards:**
- Check Lambda logs: `aws logs tail /aws/lambda/centene-demo-session-data`
- Verify member ID reaches the session: Look for `memberId=99999100001 pushed to session`
- Verify orchestrator agent is registered: Look for `orchestrator agent 62f706c6...` in logs

**Tools don't appear in AI agent designer:**
- Step 1: Re-run console checklist Step 1 (delete + re-add MCP app)
- Wait 3–5 minutes
- Refresh browser

**Member lookup fails:**
- DID not routing to flow: Check Connect flow settings
- Profile lookup not finding member: Test with CLI: `aws customer-profiles get-profile --instance-id d232199a... --profile-id 3ecab426f5fa441c9240d035eeafa57f`

**Lambda environment not updating:**
- Check: `aws lambda get-function-configuration --function-name centene-demo-session-data | jq .Environment`
- Should show: `ORCHESTRATOR_AI_AGENT_ID=62f706c6-f5e8-4580-ab7d-5d5669751376:4` (or later version)
