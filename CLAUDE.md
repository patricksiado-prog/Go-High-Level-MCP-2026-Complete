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
- Workflow read/create/clone/toggle via busybee needs `GHL_FIREBASE_API_KEY` +
  `GHL_FIREBASE_REFRESH_TOKEN` (or `GHL_REFRESH_TOKEN`) in Railway env. **Update 2026-06-30:
  Command's creds are set → workflow builder WORKS** (read/build/clone/toggle automations live).
  **Frontline's Firebase refresh token is EXPIRED** (`INVALID_REFRESH_TOKEN`) → automations fail
  there until it's renewed + redeployed (Frontline `pit-`/reads/SMS are unaffected).

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

## 3. Phone / SMS setups (updated 2026-06-30)
- **Command** — **6** SMS-capable US local numbers, account `active`, default **+13466840331**
  ("Patrick's number"); also +13467886943, +13465212885, +13466840217, +13465982878, +12819035606.
- **Frontline** — **22** SMS-capable numbers (TX/AL/AZ/OK/LA/MS) + Voice-AI inbound on several;
  default now **+12283385872** ("Espeedy Biloxi"); includes Zack's 4 numbers.
- **A2P 10DLC: Patrick confirms registered / Approved on both.** Per-number `bundleSid` still reads
  `null`, but that's an LC Phone reseller quirk — trust the Trust Center, not the field.

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

## 11. AT&T dealer promo sheet (Knowledge+ NDSc + NDSb, captured 2026-06-08)
Source = `attknowledgeplus.com` (dealer portal, login-gated). All offers LTO; exact
eligibility/end dates + regional (DMA) limits live in the portal. This is the talk-track
reference for Patrick + Zack. NDSc = consumer/residential; NDSb = business.

### NDSc — Consumer
**Wireless:** Choice Switcher (Port-In) **$250 bill credits OR $250 reward card**; BYOD Port-In
**$360 or $180** bill credits; waived activation. Premium Trade-In (w/ eligible unlimited + trade):
iPhone up to **$1,100/$800/$500/$350** off; Galaxy Z Fold7 & S25 Ultra/+ up to **$1,100/$900/$500**;
Pixel up to **$1,250/$1,050/$500**; moto razr ultra up to **$1,320/$1,000/$500**. Tiered new-line
device offers $0–$25.99/mo by trade tier.
**Fiber (resi):** GIG speeds **−$30/mo ×12**; 300Mbps+ **−$15/mo ×12**; 1 GIG **$200** reward card;
5 GIG **$200** Visa; Hyperlocal 5 GIG **−$55/mo**, 1 GIG **−$45/mo**; Austin DMA 1 GIG −$40/mo &
5 GIG −$75/mo; Fort Myers 1 GIG+ −$25/mo. Upgrades: Copper→Fiber 1 GIG+ −$10/mo; Copper→Fiber
5 GIG+ **$100** reward card.
**Converged (bundle):** Wireless+Fiber/AIA discounts; Chicago DMA AIA −$5/mo ×12; 55+ FAN
Wireless+Fiber −$5/mo, Wireless+AIA −$31/mo; 55+ Plan Wireless+Fiber/AIA **−$20/mo per line**;
Hyperlocal (Lumos markets) **extra wireless line free**.

### NDSb — Business
**Channel-specific wireless (port-in/switcher credits):** Private Port-In **$250**; New Line
(non-port) **$180**; Port-In **$360**; BYOD Port-In **$600** (qualifying unlimited + BYOD
deactivation) — plus a $25 BYOD variant; waived activation.
**Business Fiber (ABF):** Tiered Reward Card **$500** (1/2/5 GIG) · **$400** (500M) · **$300**
(300M), new ABF 300Mbps+ — stacks with switcher + All-In-One + waived activation. ABF **Switcher
up to $750 Visa** (switch w/ prior-carrier ETF, ABF 300Mbps+, prior bill dated within 60 days of
install). ABF **Discount monthly price**: 1 GIG **$120/mo** · 500M **$90/mo** · 300M **$60/mo**.
Waived installation ($99). Austin DMA: 500M $100/mo · 1 GIG $120/mo.
**Internet Air (AIA-B) / Wireless Broadband (AWB):** AIA-B **$360** bill credits ($10/mo×36) · Free
5G Gateway ($274.99 credits) · Inseego FX4200 switcher **$863.35**; **AIA-B Switcher up to $750 Visa**
(ETF reimbursement — cannot also take ABF, 1 reward card/BAN). AWB: free Franklin A70 ($209.99) or
Netgear Nighthawk M7 Pro (up to $269.99) hotspot; NY AWB Premium −$40/mo; Inseego MiFi Pro M4 **$209.99**.
**Multi-product (the bundle money-play):**
- **All-In-One for Business (ABF):** save up to **$50/mo on Fiber** — credit by speed **$50/mo
  (1/2/5 GIG) · $40/mo (500M) · $30/mo (300M)** — **OR $30/mo on Wireless** (ABF + new CRU wireless
  BAN, ≥1 line on a qualifying plan). Must retain both services.
