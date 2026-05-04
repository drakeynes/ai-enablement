# M5 cleanup — Scott meeting notes

Generated: `2026-05-04T23:05:43.864271+00:00`

_Apply phase ran. Counts: primary_csm_applied=24, handover_already_present=8_

## Bucket A — pre-apply ambiguities (Scott decides)

### A1. Blank or N/A status (0)

_(none)_

### A2. Aleks-owned rows (4)

- **Alex Crosby** (USA) — current owner `Scott Chasing`
- **Colin Hill** (USA) — current owner `null`
- **Jose Trejo** (USA) — current owner `Scott Chasing`
- **Ming-Shih Wang** (USA) — current owner `Scott Chasing`

### A3. Name-ambiguous CSV rows (0)

_(none)_

### A4. NPS Standing CSV-vs-Gregory (59)

_(Path 1 owns `clients.nps_standing`; CSV's NPS Standing column is Scott's read. Surfaced for eyeball — never auto-applied.)_

| Client | Tab | Gregory NPS Standing | CSV NPS Standing |
|---|---|---|---|
| Abel Asfaw | USA | `(not loaded)` | `Neutral` |
| Ajalynn Domingo | USA | `(not loaded)` | `Neutral` |
| Allison Jayme Boeshans | USA | `(not loaded)` | `Neutral` |
| Amaan Mehmood | USA | `(not loaded)` | `Promoter` |
| Amanda S. | USA | `(not loaded)` | `Detractor / At Risk` |
| Andrew Hsu | USA | `(not loaded)` | `Neutral` |
| Anthony Palumbo | USA | `(not loaded)` | `Neutral` |
| Ashan Fernando | USA | `(not loaded)` | `Neutral` |
| Austin Burke | USA | `(not loaded)` | `Promoter` |
| Avery Walker | USA | `(not loaded)` | `Promoter` |
| Brendan Groves | USA | `(not loaded)` | `Promoter` |
| Cindy Yu | USA | `(not loaded)` | `Neutral` |
| Cole Coughlin | USA | `(not loaded)` | `Detractor / At Risk` |
| Dadiana Perez | USA | `(not loaded)` | `Promoter` |
| Dhamen Hothi | USA | `(not loaded)` | `Neutral` |
| Dominique Frederick | USA | `(not loaded)` | `Promoter` |
| Edward Molina | USA | `(not loaded)` | `Promoter` |
| Elizabeth Williams | USA | `(not loaded)` | `Neutral` |
| Fernando G | USA | `(not loaded)` | `Promoter` |
| Frank Roselli | USA | `(not loaded)` | `Promoter` |
| Ian Drogin | USA | `(not loaded)` | `Promoter` |
| Intekhab Naser | USA | `(not loaded)` | `Detractor / At Risk` |
| Isabel Bledsoe | USA | `(not loaded)` | `Detractor / At Risk` |
| Jason Hamm | USA | `(not loaded)` | `Promoter` |
| Javi Pena | USA | `(not loaded)` | `Promoter` |
| Jenny Burnett | USA | `(not loaded)` | `Detractor / At Risk` |
| Jerry Thomas | USA | `(not loaded)` | `Promoter` |
| Jonathan Duran | USA | `(not loaded)` | `Promoter` |
| josh glandorf | USA | `(not loaded)` | `Promoter` |
| KC Lantern (Casie Weneta) | USA | `(not loaded)` | `Promoter` |
| Kenan Cantekin | USA | `(not loaded)` | `Promoter` |
| Krish Gopalani | USA | `(not loaded)` | `Neutral` |
| Kristen Lee | USA | `(not loaded)` | `Promoter` |
| Kurt Buechler | USA | `(not loaded)` | `Detractor / At Risk` |
| Luis Malo | USA | `(not loaded)` | `Promoter` |
| Mac McLaughlin | USA | `(not loaded)` | `Promoter` |
| Marcus Miller | USA | `(not loaded)` | `Promoter` |
| Mark Entwistle | USA | `(not loaded)` | `Detractor / At Risk` |
| Mary Kissiedu | USA | `(not loaded)` | `Neutral` |
| Matt Leblanc | USA | `(not loaded)` | `Detractor / At Risk` |
| Michael Shaw | USA | `(not loaded)` | `Detractor / At Risk` |
| Musa Elmaghrabi | USA | `(not loaded)` | `Promoter` |
| Naymuddullah Farhan | AUS | `(not loaded)` | `Neutral` |
| Nicholas V. LoScalzo | USA | `(not loaded)` | `Promoter` |
| Nico Bubalo | USA | `(not loaded)` | `Promoter` |
| Nolan | USA | `(not loaded)` | `Detractor / At Risk` |
| Owen Nordberg | USA | `(not loaded)` | `Promoter` |
| Rahim Ali | USA | `(not loaded)` | `Neutral` |
| Ryan Murphy | USA | `(not loaded)` | `Detractor / At Risk` |
| Sadiq Sumra | USA | `(not loaded)` | `Promoter` |

