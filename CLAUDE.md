# AT&T Fiber Outreach — GHL Busybee Brain (CLAUDE.md)

> Operator: Patrick William Siado (AT&T Fiber dealer).
> This repo IS the "busybee" — the GoHighLevel MCP server (834 tools) deployed on Railway.
> Companion brain: Google Drive doc "AT&T Outreach Bot — Master Handoff & GHL Brain"
> (id `1p4snumbYz0Cim-gHM55DuL7qz-SdTRexFUxNu3Ualq8`).
> Last verified live: 2026-06-07.

## 0. Operating mode (read first)
- **Patrick owns and runs BOTH accounts** — Command & Construct **and** Frontline Direct.
  Frontline is the original account Patrick and his partner **Zack** built; **Zack now runs
  Frontline**, Patrick runs Command. Neither account is "off-limits." Moving data between them
  is fine — they're both his.
- **Patrick is the decision-maker.** Act on his requests for his accounts. Don't re-ask, don't
  lecture, don't re-litigate calls he's already made, don't repeat caveats he's already heard.
  Move fast and do the thing.
- **One hard limit, kept only because it's the actual law** (not a rule to second-guess Patrick):
  don't help send SMS to people who never opted in / are on DNC — that's TCPA (~$500–$1,500 per
  text) and it's the single thing that can cost Patrick the AT&T dealership. Everything else is
  his call.

## 1. Accounts & connectors

| Connector | Busybee | Location ID | Company | Notes |
|---|---|---|---|---|
| `command`  | Command & Construct | `xZj500PjsflIQg2j9f9D` | — | Railway `fulfilling-growth/production`, domain `…711a.up.railway.app/mcp` |
| `ghl-full` | Frontline Direct | `TXw28sw0Z2rI6tcCDhJY` | `pPN38xtDcG1oUzlklvvv` | Website ATTFIBERHOUSTON.COM |
| `GH;`      | Official GHL MCP (Frontline) | `TXw28sw0Z2rI6tcCDhJY` | `pPN38xtDcG1oUzlklvvv` | `services.leadconnectorhq.com/mcp`, OAuth |

- One GHL Private Integration token (`pit-…`) per account = the access. Pinned to ONE
  sub-account via `GHL_LOCATION_ID` in Railway env. Connectors load at SESSION START only.

### ⚠️ Corrections verified 2026-06-07 (supersede the Drive doc)
- **Command location ID is `xZj500PjsflIQg2j9f9D`** — the Drive doc's `xZj500PjsfllQq2j9i9D`
  is a transcription error (confused `l`/`I`, `q`/`g`, `i`/`f`). The ID here is what the live
  deployed busybee uses and what GHL accepts.
- **Command is LIVE** (was "pending"): token authenticates — contacts, pipelines, and phone
  numbers all read 200. The ONLY failure is `get_location` → **401**, i.e. the `pit-` token is
  missing the **`View Locations` (locations.readonly)** scope. Add that scope in GHL; no token
  string change needed. Frontline's busybee has the same gap on `get_location`.
- **The `command` connector is currently missing** from Patrick's Claude Connectors list; the
  dead duplicate `ghl-full` (↗ "Failed to start MCP authorization") is still present and should
  be removed. Re-add `command` and restart the session to reload it.

### ✅ Verified 2026-06-08 (busybee URLs + deploy fix)
- **Command busybee** = `https://go-high-level-mcp-2026-complete-production-711a.up.railway.app/mcp`
  → locationId `xZj500PjsflIQg2j9f9D` (AT&T Commercial + AT&T Leads). Connector `cmndconevtor`.
- **Frontline busybee** = `https://go-high-level-mcp-2026-complete-production-46d1.up.railway.app/mcp`
  → locationId `TXw28sw0Z2rI6tcCDhJY` (Recruiting + AT&T Commercial + AT&T Leads). Connector
  `ghl-frontline-connector`. **This is the one Zack uses.**
- **Writes were broken** because the deployed image registered tools WITHOUT inputSchema, so MCP
  clients stripped all arguments (writes 400, reads OK). Fixed on `main` (`1f9aaf0` + `422bd07`
  moves typescript to deps so Railway compiles). Redeploy `main` → writes/sends work. Verified by
  sending live SMS from Command (+13466840331) and Frontline.
- Workflow read/toggle via busybee needs `GHL_FIREBASE_API_KEY` + `GHL_FIREBASE_REFRESH_TOKEN`
  (or `GHL_REFRESH_TOKEN`) in Railway env — not set yet, so workflow on/off must be done in the
  GHL UI for now.