- **All-In-One for Business (AIA-B/AWB):** save **$20/mo** on **up to 6** AIA-B/AWB lines.
- **ABF + Phone for Business Bundle:** Unlimited North America **$15/mo per line (lines 1–6)**.
**Trade-in/tiered:** premium trade-in up to ~$1,100–$1,320; Smartphone Reimbursement Switcher
up to **$800 Visa**; tiered device offers $0–$99.99/mo; Next Up daily upgrade up to $500/$350 off.

## 12. Busybee usage & tool capabilities (verified 2026-06-08)
**Two busybees — same code, separate Railway deployments, one account each:**
- **Command** → `https://go-high-level-mcp-2026-complete-production-711a.up.railway.app/mcp`
  · location `xZj500PjsflIQg2j9f9D` (Patrick). Pipelines: AT&T Commercial, AT&T Leads.
- **Frontline** → `https://go-high-level-mcp-2026-complete-production-46d1.up.railway.app/mcp`
  · location `TXw28sw0Z2rI6tcCDhJY` (**Zack runs it**). Pipelines: AT&T Commercial, AT&T Leads, Recruiting.
- Add either in claude.ai → Connectors → Add custom connector (paste URL, leave auth blank).
  Connectors load **at session start** → open a fresh chat after adding/swapping. Each connector
  is pinned to ONE account; pick the right one for the account you mean to touch.

**How to talk to each one (connector routing):** each busybee is a separate MCP connector,
hard-wired to ONE account — you don't pass a `locationId`, you **pick the connector**, and that
chooses the account. Like two walkie-talkie channels: same voice, different account.
- **Command** → connector **`cmndconevtor`** (tools `mcp__cmndconevtor__*`) → account `xZj500PjsflIQg2j9f9D`.
- **Frontline** → connector **`ghl-frontline-connector`** (tools `mcp__ghl-frontline-connector__*`) → account `TXw28sw0Z2rI6tcCDhJY`.
- Send the **same** request down each connector and each answers for **its own** account
  (e.g. `get_pipelines` → Command returns 2 pipelines, Frontline returns 3 incl. Recruiting).
- **Match the connector to the account you mean** — a "Command" action sent on the Frontline
  connector lands in the wrong account. When unsure which is which, call `get_pipelines` and check
  the returned `locationId` (xZj…=Command, TXw…=Frontline). Connector display names can change when
  re-added, so verify by locationId, not by the name.
- Don't confuse these with: **`ghl_connect`** = GHL's official read-heavy connector (Frontline),
  and **`apibusybee`** = the unrelated BusyBee tasks/productivity app (not GHL at all).

**What works via the busybee (834 tools):**
- **Reads:** pipelines, contacts (`search_contacts` by name/phone/email), phone numbers
  (`list_active_numbers_by_location`), conversations (`get_conversation`), opportunities.
- **Writes:** create/`upsert_contact`, `add_contact_tags`, create/`update_opportunity`
  (move stage via `pipelineStageId`), `create_contact_note`, `send_sms` (needs `contactId` +
  `fromNumber`). Sends verified live from Command (+13466840331) and Frontline.
- Tags array must be a real array; if a tool returns "no fields", the connector is stale
  (redeploy / reload — see §1 inputSchema fix).

**What does NOT work via the busybee (use the GHL UI, or add creds):**
- **Workflows** (read/create/clone/toggle) — needs `GHL_FIREBASE_API_KEY` +
  `GHL_FIREBASE_REFRESH_TOKEN` (or `GHL_REFRESH_TOKEN`). **2026-06-30: Command WORKS** (creds set —
  read/build/clone/toggle automations via busybee). **Frontline DOWN** — Firebase refresh token
  expired (`INVALID_REFRESH_TOKEN`); renew it + redeploy to enable. Reads/contacts/SMS fine on both.