_(...truncated; 9 more — see full diff)_

### A5. "Owing Money" / unparseable standing (15)

- **Benjamin Baros** (USA) — CSV value `Owing Money`, current Gregory `at_risk`
- **Camilo Corona** (USA) — CSV value `Owing Money`, current Gregory `at_risk`
- **Charles Biller** (USA) — CSV value `N/A (Churn)`, current Gregory `at_risk`
- **Daniel Wajsbrot** (USA) — CSV value `Partial Refund`, current Gregory `at_risk`
- **Emmanuel DharaCharles** (USA) — CSV value `Chargeback`, current Gregory `at_risk`
- **Ethan Evans** (USA) — CSV value `Owing Money`, current Gregory `at_risk`
- **Grayson Carpenter** (USA) — CSV value `Owing Money`, current Gregory `at_risk`
- **Heath Perkins** (USA) — CSV value `Owing Money`, current Gregory `at_risk`
- **Jarrett Fortune** (USA) — CSV value `Refunded`, current Gregory `at_risk`
- **Muhammad Omer Masood** (USA) — CSV value `Chargeback`, current Gregory `at_risk`
- **Muhammed Mudasser** (USA) — CSV value `Full Refund`, current Gregory `at_risk`
- **Patrick Tobin** (USA) — CSV value `Partial Refund`, current Gregory `at_risk`
- **roula deraz** (USA) — CSV value `Full Refund`, current Gregory `at_risk`
- **Steven Bass** (USA) — CSV value `Chargeback`, current Gregory `at_risk`
- **Taidhg Driscoll** (USA) — CSV value `Full Refund`, current Gregory `at_risk`

### A6. Handover-note targets unresolved (2)

- **Matthew Gibson (in CSV row USA/180 but no Gregory client matches — needs to be created first)**
- **Lou (no client by that name in either CSV — spec ambiguous)**

### A8. Email mismatches (2)

_(CSV email differs from Gregory primary AND not in `alternate_emails`. Handle per `docs/runbooks/backfill_nps_from_airtable.md` § Failure modes — per-client triage to alternate_emails. Don't bulk-apply.)_

- **Cheston Nguyen** (USA) — Gregory `cheston@395northai.com`, CSV `cheston.nguyen@gmail.com`
- **Yeshlin Singh** (AUS) — Gregory `yeshlin_singh@yahoo.com`, CSV `yeshlinp@gmail.com`

### A9. Unmatched CSV rows WITH email — likely new clients (3)

_(These have emails but no matching Gregory client. Likely real new clients that need a manual create-or-merge decision.)_

- **Anthony Huang** (AUS row 10) — email=anthony@techmanual.io, status=Churn (Aus), owner=Lou
- **Matthew Gibson** (USA row 180) — email=leandeavor@gmail.com, status=Active, owner=Nico
- **Melvin Dayal** (AUS row 2) — email=mel2.kar3@hotmail.com, status=Churn (Aus), owner=Lou

### A10. Unmatched CSV rows WITHOUT email — Scott decision (5)

_(No email in CSV — match-by-name failed. Scott decides whether each is a real client to create, a duplicate to merge, or noise to skip.)_

- **Clyde Vinson** (USA row 87) — status=N/A, owner=N/A
- **Mishank** (AUS row 8) — status=Churn (Aus), owner=N/A
- **Rachelle Hernandez** (USA row 132) — status=N/A, owner=N/A
- **Scott Stauffenberg** (USA row 81) — status=N/A, owner=Nabeel
- **Vaishali Adla** (USA row 45) — status=N/A, owner=Nabeel

## Bucket B — post-apply mismatches (Scott confirms)

_(none — Gregory state matches CSV after apply)_

## Quick reference — status directives applied

_(no status flips proposed)_

