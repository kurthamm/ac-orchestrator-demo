# AC Agent-Assist Orchestrator Demo — Design

**Date:** 2026-07-13
**Goal:** A killer Amazon Connect demo for Centene: a Connect AI agent (Orchestration type) listens to a live member-services call and **dynamically surfaces member-specific backend data** in the AI Agent panel — same zero-effort experience as Wisdom KB recommendations, but with live data and an approval-gated action.
**Instance:** `aetheriacc.my.connect.aws` (account 441700732419, us-east-1, `default` AWS profile).

## Demo narrative (what the audience sees)

The human agent takes a voice call and **does nothing but talk**. The AI Agent panel reacts beat by beat:

1. Member: "Dr. Alvarez retired, I need a new doctor" → panel proactively shows the member's **current PCP** (from mock backend) + the **KB policy** on PCP changes (effective 1st of next month; must be in-network, accepting new patients).
2. Member: "...near me, someone who speaks Spanish" → panel shows **3 in-network PCP candidates** filtered by the member's zip (known from profile) + language.
3. Member: "Also, why did I get a bill from my last visit?" → panel pivots unprompted to a **claim-status card** (adjudication/denial code from backend) + KB explanation of that code.
4. Member picks a doctor → orchestrator proposes **`update_pcp`** as an action card. The agent's only click of the demo: **Approve**. Backend updates; panel confirms new PCP + effective date.
5. Wrap-up → agent triggers **Generate Notes**; AI summary lands in the contact record.

**Not a screen pop.** The ANI→profile→member ID chain is silent plumbing so the orchestrator's proactive tool calls are personalized. Identification happens in the IVR before the agent is ever connected.

## Architecture

```
Caller (known test number)
  │ ANI match
  ▼
Connect flow: Customer Profiles block → memberId contact attribute
  ├─ Connect assistant block (associates Q in Connect assistant/session)
  ├─ Lambda block → qconnect UpdateSessionData {memberId}
  ▼
Agent Workspace (human agent on call)
  ├─ Contact Lens real-time transcription → live transcript into AI session
  ▼
Custom Orchestration AI agent (Q in Connect)
  ├─ AI prompt: {{$.transcript}} + {{$.Custom.memberId}} → decides when to fire tools
  ├─ KB: PCP-change policy article, claim denial-code articles
  └─ MCP tools via Bedrock AgentCore Gateway → mock backend Lambda
        get_member(memberId)                      — current PCP, plan, zip, language
        find_providers(zip, language, network)    — in-network PCPs accepting new patients
        get_claims(memberId)                      — recent claims with status/denial code
        update_pcp(memberId, providerId)          — WRITE, approval-gated in panel
  ▼
AI Agent panel: cards render dynamically; write actions require agent Approve
```

## Components to build

1. **Mock member backend** — one Lambda (Python or Node) with an in-memory/DynamoDB-seeded dataset: 1–2 members (keyed to Kurt's test phone numbers), a provider directory (~10 PCPs with zip/language/accepting-new flags), 2–3 claims (one with a denial code). Four operations matching the tools above. Fail fast on unknown member IDs — no fallback data.
2. **AgentCore Gateway** (Bedrock AgentCore, us-east-1) — Lambda target with JSON tool schemas; Discovery URL = `https://aetheriacc.my.connect.aws/.well-known/openid-configuration`. Constraint: one gateway ↔ one Connect instance ↔ one MCP-server integration.
3. **Connect MCP-server integration** — register the gateway in the Connect console (Integration type: MCP server); grant tools via security profile.
4. **Knowledge base** — small KB with: "How to change your PCP" (policy rules) and "Understanding claim denial codes" (covering the seeded code).
5. **Customer Profiles** — profile for the test member with phone number = Kurt's test caller ANI, attributes incl. memberId, zip, language.
6. **Custom Orchestration AI agent** — AI prompt encoding the proactive behavior (when to call which tool, how to present results, always propose-not-execute for writes); guardrail optional for v1.
7. **Flow wiring** — inbound flow: Customer Profiles lookup → Connect assistant block → Lambda (DescribeContact → UpdateSessionData with memberId) → queue to agent. Enable: Connect AI agents, Contact Lens real-time (voice), NoteTaking.

## Prerequisite check (step 0)

Inventory `aetheriacc` before building: Q in Connect assistant existence, Contact Lens real-time availability, existing integrations, whether MCP-server integration type + Orchestration AI agent type are available in the account/region. Any gap here is a blocker to resolve first.

## Error handling / demo resilience

- Tools return explicit errors for unknown members — orchestrator prompt instructs the model to tell the agent what's missing rather than invent data.
- 30-second MCP tool timeout: mock backend responds in <1s, so not a factor, but tool code must not hang on bad input.
- Rehearsal risk: proactive triggering depends on transcript quality + prompt tuning. Plan a scripted call sheet (exact phrases for each beat) and tune the orchestration prompt against it before demo day.

## Out of scope (v1)

- Real Centene systems, PHI, or production data — all mock.
- Chat channel (voice only for the demo).
- The Pega-in-AC 3PA iframe work (separate effort, currently parked).
- Multi-language IVR, guardrail tuning, case/task integration.

## Success criteria

A live voice call on `aetheriacc` where all five demo beats occur with zero agent keyboard input except the single Approve click and the Generate Notes click, and the backend PCP value verifiably changes.