- **Smart-list create** (`POST /contacts/smart-lists`) → 404. Build smart lists in the UI.
- **Bulk tag** (`POST /contacts/tags/bulk`) → 404. Tag per-contact with `add_contact_tags`,
  or bulk in the UI / via CSV re-import.
- **Bulk contact import:** no endpoint. Use GHL's native **CSV Import** (matches by phone so no
  dupes; can apply a tag on the import screen).
- **get_location** → 401 on Command (token missing `locations.readonly`; cosmetic — reads/sends fine).

**Pull a lead batch:** filter Contacts by **Date Added** in the UI (e.g., an import day), or tag
the batch via a native CSV re-import (apply the tag on import), then filter by tag.

**AT&T promo reference:** consumer flyer pricing → §10; full dealer sheet (NDSc consumer + NDSb
business — fiber/wireless/converged/bundle, reward & bill credits, switcher) → §11. Ready-made
one-pagers in repo: `docs/consumer-fiber-promo-sheet.{md,html,pdf}` and
`docs/business-fiber-promo-sheet.pdf` (rebuild via `scripts/build_promo_pdf*.py`).

## 13. GoHighLevel (GHL / HighLevel) platform reference
**What it is:** all-in-one CRM/marketing SaaS. Hierarchy: **Agency (Company)** → **Sub-accounts
(Locations)**. Each Location = one business (Command and Frontline are two Locations). `locationId`
scopes nearly every API call.

**Access / tokens:**
- **Private Integration Token (`pit-`)** — per-location; what the busybee uses (pinned via
  `GHL_LOCATION_ID`). The busybee URL itself = full account access (no extra auth).
- **OAuth (v2 API)** — `services.leadconnectorhq.com`, header `Version: 2021-07-28`. Official GHL
  MCP = `services.leadconnectorhq.com/mcp` (read-heavy, ~22 tools).
- **Agency/Company token** — can span multiple sub-accounts, but only ones under the **same agency**.

**Core objects:**
- **Contacts** — leads/customers; name/email/phone, `additionalPhones/Emails`, **tags**,
  **custom fields**, **DND** (do-not-disturb per channel), source/attribution.
- **Opportunities** — a deal inside a **Pipeline → Stage**; has **status** (open/won/lost/abandoned)
  + `monetaryValue`. Move stage via `pipelineStageId`.
- **Pipelines & Stages** — e.g. Lead → Contacted → Closed/Won → Lost.
- **Conversations** — unified inbox: SMS, email, WhatsApp, FB/IG DM, calls; messages carry
  direction/type/status.
- **Calendars & Appointments** — booking, free/block slots, reminders.
- **Workflows** — v2 automation builder (triggers + actions). Legacy: **Campaigns** (drip) +
  **Triggers**.
- **Forms / Surveys / Funnels / Websites / Blogs** — capture + web.
- **Smart Lists** — saved contact filters/segments (show in the Contacts "All Contacts ▾" dropdown).
- **Custom Fields / Custom Values / Custom Objects** — data-model extensions.
- **Phone (LC Phone / Twilio)** — numbers, **A2P 10DLC** registration, number pools, call
  forwarding, IVR, voicemail.
- **Email (LC Email / Mailgun)** — templates, domains, campaigns.
- **Payments** — invoices, estimates, products, orders, subscriptions, POS.
- **Memberships/Courses, Communities, Reputation (reviews), Social Planner, Affiliates.**
- **SaaS mode / rebilling** — agencies resell GHL to sub-accounts.
- **Snapshots** — clone config (pipelines/workflows/funnels/calendars) between Locations.
  **Do NOT carry contacts** (that's why Command's pipelines moved but the leads didn't).

**A2P 10DLC:** US carriers require brand + campaign registration for business SMS or messages get
filtered. With the LC Phone reseller, it's managed in GHL/Trust Center; a per-number `bundleSid`
can read `null` even when the brand/campaign is **Approved** — trust the Trust Center, not the field.

**Mobile app (LeadConnector):** Dashboard · Conversations · **Dialer** · Contacts · Calendar ·
Pipelines · POS/Estimates/Invoices/Products. To dial a contact: open them → tap the phone icon
(routes through the location number). Saved Smart Lists live in the Contacts "All Contacts ▾" menu.

**This repo** = a custom GHL MCP server (834 tools) over the v2 API — see §12 for what's wired up
vs. the gaps.
