# Recipes

These recipes are practical MCP workflows for a GoHighLevel assistant. Each JSON file is structured so an MCP client can show the human-readable flow, inspect required inputs, and map each action to a tool call.

Use placeholders like `{{locationId}}`, `{{contactId}}`, and `{{startDate}}` as values supplied by the user, agent memory, or the host app.

## Available recipes

- `lead-intake-and-dedupe.json` - Search before creating a lead, then tag and task it.
- `book-appointment-from-lead.json` - Find a contact, check calendar availability, and book a confirmed appointment.
- `pipeline-follow-up.json` - Review open opportunities and create follow-up tasks for stale deals.
- `customer-follow-up.json` - Work the conversation inbox: find customers needing a reply, draft messages, and schedule follow-ups.
- `att-fiber-consented-drip.json` - AT&T fiber SMS drip to consented opt-ins only (single registered number, throttled, book + one follow-up). Never cold/DNC.
- `att-post-call-interested-sms.json` - Single recap text fired on hang-up of an answered call (Call Status = Completed, Duration > 0), with the current promos ($500 Visa, lines from $15/mo, iPhone 17 ~$4/mo). Consent = the live call; never no-answer/voicemail.
- `att-no-answer-callback-task.json` - No-answer dials (Call Status = No Answer, Duration 0) create a callback/door-knock task for the rep — never an SMS. Keeps non-pickups worked hard while staying off the cold-text/TCPA path.
- `lost-opportunity-recovery.json` - Find lost opportunities and enroll selected contacts in a recovery workflow.
- `weekly-ads-report.json` - Pull ad, attribution, funnel, and conversion data for a weekly summary.
- `form-submission-triage.json` - Review recent form submissions and surface uncontacted leads.
- `reputation-review-request.json` - Check review links, send review requests, and report request activity.
- `snapshot-rollout-audit.json` - Inspect snapshots and push status before a subaccount rollout.
- `agency-location-health-check.json` - Summarize location, user, pipeline, calendar, and dashboard health.

## Shape

Each recipe uses this shape:

```json
{
  "id": "stable-recipe-id",
  "title": "Human-readable title",
  "goal": "What the workflow accomplishes",
  "requiredInputs": ["locationId"],
  "steps": [
    {
      "id": "step-id",
      "description": "What this step does",
      "tool": "mcp_tool_name",
      "input": {
        "field": "{{placeholder}}"
      }
    }
  ],
  "confirmationPoints": ["Actions requiring user approval"],
  "output": "Expected final response"
}
```

Treat delete operations, outbound messages, workflow enrollment, appointment creation, and snapshot pushes as confirmation-gated actions.
