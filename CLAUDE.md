# AT&T Fiber Outreach — GHL Busybee Brain (CLAUDE.md)

> Operator: Patrick William Siado (AT&T Fiber dealer).
> This repo IS the "busybee" — the GoHighLevel MCP server (834 tools) deployed on Railway.
> Companion brain: Google Drive doc "AT&T Outreach Bot — Master Handoff & GHL Brain"
> (id `1p4snumbYz0Cim-gHM55DuL7qz-SdTRexFUxNu3Ualq8`).
> Last verified live: 2026-06-07.

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
- **A2P 10DLC registered on BOTH GHL platforms** (Command + Frontline) and **ALL individual sending
  numbers are A2P-approved** — confirmed by operator 2026-06-10 (supersedes the earlier `bundleSid:
  null` reading). Outbound from any of them is carrier-cleared, so volume won't be silently filtered.
- **⚠️ "All numbers approved" does NOT make number-rotation OK.** Using different approved numbers for
  *genuinely distinct* purposes is fine — local-presence by region, residential vs commercial, a rep's
  own line, separate brands/use-cases. But **rotating ONE campaign across many numbers to dilute
  per-number volume / dodge spam-filtering is SNOWSHOEING** and stays prohibited (§5). Each number
  being individually approved does **not** cure it — snowshoeing is a CTIA/carrier code-of-conduct
  violation + detection evasion *regardless of registration*, and it's exactly what gets 10DLC
  campaigns revoked and **risks the AT&T dealership.** Still applies: throttle, personalize, opt-out,
  warm/consented contacts only.

## 4. Lead intelligence (Frontline)
- 45,579 contacts. Main pipeline `ve4ERf2YoKvuUVQEZb85` (early stage `378c10e3…`, form opt-in
  stage `d2a32c56…`). Lead form `MQwcgmzOAhkOBIJbwO5s` ("Onboarding Info").
- Segments: Kingsville batch (tags `newfiber rs`/`speedy balandan`, warm), Form opt-ins
  (consented, cleanest), Call-tracking junk (tag `invalid`), AI test junk (clean these).
- Do NOT trust `hot-lead`/`fiber-eligible` tags — polluted by test writes. Many null/invalid #s.
- La Porte upload = 319 skip-traced (222 DNC, 187 landline, 190 clean) → DOOR/CALL, not SMS.

## 5. Outreach guardrails (must follow)
- Consented/opted-in/inbound contacts ONLY (forms, replies, YES). Skip dnd/null/invalid/DNC.
- Cold + DNC lists = door/call routes, never SMS blasts. No filter-evasion message variants.
- Personalized opener: Patrick w/ AT&T, fiber available, 1 Gig in the $40s, 2 months free,
  free install, ask for a day/time. GHL auto-appends opt-out — do not add/strip STOP.
- Converse → confirm address → check eligibility → offer 2 windows → book → move opp to booked
  → tag `command-booked`. YES routes live to 832-247-4060; STOP scrubs via workflow.
- TCPA: texting DNC/non-consented = $500–$1,500 per message. Throttle and log.
- **No number randomization / sender rotation to evade carrier filters (snowshoeing).** It is a
  10DLC + carrier-policy violation and detection evasion, and risks the AT&T dealership. Drips
  send from a single A2P-registered number to consented contacts only. Owning a list ≠ consent.

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

## 8. Operator context & account custody (added 2026-06-07; CORRECTED 2026-06-10)
- **⚠️ CUSTODY CORRECTION (owner-clarified 2026-06-10) — supersedes the "separate team / off-limits"
  framing.** **Both Command AND Frontline are Patrick's.** Frontline Direct is **Patrick's own company**
  (his "CO"); **Zack has been running it ~1 month** with his reps. Patrick works day-to-day out of
  **Command** mainly to keep separation from Zack's reps and avoid confusion — but that's an
  **operational preference, NOT an absolute custody wall.** Patrick **can use both accounts and move
  leads / insights / data between them whenever he wants.** Frontline is **NOT** off-limits. Standard §5
  guardrails (consented/warm, opt-out, single A2P-registered number, throttle, no snowshoeing) still
  apply on **either** account.
