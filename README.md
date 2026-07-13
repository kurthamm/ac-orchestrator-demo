# AC Agent-Assist Orchestrator Demo

Amazon Connect demo for Centene member services: a custom Orchestration AI agent (Q in Connect) listens to a live voice call via Contact Lens real-time transcription and dynamically surfaces member-specific backend data in the AI Agent panel — current PCP, in-network provider search, claim status — plus one approval-gated write action (`update_pcp`).

**Not a screen pop.** Caller identity flows silently (ANI → Customer Profiles → `UpdateSessionData` → `{{$.Custom.memberId}}` in the orchestration prompt) so every proactive tool call is already scoped to the caller. The human agent's only inputs are one Approve click and Generate Notes.

## Architecture

- **Connect instance:** `aetheriacc.my.connect.aws` (us-east-1)
- **Mock member backend:** Lambda with seeded member/provider/claims data
- **Tools:** `get_member`, `find_providers`, `get_claims`, `update_pcp` — exposed as MCP tools via a Bedrock AgentCore Gateway, registered as an MCP-server integration in Connect
- **Knowledge base:** PCP-change policy + claim denial-code articles
- **Flow:** Customer Profiles lookup → Connect assistant block → Lambda (`UpdateSessionData` with memberId) → queue

Full design: [docs/superpowers/specs/2026-07-13-ac-agent-assist-orchestrator-demo-design.md](docs/superpowers/specs/2026-07-13-ac-agent-assist-orchestrator-demo-design.md)

## Status

Spec approved. Next: instance inventory (step 0), then implementation plan.