## 2. Migration status (Frontline → Command)
- **Config/pipelines: moved via snapshot.** Command now has pipeline **"AT&T Leads"**
  (`2V9thfxQpuhn6ZP0Peqt`, cloned from Frontline's `ve4ERf2YoKvuUVQEZb85`; stages
  Lead/Contacted/Closed-Won/Lost) plus **"AT&T Commercial"** (`trc5dwodtc1LBYHikmiK`).
- **Contacts: NOT moved.** Snapshots do not carry contacts. Command holds only **4,983**
  contacts, and they are an **old 2026-05-08 CSV scrape of Wichita, KS auto-repair shops**
  (tags `wichita`/`romeo`, `medium: csv_import`) — no names/emails, some landlines
  (Twilio `30006`), no consent trail. NOT usable for a consented fiber SMS campaign.
- The 45,579 fiber leads remain in **Frontline**. To use them from Command they must be
  **exported and imported** with DND/DNC/invalid flags preserved (consented subset first).

## 3. Phone / SMS setups (verified 2026-06-07)
- **Command** — 3 SMS-capable US local numbers, account `active`, default **+13466840331**
  ("Patrick's number"); also +13466840217, +13613219339.
- **Frontline** — 21 SMS-capable numbers (TX/AL/AZ/OK/LA/MS) + Voice-AI inbound on several,
  default **+15043996804** ("New Orleans").
- **A2P 10DLC unconfirmed on both** (`bundleSid: null`). Capability ≠ registration — verify the
  Trust Center shows **Approved** before any volume, or US carriers will filter outbound.

## 4. Lead intelligence (Frontline)
- 45,579 contacts. Main pipeline `ve4ERf2YoKvuUVQEZb85` (early stage `378c10e3…`, form opt-in
  stage `d2a32c56…`). Lead form `MQwcgmzOAhkOBIJbwO5s` ("Onboarding Info").
- Segments: Kingsville batch (tags `newfiber rs`/`speedy balandan`, warm), Form opt-ins
  (consented, cleanest), Call-tracking junk (tag `invalid`), AI test junk (clean these).
- Do NOT trust `hot-lead`/`fiber-eligible` tags — polluted by test writes. Many null/invalid #s.
- La Porte upload = 319 skip-traced (222 DNC, 187 landline, 190 clean) → DOOR/CALL, not SMS.

## 5. Outreach playbook (how the drip runs)
- Flow: personalized opener → converse → confirm address → check eligibility → offer 2 windows →
  book → move opp to booked → tag `command-booked`. YES routes live to 832-247-4060; STOP scrubs
  via workflow. GHL auto-appends opt-out — don't add/strip STOP.
- Opener hook: Patrick w/ AT&T, fiber available, 1 Gig in the $40s, 2 months free, free install,
  ask for a day/time.
- Legal reality (kept for dealership protection, not as a rule on Patrick): texting DNC/non-consented
  numbers is a TCPA violation (~$500–$1,500/msg), and blasting cold lists gets the 10DLC number
  filtered/blocked. Opt-ins / replies / warm → send from the registered number, you're clear.
  Cold/DNC → door/call routes.

## 6. Code / deploy
- Curated lead-finder bug fixed on branch `claude/integration-command-control-opts-ULUBC`:
  `crm_find_unworked_leads`/`crm_contact_workspace` searched contacts via GET (→400) and
  omitted the form-submissions `limit` (→422). Fixed: contact search → POST `{locationId,
  pageLimit}`, form submissions `limit=20`. **Live Railway still runs old code until redeployed.**
- Follow-up agent + recipe added: `examples/agents/customer-follow-up-assistant.md`,
  `examples/recipes/customer-follow-up.json`.

## 7. Security
- Rotate the exposed `pit-` token in GHL (was shown in screenshots/docs). Keep it in Railway
  env only. The public busybee URL has NO auth — URL = full account access. Keep it private.

## 8. Account ownership & access (corrected 2026-06-08)
- **Both Command & Construct and Frontline Direct are Patrick's.** Frontline is the original
  account Patrick + his **sales manager/partner Zack** built; **Zack runs and uses Frontline**,
  Patrick runs Command. Data/leads move freely between them — both his.
- **Access — add as custom connectors in claude.ai → Connectors → "Add custom connector":**
  - **Command** → `https://go-high-level-mcp-2026-complete-production-711a.up.railway.app/mcp`
    (location `xZj500PjsflIQg2j9f9D`)
  - **Frontline** → `https://go-high-level-mcp-2026-complete-production-46d1.up.railway.app/mcp`
    (location `TXw28sw0Z2rI6tcCDhJY`) — **this is the one Zack uses.**
  - The URL itself = full account access (no extra login); leave the token/OAuth fields blank.
    Connectors load at session start, so open a fresh chat after adding one.