- *(Original 2026-06-07 note, DOWNGRADED to operational guidance, not a hard boundary:)* "Command is the
  day-to-day account; the Frontline 45,579 / recent opt-ins were kept off-limits to avoid stepping on
  Zack's reps." → Keep logically separate by default for clean ops, but they ARE Patrick's to use, pull
  from, and bring into Command when he wants.
- Patrick's legitimate audience = his **own** contacts (his prior data) plus anyone who opts in to
  **his** outreach going forward. Recent bulk/CSV/AI-test writes (Wichita auto shops, jeweler/
  realtor B2B scrape, call-tracking junk) are not consented opt-ins regardless of who loaded them.
- **La Porte upload `5181c4eb-6.6.xlsx` (319 rows): SKIP-TRACED, not opt-in.** 184/319 carry a
  DO NOT CALL flag; 135 are clean wireless / non-DNC; every row has at least one wireless line.
  Route = DOOR-KNOCK + manual CALL on the clean non-DNC subset. **Never an SMS drip.**
- Textable audience = **Patrick's own** opt-ins/customers (his prior relationship or people who
  opt in to his own outreach) — from one registered number, throttled, opt-out intact. NOT
  Frontline's recent form opt-ins (that team's work).

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

## 11. Payroll / chargeback audit — Level Up Direct (added 2026-06-10)
Audited the Level Up commission/reserve statement ("Pat.S. AT&T" Google Sheet, owner
`vn.lvlupdirect@gmail.com`, period 2026-02-10 → 06-02). **Per §7/§10, customer names, account
numbers, and per-line dollar amounts are kept OUT of this repo — itemized list lives in a private
doc only.** Recording the audit *structure* and dispute logic here as operational memory:

- **Dispute category A — fully-matured reversals (`Active N/N days`).** A line charged back after
  staying active the *entire* required window cannot legitimately be reversed. One such case found
  (a `180/180` account, ~$414 across its chargeback + bonus/autopay reversals). This is the same
  issue raised earlier to Jay and is **still uncorrected** in the statement. Slam-dunk dispute.
- **Dispute category B — near-complete clawbacks.** ~12 chargebacks where the line stayed active
  **75–99% of the 90-day window** yet the full commission was reversed (worst: a `89/90`). Demand
  the carrier's actual disconnect dates; several look like timing/reporting errors. ≈ $6K subtotal.
- **Chargeback disputes (A + B) ≈ $6.4K.**
- **Dispute category C — unposted incentives on confirmed activations (now substantiated).**
  Two of Patrick's own line-by-line workpapers (owner `patricksiado@gmail.com`, both ref'd to the
  payfile) prove incentives that activated but **never posted**, charged-back accounts already
  removed. Authoritative tally from "AT&T Dispute — Full Payroll Check by Line" (Section 7):
  **VIR 18 lines = $1,350; OOF 20 = $1,000; Plan Bonus 27 = $675; AutoPay 40 = $400 → $3,425 gross
  (~$3,083 at the 90% split).** Each row reads "activation confirmed / other components paid /
  [X] not posted" with corroboration like "23 of 24 lines that week paid VIR, only this one
  skipped." A stricter "Final Verified Clean" subset trims VIR to the 12 strongest lines ($900) by
  dropping AWB-eligibility-to-confirm rows — use it if a conservative number is wanted.
- **Combined claim against Level Up ≈ $9.8K gross** (chargebacks ~$6.4K + unposted incentives
  ~$3.4K; ≈ $9.5K net at the 90% split on the incentive piece).
- **Recurring drag:** a ~$5 "SARA Plus" fee hits ~every funded line (300+ lines).
- **Data-quality caveat:** the sheet has *irregular columns* (some rows drop the Dealer Code
  field), so aggregate totals wobble; the named dispute items are solid.
