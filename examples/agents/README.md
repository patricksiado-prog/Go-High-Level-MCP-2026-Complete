# Agent Starters

These starter prompts are meant for MCP clients that connect to this GoHighLevel server. They focus the assistant on safe tool use, useful CRM behavior, and confirmation before write-heavy actions.

## Templates

- `crm-assistant.md` - Contact lookup, notes, tags, tasks, and conversation context.
- `appointment-setter.md` - Calendar availability and appointment booking.
- `pipeline-manager.md` - Opportunity review, follow-up, and status hygiene.
- `ads-reporting-assistant.md` - Weekly/monthly ad and attribution summaries.
- `agency-ops-assistant.md` - Multi-location operational checks and setup support.

## Common guardrails

- Use read tools before write tools.
- Ask for missing IDs instead of guessing.
- Confirm before sending messages, booking appointments, enrolling workflows, deleting records, changing opportunity status, or pushing snapshots.
- Summarize tool results plainly and include record IDs that were changed.
- If a tool returns partial or ambiguous data, say what is missing and suggest the next tool call.