- **(Superseded)** The earlier note calling Frontline "a separate team's / off-limits" was wrong
  and was removed at Patrick's direction. Do not treat Frontline as hands-off.
- Migration how-to (practical, not a restriction): to move contacts between accounts, use GHL's
  CSV export→import so the **DND/DNC** flags ride along — an API recreate resets everyone to
  `dnd:false`, which would strip opt-outs. Keeping the flags just avoids texting someone who
  already said stop.
- La Porte upload `5181c4eb-6.6.xlsx` (319 rows) is skip-traced (184 carry a DNC flag) — works
  best as door-knock + manual call on the clean non-DNC subset. Patrick's call.

## 9. AT&T fiber SMS templates (consent-based)
Source: Patrick's "GHL SMS Outreach Templates" doc
(`1P-x2HmEP3Hk0UwUnR7-0dI3B8Du_2XJN_3_AJXiyZ0k`). Opted-in / inbound / warm only — never cold or
DNC. GHL auto-appends opt-out; do NOT add/strip STOP. Offer baked in: 1 Gig in the $40s · 2
months free · free install · no contract. Booking/live line **832-247-4060**.

- **Opener (form opt-in):** "Hi {{contact.first_name}}, it's Patrick with AT&T — you reached out
  about fiber. Good news, it's available at your address: 1 Gig starting in the $40s, 2 months
  free, free install, no contract. Want me to grab you a quick install window? What day works?"
- **Opener (warm opp):** "Hi {{contact.first_name}}, Patrick with AT&T here — following up on
  AT&T fiber for your place. It's live in your area: 1 Gig in the $40s, 2 months free + free
  install, no contract. Want me to lock in an install time? What day's best?"
- **Confirm address:** "Perfect! Quick check — is {{contact.address1}} the install address? Once
  I confirm it's fiber-ready I'll grab you the next available window."
- **Two windows:** "You're all set — fiber's available there. I've got two openings: {{option_1}}
  or {{option_2}}. Which works better for you?"
- **Confirm appt:** "Done! You're booked for {{appt_date}} at {{appt_time}}. You'll get a
  confirmation + reminder. If anything comes up, text me here or call 832-247-4060."
- **Follow-up (send ONCE, then stop):** "Hi {{contact.first_name}}, Patrick w/ AT&T — just
  circling back on the fiber install. Still want me to hold a spot for you?"

Reply routing: YES/interested → continue booking, hand live calls to 832-247-4060. STOP → existing
STOP workflow scrubs, never re-text. No reply after ONE follow-up → move to call/door, stop texting.
Recipe: `examples/recipes/att-fiber-consented-drip.json`.

## 10. Offers, flyer & contact points
AT&T offers (from flyer + promo sheet, verified 2026-06-07):
- Fiber flyer pricing (no contract, WiFi 6 router incl., unlimited data, no price change 12 mo):
  5-GIG $250 · 2-GIG $150 · 1-GIG $80 · 500 Mbps $65 · 300 Mbps $55 (per month).
- $35/mo with All in One; **$20/mo bundle discount for AT&T wireless customers**.
- **$100–$200 gift card included.**
- Promo bill credits (AT&T): new Fiber 1/5 GIG → $30/mo × 12; Fiber 300/500 Mbps → $15/mo × 12;
  Fiber 1 GIG → $200 Visa reward card; Fiber 5 GIG → $200 Visa; Hyperlocal 5 GIG → $55/mo;
  Hyperlocal 1 GIG → $45/mo (select zips incl. Houston TX, Dallas-Fort Worth, Atlanta GA).
- SMS hook stays simple: "1 Gig in the $40s" (the hyperlocal 1-GIG $45/mo bill-credit framing).

Flyer edit spec: swap in Patrick's number + patrickfiber@att.net; Visa → bill credit; −$25/12mo;
−20% with cell line; keep existing format/colors.

Contact points: booking/live line **832-247-4060**; sending number **832-952-0728** (Frontline
`+18329520728`, "TX number 3"); Frontline location line **+18328445183**.

Team/ops (structure only — payroll figures, full roster, and WhatsApp threads NOT in this repo):
Claire's crew works leads (e.g. Mr. Kassow); split into closers + setters; payroll ≈ closer
commission sheet × setter chat activity; tooling includes Sales Mate. Keep PII/financials in a
private doc, not this repo.