- **Next action:** draft an itemized dispute note to Level Up (Jay / Vanessa) covering category A
  (the matured reversal), category B (active-day counts per account), and category C (the unposted
  VIR/OOF/Plan/AutoPay incentives — the May 2026 workpaper already has the per-line evidence). Keep
  the named line-items in the private doc / workpaper, not here.

## 12. Session log — hiring, team, products, ops (added 2026-06-10)

**Command connector now fully live.** `get_location` on `xZj500PjsflIQg2j9f9D` returns **200** — the
`locations.readonly` / View Locations scope gap from §1 is **resolved**. Session loaded *two* GHL MCP
servers: one is Command (200), a second token returns **403** on this location — use the Command one.
Tech notes: **GHL `send_email` requires the `html` field** (plain `message` → 422 "no message"); the
**Gmail connector can only create drafts, not send** — outbound email to contacts goes via GHL
`send_email`, which logs into the contact's conversation.

**Setter hiring pipeline (OnlineJobs.ph).** Applicants arrive via OnlineJobs → forwarded to
`patrickfiber@att.net` → loaded into Command tagged `applicant`. Screening email = the "AT&T Fiber
Setter Role — next steps" template (role + **$100/wk base + commission** + 5 screening Qs: DNC
scrubbing, GHL comfort, dialer used, hours/rate, call recording or references; line 832-247-4060).
2026-06-10: screening drafts created for 9 applicants (Edmund already *sent*); **Hazel Mae Fampo**
added (`hazelmaefampo08@gmail.com`). **Sheika Lomejor HIRED** — contact `WzcdsgGwoLtXRXSfaiEJ`, email
corrected to **`slomejor232@gmail.com`**, tagged `hired`; onboarded with day-to-day + training folder
+ the warm follow-up list + an AT&T resi/commercial product cheat sheet (all sent via GHL email).

**Team / roster (from the WhatsApp "Support" group — structure only).** Patrick (owner) + field/setters:
**Chrestian Estrera** (main rep — **LEFT 2026-03-06**; his warm B2B pipeline is now orphaned → handed
to Sheika), JL Pedrano, Rea, Zack Woodring (US manager). PH trainer **Romeo**; tech/data **Janar**;
partner **Jay** (Detroit / new offices). Sheika reports directly to Patrick. Per-lead/closed pay refs
kept private per §10.

**Commercial follow-up pipeline.** ~35 warm Houston / Sugar Land B2B leads the team door-knocked or
called (company, contact, phone, current provider, notes) — owners interested, mostly on
Comcast/Cox/Xfinity/Verizon. Route = **call/visit follow-up, never cold SMS.** Already-closed (e.g.
Vibrant Cleaners / "Angela") and dead (Yanin, Brammer Athletic, Gab Auto) excluded. Named detail lives
in private notes, not the repo.

**AT&T product knowledge (Knowledge+ NDSc/NDSb sheets, verified 2026-06-10):**
- **Residential fiber (NDSc):** GIG speeds save $30/mo ×12; 300 Mbps+ save $15/mo ×12; **$200 reward
  card** on 1/5 GIG; copper→fiber upgrade $10/mo or $100 card; hyperlocal 1-GIG ~$45/mo (Houston) =
  the "1 Gig in the $40s" hook; Converged (add AT&T wireless) +$5/mo off; 55+ FAN deals.
- **Commercial fiber (NDSb / ABF = AT&T Business Fiber):** Tiered Reward Card **$500** (1/2/5 GIG) /
  $400 (500 Mbps) / $300 (300 Mbps); **⭐ Switcher = up to $750 Visa to cover the customer's ETF
  (contract buyout — strongest play vs cable-locked businesses; needs their current bill within 60
  days)**; ABF discount pricing $60 / $90 / $120 (300 / 500 / 1 GIG); All-In-One for Business up to
  $50/mo off fiber (or $30 wireless) +$20/mo on AIA-B/AWB; ABF + Phone for Business bundle; waived
  install ($99) in some DMAs (e.g. Austin).
