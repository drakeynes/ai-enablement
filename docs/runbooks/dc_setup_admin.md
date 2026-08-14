# DC Setup — operator guide (for Zain / Aman / the team)

**Where:** Gregory → Sales sidebar → **DC Setup** (visible to admins only).
**What it's for:** everything the **DC Ads** page needs to stay accurate —
people, landing pages, campaigns — with **no engineer involved**. Most things
register themselves automatically; this page is where you confirm new reps,
offboard leavers, rename things, and fix what the automation can't know.

Changes show up on the DC Ads page within a minute or two (refresh the page).
Lead/spend numbers that depend on re-stamping (e.g. moving a campaign to a
different landing page) catch up within ~15 minutes.

---

## Scenario 1 — a new rep joined

1. Add them to the **Airtable "Sales Team Member" table** (as always). Within
   ~30 minutes they appear in DC Setup under **"New reps to verify."**
2. Open DC Setup. On their card: check the name, pick their **role**
   (Setter / Closer / DC Closer), and pick their **Close account** — the
   dropdown is usually pre-filled with a suggested match (highlighted);
   confirm it's the right person. Their email fills in automatically.
3. Click **Verify**. Done — they now appear on the DC Ads by-rep table, the
   roster cards, and every other per-rep view, with their calls and their
   filed close forms merged into one row.

> Why this matters: until someone is verified, their **dialing** shows under
> their Close name and their **closes** show under their form nickname — two
> separate rows (that's the "NOT LINKED" tag you may see on the DC Ads page).
> Verifying links the two identities permanently.

## Scenario 1b — dismissed someone by accident

Under the verify queue there's a collapsed **"Dismissed (N)"** line — click it,
find the person, hit **Restore**. They pop straight back into the queue above.
(Dismiss is only for test/junk rows; real people get verified or left waiting.)

## Scenario 2 — a rep left (high turnover path)

DC Setup → **Current team** → find them → **Deactivate**. Their history stays
counted forever; they just stop showing as an active member. If they come
back, **Reactivate** — same row, nothing lost. Never ask for a delete.

## Scenario 3 — someone's dialing but not showing on the DC Ads page

The page shows **confirmed team members only**. If someone's calls aren't
appearing, they're not on the team yet: add them to the **Airtable Sales Team
Member table** and verify them (Scenario 1) — their past activity appears
retroactively the moment they're verified. Anyone you don't add simply never
shows on the page.

## Scenario 4 — a new funnel / landing page launched

Usually: **do nothing.** When the ads start running, the campaign and its
landing page register themselves (named by the URL, e.g. `join/training`), and
the videos attach once Wistia sees them play on the page. Afterwards, in the
**Landing pages** section you can:

- **Rename** it (the name shows in the DC Ads dropdown).
- Attach the **Typeform** if it didn't resolve on its own, then pick the
  **qualification question** and tick the answers that count as *qualified*
  (this drives the "Qualified" number on the DC Ads page).
- Add **videos** that haven't auto-attached, and the **extra funnel pages**
  (pages after the opt-in that show the funnel's video — e.g. Luke's `/t-2`).

## Scenario 5 — a landing page or campaign is being retired

- **Landing page** → Landing pages section → **Retire**. It leaves the DC Ads
  dropdown; history stays counted. **Restore** brings it back.
- **Campaign** → Campaigns section → **Retire**. ⚠ This removes its spend
  **and its leads** from every number on the DC Ads page — use it only for
  campaigns that never belonged there. A campaign that's merely paused in
  Meta should stay active here (its history still counts).

## Scenario 6 — a campaign is pointing at the wrong landing page(s)

Campaigns section → tick/untick the landing-page checkboxes on that campaign's
row. Spend re-scopes immediately; the lead numbers re-stamp within ~15
minutes. **Split-testing two pages under one campaign?** Tick both — each
lead is attributed to the page whose form they filled (the first ticked page
is the fallback when a lead never reached a form). The DC Ads page's
landing-page dropdown and the "All landing pages" summary always show exactly
the pages ticked on active campaigns.

---

## Scenario 7 — "are the numbers up to date?"

Bottom of DC Setup: **System health** — one card per data feed (Meta Ads,
Close, Typeform, Airtable, Wistia, and the page's own refresh) with
✅ Connected · last sync time. All green = nothing to do. A ⚠ (stale) or
❌ (silent for days) means that feed stopped — ping Drake with a screenshot;
nothing on this page can break it further.

## What you never need to touch

- **Adding campaigns** — auto-detected from Meta within ~15 minutes of ads
  running (instant-form campaigns by their form setup, landing-page campaigns
  by their ads pointing at a `digitalcollege.ai` page).
- **Adding landing pages for new campaigns** — auto-created from the ads'
  destination URL.
- **Attaching videos** — auto-attached when Wistia sees a video playing on a
  registered page (add the page under "extra funnel pages" if the video lives
  on a mid-funnel page).
- **Typeform linking** — usually auto-resolved from the form's hidden
  tracking fields.

---

## Loom recording script (for the walkthrough video)

1. **Open** the Sales dashboard → point at **DC Setup** in the sidebar ("this
   page only shows for admins — it's where we manage everything about DC Ads
   ourselves").
2. **Team block**: show the verify queue. Pick one card, walk through
   name → role → the pre-suggested Close account ("it guesses the match — you
   just confirm it's the right human") → Verify. Then flip to the DC Ads page
   and show the person's row now merged (dials + closes together, tag gone).
3. **Offboarding**: back in DC Setup, Current team → Deactivate someone →
   "history stays, they just stop being active" → Reactivate them.
4. **Radar**: point at "Seen dialing, not on the team" — "if a name shows
   here, they need to be added to the Airtable Sales Team Member table."
5. **Landing pages**: open Edit on `join/training` — show renaming, the
   Typeform picker, the qualification question with its checkboxes ("this is
   what makes an opt-in count as Qualified"), the video chips, extra funnel
   pages. Cancel without saving.
6. **Campaigns**: show the landing-page dropdown per campaign and the
   Retire button — read the warning out loud ("retiring removes the campaign's
   spend AND leads from the page — only for campaigns that never belonged").
7. **Close** with: "everything else is automatic — new campaigns, new landing
   pages, and videos register themselves. You only confirm people and fix
   names."