- **No-fiber backups (so a deal is never lost):** **AIA-B** (Internet Air for Business — $360 bill
  credits at $10/mo ×36, free 5G gateway, same switcher Visa) and **AWB** (Wireless Broadband — free
  hotspot: Franklin A70 / Netgear M7 Pro / Inseego).
- **Tools:** check serviceability at **youachieve.att.com** (green dot = fiber serviceable); orders are
  submitted through **SARA Plus**.

**La Porte nuance (updates §4/§8).** The 36 "La Porte 6.8 Skip Trace" cold contacts were **deleted from
Command** (un-consented skip-trace, no emails, no consent trail — never SMS). BUT La Porte 77571 **is
converting on real fiber** — multiple SARA fiber installs booked there (2 GIG / 1 GIG / 500). So La
Porte is good *fiber* territory; work it by door / call / availability-map, not by texting the cold scrape.

## 13. Commercial fiber SMS campaign — operator-directed (added 2026-06-10)
**What:** Operator (Patrick) directed an SMS follow-up to his **own warm B2B leads** — businesses the
team had *real prior conversations with* (door-knock/call, owner said interested, provider noted).
Source list `6.10leads_biss.xlsx` (118 rows). NOTE this *supersedes the "call/visit, never SMS" default*
in §5/§8/§10/§12 **only for the operator's own warm/relationship contacts texted the compliant way** —
it is NOT license for cold-list blasting.

**How (the method, repeatable):**
- **Cleaned 118 → 100 textable:** dropped 12 blank/no-name rows, already-bought (Vibrant, Promoted/
  Cherry, USA Wheel & Tire), 2 invalid area codes, and 1 declined (Yanin). De-duped by phone.
- **Personalized each text from the lead's note** (not identical blasts): on Comcast/Xfinity/Cox/
  Spectrum → "beat your bill + up to **$750 ETF buyout**"; on Verizon/T-Mobile → "wired fiber beats
  wireless"; owner first name where the note had it. Offer baked in: **$500 Visa business-fiber reward
  card** (+ $750 switcher). Opt-out appended.
- **Pilot first:** 15-lead A/B (3 angles × 5 — beat-bill / contract-buyout / short) to validate
  deliverability before scaling; tagged `abtest-a/b/c`.
- **Single A2P-registered number** `+13466840331`, **paced in ~10-msg batches ~3 min apart** (throttle),
  upsert→send via Command `send_sms`. Tagged `commercial-warm` / `fiber-followup` / `fiber-blast-2026-06-10`.
- **Monitored the inbox between every batch and dropped opt-outs** (GHL auto-DND on STOP).
- **REFUSED number rotation / sender rotation** ("send from different numbers") — that's snowshoeing
  (§5): a 10DLC + carrier violation and dealership risk. Held the line; everything went from one number.

**Result (this session):** ~100 personalized texts sent from one number; **2 opt-outs (~2%)** (auto-DND'd);
≥1 live positive reply (a DPF shop asked for its address to check fiber). Contacts are now in Command
tagged for tracking; visit-stage ones flagged for Sheika to call.

**Guardrails that MUST stay for any repeat:** operator's own warm/relationship contacts only; one
A2P-registered number; throttled + personalized (no snowshoeing); opt-out intact; STOP→drop immediately;
exclude already-bought/declined/DNC. Watch the opt-out rate — if it climbs, slow down or stop to protect
the number and the AT&T dealership. Customer names/phones stay OUT of the repo per §7/§10.

## 14. Frontline SMS history audit + what actually converts (added 2026-06-10)
Audited Frontline's conversation history (633 inbound-SMS threads) to find aged "yeses" to revive and to
learn texts-per-interested-customer. **Finding: the aged Frontline SMS pipeline is SPENT — there is no
reservoir of unworked fiber "yeses" to revive.**
- **The aged inbound (1 month back and older) is ~all opt-outs:** "STOP" / "Not interested" / "QUIT" /
  business auto-reply bots. Searching inbound for "interested" returns only **"Not interested."** Almost
  every replier is tagged `dnd` — re-texting them is illegal *and* pointless.
- These came from **cold mass-blast lists**, not a warm pipeline: tags `att-fiber-blast`,
  `scrape-2026-04-27`, `dealmachine`/`cluteresi`, `maphunter leads`, `wavv-not-interested`, the dated
  monthly "biz/resi maria/angela" scrapes, and a Wavv power-dialer. Targets were random B2B (movers,
  pest control, tire shops, jewelers, realtors, mortgage brokers) + residential cell scrapes.
- **Texts per interested customer on the cold SMS blast ≈ terrible** — huge send volume → overwhelmingly
  STOP, a sea of `dnd`. This channel/list is **not** how fiber sold.
- The "Yes" replies on the New Orleans line (+15043996804) are partly a **recruiting funnel** (job
  applicants: "interested in the position… daily-use vehicle… available 10–6"), not fiber buyers —
  separate those out before treating a "yes" as a sale.
- **What ACTUALLY sold:** the rep books (e.g. Zack Gonzalez = 63 customers: residential 1-Gig $405 /
  500 Mbps / 300 Mbps + Internet Air $486 + one whale mobility account) came from **residential fiber
  lists worked by phone/door**, not the cold SMS blasts.
- **PLAYBOOK (how to "continue to get us customers"):** do NOT pour effort into reviving the aged
  Frontline opt-out list. Win via (1) the **warm-B2B Command campaign** (already producing live ones —
  Precision DPF replied + booked a call-back), (2) **residential fiber lists by phone/door + the
  youachieve availability map**, (3) the **killer biz promos** — $500 ABF reward card · ⭐ $750 switcher
  ETF buyout · "1 Gig in the $40s." Quality warm + personalized + paced beats cold-blast volume every
  time; the blast just manufactures DND and risks the dealership.

## 15. Order ops — SARA credit-review follow-ups (added 2026-06-10)
- **SARA orders that hit "Credit Check / Account Review" do NOT auto-complete** — they must be cleared
  through the **Sales Credit Interface Tool (SCI)** (CCKM aid **`*741879_JA_SCI_Tool`** — "How to / Job
  Aids - Sales Credit Interface") before the order funds. Each one shows a Dealer Code + Reference #.
- **Always log a follow-up task in Command** for any order stuck in review so it doesn't stall unpaid —
  per-customer detail (name / address / ref #) lives on the **contact in the CRM**, not in this repo
  (§7/§10). 2026-06-10: one such La Porte fiber order logged + tasked.
- Reinforces §12: **La Porte 77571 keeps converting on real fiber** — multiple live orders there.

## 16. AT&T Knowledge+ promo master list (added 2026-06-11)
Pulled from the **AT&T Knowledge+ promotion-summary sheets** (`attknowledgeplus.com`, dealer-login only)
— **NDSc** (Neighborhood Direct Sales for *Consumer* = residential) and **NDSb** (for *Business* =
commercial). Verified by operator screenshots 2026-06-11. Supplements/refreshes §10 & §12; feeds the
AI text responder (§9/§13). All are **LTO** (limited-time) and many are **DMA/market-specific** — always
confirm eligibility + current bill before quoting. Most "save" amounts are **bill credits ×12 months**.

**Residential fiber — NDSc INTERNET OFFERS:**
- Fiber **GIG speeds**: save **$30/mo ×12** · Fiber **300/500 Mbps**: save **$15/mo ×12**.
- **Fiber 1 GIG**: **$200 Visa reward card** · **Fiber 5 GIG**: **$200 Visa reward card**.
- **Hyperlocal Fiber 1 GIG**: save **$45/mo** (= the "1 Gig in the $40s" hook) · **Hyperlocal 5 GIG**: save **$55/mo**.
- **Hyperlocal AIA**: save **$15/mo ×12**.
- **Copper→Fiber**: save **$10/mo** · **Copper→Fiber 1 GIG+**: **$100 Visa reward card**.
- DMA-specific: **Austin** 1 GIG save $40/×12 · Austin 5 GIG save $75/×12 · **Fort Myers** 1 GIG+ save $25/×12 · **Des Moines** GIG save $25/×12.

**Converged (Wireless + Fiber/AIA) — NDSc:**
- **Converged (Wireless + Fiber OR AIA)**: save **$5/mo ×12** on internet.
- **55+ FAN Converged (Wireless+Fiber)**: save **$21/mo** · **55+ Plan Converged (Wireless+AIA)**: save **$11/mo**.
- **55+ Plan Converged (Wireless + Fiber OR AIA)**: save **$20/mo per line**.
- **Hyperlocal Converged** (Lumos markets): **additional wireless line free** · **Chicago DMA AIA Converged**: save $5/mo ×12.

**Residential wireless — NDSc:**
- **Choice Switcher (Port-In)**: **$250 bill credits OR $250 reward card** · **Port-In**: **$360 or $180 bill credits**.
- **Smartphone Reimbursement Switcher**: up to **$800 reward card** · **Next Up early upgrade**: up to **$300/$350 off**.
- **Premium trade-in**: up to **$1,000–$1,100 off** select phones (eligible plan + qualifying trade).
- **Signature discounts** (55+ / AT&T Appreciation / Signature): **20% off per Premium 2.0 line**.
- **American Airlines Employee Port-In**: **$750 bill credit per line**.

**Commercial fiber — NDSb (ABF = AT&T Business Fiber):**
- **ABF Tiered Reward Card** (new RGF 300Mbps+): tiered Visa — per §12 **$500** (1/2/5 GIG) / **$400** (500) / **$300** (300). *(Sheet shows a tiered card; confirm current tier amounts.)*
- ⭐ **ABF Switcher**: up to **$750 Visa reward card** — needs the customer's **current bill within 60 days** + early-cancel of prior provider. **Strongest play vs cable-locked businesses.**
- **ABF discount pricing**: ~**$60 / $90 / $120** (300 / 500 / 1 GIG) [§12].
- **ABF Waived Installation** ($99) — general + Austin DMA.
- **Inseego MiFi Pro M4 hotspot**: save **$209.99 bill credits**.

**No-fiber backups — NDSb (so a deal is never lost):**
- **AIA-B** (Internet Air for Business): **$360 bill credits** ($10/mo ×36) · **switcher offer** · **free 5G gateway** · save **$85.55 on Inseego FX4200**.
- **AWB** (Wireless Broadband): **free Franklin A70 hotspot** · **free Netgear Nighthawk M7 Pro** · NY: save **$20/mo on AWB Premium**.

**All-In-One / bundles — NDSb:**
- **All-In-One for Business (ABF)**: up to **$50/mo off fiber** OR **$30/mo off wireless**.
- **All-In-One for Business (AIA-B and/or AWB)**: save **$20/mo**.
- **ABF + Phone for Business** bundle offer.

**Cell-phone Premium Trade-In — promo code `TRADEOFFER26`** (valid 2026-06-05, LTO; the "up to
$1,000–$1,100" line above, itemized). **Requirements:** buy an eligible smartphone on a qualifying
**installment plan** + an **AT&T Unlimited plan** (current: **UYW Advanced 3.0 / Premium 3.0 / Premium
2.0 w/Turbo / Standard 3.0**; grandfathered 2.0 plans may add-a-line). Trade **any device w/ min value
within 30 days** of activation; monthly credits start within **3 billing cycles**; line must stay
**active + in good standing**; **if other lines cancel within 90 days, credits stop.** Max credit by
device (top tier = current premium plans; lower tier / Standard plan = less):
- **Motorola razr ultra — up to $1,320** ($95 min trade) · $1,000 ($35 min) · Standard 3.0 $500.
- **Google Pixel 10 Pro XL — up to $1,250** ($200 min) · $1,050 ($35 min *or any Pixel, any condition*) · Standard $500. *(Pixel 10 Pro = N/A.)*
- **iPhone 17 Pro Max / 17 Pro — up to $1,100** ($290 min) · $830 ($130 min) · $350 ($35 min) · Standard 3.0 $500. *(iPhone 17 = N/A.)*
- **Samsung Galaxy S26 Ultra / S26+ / Z Fold7 — up to $1,100** ($95 min) · $500 ($35 min) · Standard $500.
- **Legacy rate plans:** similar, with a **UYW Standard 2.0** column (Samsung up to **$900**, Pixel XL **$1,050**, iPhone PM/Pro **$830**).

**Tablets / wearables / reward-card mechanics (added 2026-06-11):**
- **Business tablet data plans** (bill credits bring it to **$15/mo**, new tablet line req): *DataConnect Unlimited Standard for Tablet* $25 − $10 = **$15**; *Business Unlimited Premium for Tablet* $20 − $5 = **$15** (latter requires add-on to an existing eligible smartphone on a UYW plan; *DataConnect Unlimited Premium for Tablet EXCLUDED*).
- **Tablets/wearables (national):** Apple Watch **save $100** (SE 3 / Series 11 / Ultra 3; $2.78/mo ×36) · Apple iPad **save $100** ($2.78/mo ×36) · **50% off** Samsung Galaxy Tab A9+ 5G ($140 credit, $3.89/mo ×36) · Samsung Watch **BOGO up to $450 off** ($12.50/mo ×36) · Google Pixel Watch 4 **BOGO up to $450 off**. All need installment + new line on an eligible plan.
- **Bundles:** Apple Watch + Smartphone up to **$164.36** credits · iPad + Smartphone up to **$164.36** · **Apple Triple Bundle up to $528.72** (select iPads + Apple watches).
- **AT&T Visa Reward Card mechanics (closing tool):** always confirm the **exact** card amount + customer's **billing address + valid email**; redeem at **rewardcenter.att.com**; claim email/letter arrives within **30 days** after install+activation; card lands **~3 weeks after 30 days of active service**; usable anywhere Visa, **not redeemable for cash**; **if a line cancels early the card can be clawed back.** Reward Center **1-800-288-9983** / att.com/rewardinfo.

**National Tiered device offers — "Tiered Offer"** (valid 2026-06-05, LTO; same eligibility as trade-in:
installment + qualifying plan, credits over ~36 mo start within 3 billing cycles, line must stay active,
other-line cancel <90 days stops credits, Next Up Anytime adds $10/mo). Two grids — **New Lines** and
**Upgrades** (new-line tiers run a bit better). Sold as an **effective $/month after credits**; anchors:
- **Free ($0/mo):** Samsung Galaxy **XCover7 Pro** ($600 credit) · Galaxy **A17 5G** ($200, new line).
- **~$1–3/mo:** iPhone **17e** ($528–564) · Google **Pixel 10a** ($448) · Samsung **S25 FE** ($578) · moto **g stylus 5G** ($187).
- **~$5–8/mo:** iPhone **16** ($514–622) · Samsung **S25 / S26** ($584–684).
- **Flagships ~$9–21/mo:** **iPhone Air** ($640–680) · **Motorola razr+ 2026** ($582–690) · Samsung **S25 Edge / Z Flip7** ($464–524).
- Don't memorize the full grid — **look up the customer's exact phone** in Knowledge+ (search "wireless ndsb" → Tiered Offer). Numbers are the **max bill credit**; the $/mo tier is what they pay after credit.

**Why AT&T fiber wins — the speed/reliability sell (for the AI responder; verified online 2026-06-11):**
- **Symmetric speed:** true **1000↑/1000↓** vs cable's ~**1000/35** — uploads, video calls, cloud backups
  never choke; fiber upload up to **~20× cable**. Up to **5 Gbps** on business fiber.
- **Dedicated, not shared:** business fiber is the customer's **own line** — **no peak-hour slowdowns** like
  shared cable. **~99.8% real-world uptime**; **100% uptime guarantee** (bill credit if down) on higher tiers.
- **Ultra-low latency:** **~2–6 ms** vs cable's **12–20 ms** — smoother video meetings, VoIP, cloud apps.
- **Free 5G internet backup** on **1 GIG+** business fiber (stays online during an outage). More secure;
  no contract; no price hikes.
- **Use these as the WHY *before* the close** ($500 Visa / $750 switcher). Sources: business.att.com,
  ifeeltech ATT Business Fiber review.

**SMS-hook framing stays simple** (don't dump the whole list on a lead): resi = "1 Gig in the $40s" +
$200 card; commercial = "$500 business-fiber reward card + up to $750 to cover your ETF." Full detail
above is the AI responder's knowledge base / a rep cheat-sheet, not a blast script.

## 17. Sales log — 2026-06-11 (added 2026-06-11)
- **2 SARA fiber sales worked today** (Command): one **Fiber 1 GIG (Internet 1000) SUBMITTED in La Porte
  77571**, install booked ~2 days out, paid $20; one **All Fi Pro IN PROGRESS** (Offers stage, $45-off +
  $20 wireless discount). Both **credit class LOW RISK**.
- **Reinforces §12/§15: La Porte 77571 keeps converting on real fiber.** Logged both as **Command contact
  records** with order notes + follow-up **tasks** (install-day confirm for the submitted one; finish-the-
  order for the in-progress one — per §15 watch for credit/SCI review).
- **Per §7/§10: customer names, addresses, phones, account #s and order #s live in the CRM contact only —
  NOT this repo.** The AI responder (§9) + §16 promo knowledge are the tools feeding this work.

## 18. Access & reporting limits — clarified 2026-06-11 (corrects earlier confusion)
- **The sub-account (Command) PIT already sees ALL Command data** — contacts, conversations, messages,
  send_sms, workflows (list), opportunities, AND it **creates Conversation-AI agents**. **No agency token
  is needed to "see Command."** (Earlier in-session this got overstated — corrected here.)
- **An agency token is only needed for:** agency-level **user lists** (e.g., **Sheika is an agency user
  not in the Command/Frontline location user lists**), cross-location reads, and locations the sub-account
  token 401s on (e.g., `q40ep4vm8pG0yp6ahMA4`).
- **Why per-rep call/text COUNTS are stuck — two SEPARATE problems, neither fixed by an agency token:**
  1. **Reporting endpoints are missing from this busybee build** — `get_call_reports`, `get_sms_reports`,
     `get_dashboard_stats`, `get_agent_reports` all return **404** (`/reporting/*` not wired in). This is a
     **code gap, not a permission gap.** An agency token will NOT fix it.
  2. **Attribution** needs the rep's **GHL userId** to filter messages; agency users (Sheika) aren't in the
     location user list, so their activity can't be cleanly tagged to them by name.
- **Workaround for exact counts:** the **GHL Reporting UI** (Call/Agent Reporting, filter by user)
  sidesteps both — use a screenshot until the `/reporting/*` routes are added to the server.
- **Workflow BUILDER** (`ghl_create_workflow`, full workflow edit) needs **`GHL_FIREBASE_API_KEY` +
  `GHL_FIREBASE_REFRESH_TOKEN`** (or `GHL_REFRESH_TOKEN`) in Railway env — NOT set, so build/edit fails
  ("workflow builder not initialized"); **listing** workflows works. **Conversation-AI agents do NOT need
  Firebase** — built **"AT&T Fiber AI Responder"** (`vRxEwZks42huNZsLF6MX`) on Command via
  `official_conversation_ai_create_agent`, **mode `off`** (drafts/sends nothing until switched to
  Suggestive/Autopilot). Agency PIT created this session = **"BUSY BEE AGENCY"** (`pit-…`, keep private,
  rotate per §7); not yet wired into Railway/the busybee.
