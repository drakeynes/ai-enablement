# M5 cleanup — master sheet vs Gregory diff

Generated: `2026-05-04T23:05:43.864271+00:00`

## Summary

- CSV rows total (after blank-name filter): **188**
- Matched to Gregory clients: **180**
- Unmatched: **8**
- Drake silent-skipped: **0**
- Name-ambiguous (>1 Gregory match): **0**
- Field changes proposed: **131** (Tier 1: 24 / Tier 2: 44 / Tier 3: 63)
- Handover note appends: **8** (8 idempotent skips)
- Cascade-redundant csm_standing skips: **0** (cascade sets at_risk; explicit RPC would duplicate the history row)

## Tier 1 — high-confidence auto-applies

### primary_csm (24)

| Client | Tab | Current | → Proposed | Reason |
|---|---|---|---|---|
| Ameet Kumar | USA | `Scott Chasing` | `Scott Wilson` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Andy V | USA | `Scott Chasing` | `Scott Wilson` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Cheston Nguyen | USA | `Scott Chasing` | `Lou Perez` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Christian Brooks | USA | `Scott Chasing` | `Scott Wilson` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Eric Brown | USA | `Scott Chasing` | `Lou Perez` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Eric Washington | USA | `Scott Chasing` | `Lou Perez` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Evan Bautista | USA | `Scott Chasing` | `Nabeel Junaid` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Giovanni Gregorio | USA | `Scott Chasing` | `Scott Wilson` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Hannah Carter | USA | `Scott Chasing` | `Lou Perez` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Justin J. Fogg | USA | `Scott Chasing` | `Scott Wilson` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Kevin Black | USA | `Scott Chasing` | `Scott Wilson` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Kylie Goldsmith | USA | `Scott Chasing` | `Scott Wilson` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Mubeen Siddiqui | USA | `Scott Chasing` | `Lou Perez` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Nate Simon | USA | `Scott Chasing` | `Scott Wilson` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Raga Mamidipaka | USA | `Scott Chasing` | `Lou Perez` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Rob Traffie | USA | `Scott Chasing` | `Scott Wilson` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| samhealy09@gmail.com | USA | `Scott Chasing` | `Scott Wilson` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Samuel Michel | AUS | `Scott Chasing` | `Lou Perez` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Sarah Cherney | USA | `Scott Chasing` | `Lou Perez` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Sean Rounds | USA | `Scott Chasing` | `Lou Perez` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Sonal Patel | USA | `Scott Chasing` | `Lou Perez` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Sunny Ghanathey | USA | `Scott Chasing` | `Lou Perez` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Temitomi Arenyeka | USA | `Scott Chasing` | `Lou Perez` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Zach Roberts | USA | `Scott Chasing` | `Scott Wilson` | primary_csm reassignment (cascade will likely set to Scott Chasing) |

### handover note append (8)

Each listed client gets the following text appended to `clients.notes`:

```
These clients have been handed over to advisors.
Nico-owned handovers: Marcus Miller, Mac McLaughlin, Srilekha Sikhinam, Kurt Buechler, Michael Garner, Sierra Waldrep, Matthew Gibson
Lou-owned handover: Shivam Patel
```

| Client | Existing notes? | Idempotent skip? |
|---|---|---|
| Marcus Miller | yes | yes (already contains the text) |
| Mac McLaughlin | yes | yes (already contains the text) |
| Srilekha Sikhinam | yes | yes (already contains the text) |
| Kurt Buechler | yes | yes (already contains the text) |
| Michael Garner | yes | yes (already contains the text) |
| Sierra Waldrep | yes | yes (already contains the text) |
| Shivam Patel | yes | yes (already contains the text) |
| Nico Bubalo | yes | yes (already contains the text) |


## Tier 2 — eyeball required

### email (2)

| Client | Tab | Current | CSV value | Reason |
|---|---|---|---|---|
| Cheston Nguyen | USA | `cheston@395northai.com` | `cheston.nguyen@gmail.com` | CSV email differs from Gregory primary; not in alternate_emails |
| Yeshlin Singh | AUS | `yeshlin_singh@yahoo.com` | `yeshlinp@gmail.com` | CSV email differs from Gregory primary; not in alternate_emails |

### slack_channel_id (26)

| Client | Tab | Current | CSV value | Reason |
|---|---|---|---|---|
| Basem Romio | USA | `(none — no slack_channels row)` | `C09CKPWPMC4` | Gregory has no slack_channels row for this client; CSV has one |
| Braden Threlkeld | USA | `(none — no slack_channels row)` | `C097Q3KV1PW` | Gregory has no slack_channels row for this client; CSV has one |
| Cheston Nguyen | USA | `(none — no slack_channels row)` | `C095M97K4UT` | Gregory has no slack_channels row for this client; CSV has one |
| Chris Hainlen | USA | `(none — no slack_channels row)` | `C0AVDP5R9H9` | Gregory has no slack_channels row for this client; CSV has one |
| connor savage | USA | `(none — no slack_channels row)` | `C097VJRM9T2` | Gregory has no slack_channels row for this client; CSV has one |
| DeJuan Buchanan | USA | `(none — no slack_channels row)` | `Brendan Groves` | Gregory has no slack_channels row for this client; CSV has one |
| Emmanuel DharaCharles | USA | `(none — no slack_channels row)` | `C09FC41H3C4` | Gregory has no slack_channels row for this client; CSV has one |
| Eric Brown | USA | `(none — no slack_channels row)` | `C09Q2KGFXEH` | Gregory has no slack_channels row for this client; CSV has one |
| Eric Washington | USA | `(none — no slack_channels row)` | `C09J702HP8S` | Gregory has no slack_channels row for this client; CSV has one |
| Evan Bautista | USA | `(none — no slack_channels row)` | `C09D5H0E14H` | Gregory has no slack_channels row for this client; CSV has one |
| Fabio dirico | AUS | `(none — no slack_channels row)` | `C09S9MRHTK8` | Gregory has no slack_channels row for this client; CSV has one |
| Giovanni Gregorio | USA | `(none — no slack_channels row)` | `C09AB9Q4S3G` | Gregory has no slack_channels row for this client; CSV has one |
| Hannah Carter | USA | `(none — no slack_channels row)` | `C09A0SQPXL3` | Gregory has no slack_channels row for this client; CSV has one |
| Isabel Bledsoe | USA | `(none — no slack_channels row)` | `C09KB99K4BW` | Gregory has no slack_channels row for this client; CSV has one |
| Joel Barrera | USA | `(none — no slack_channels row)` | `C0B0L1D4REC` | Gregory has no slack_channels row for this client; CSV has one |
| KEVIN ROY | USA | `(none — no slack_channels row)` | `C0AUF6DHG92` | Gregory has no slack_channels row for this client; CSV has one |
| Krish Gopalani | USA | `(none — no slack_channels row)` | `C0AGYKHESUA` | Gregory has no slack_channels row for this client; CSV has one |
| Mark Dawson | USA | `(none — no slack_channels row)` | `C0ASD3DLMSN` | Gregory has no slack_channels row for this client; CSV has one |
| Mubeen Siddiqui | USA | `(none — no slack_channels row)` | `C097VJUBBDW` | Gregory has no slack_channels row for this client; CSV has one |
| Rubin Linder | USA | `(none — no slack_channels row)` | `C0ADY6NTKHN` | Gregory has no slack_channels row for this client; CSV has one |
| samhealy09@gmail.com | USA | `(none — no slack_channels row)` | `C09J5S16145` | Gregory has no slack_channels row for this client; CSV has one |
| Sean Rounds | USA | `(none — no slack_channels row)` | `C09APUUGX5Y` | Gregory has no slack_channels row for this client; CSV has one |
| Sierra Waldrep | USA | `(none — no slack_channels row)` | `C0AVBEBE5ND` | Gregory has no slack_channels row for this client; CSV has one |
| Swapnil Napuri | USA | `(none — no slack_channels row)` | `C0B08QELQMD` | Gregory has no slack_channels row for this client; CSV has one |
| Temitomi Arenyeka | USA | `(none — no slack_channels row)` | `C09FC41H3C3` | Gregory has no slack_channels row for this client; CSV has one |
| Yogesh Dhaybar | USA | `(none — no slack_channels row)` | `C0AVD0D9ZPC` | Gregory has no slack_channels row for this client; CSV has one |

### csm_standing (15)

| Client | Tab | Current | CSV value | Reason |
|---|---|---|---|---|
| Benjamin Baros | USA | `at_risk` | `Owing Money` | financial-only standing (no CSM tier) — eyeball |
| Camilo Corona | USA | `at_risk` | `Owing Money` | financial-only standing (no CSM tier) — eyeball |
| Charles Biller | USA | `at_risk` | `N/A (Churn)` | financial-only standing (no CSM tier) — eyeball |
| Daniel Wajsbrot | USA | `at_risk` | `Partial Refund` | financial-only standing (no CSM tier) — eyeball |
| Emmanuel DharaCharles | USA | `at_risk` | `Chargeback` | financial-only standing (no CSM tier) — eyeball |
| Ethan Evans | USA | `at_risk` | `Owing Money` | financial-only standing (no CSM tier) — eyeball |
| Grayson Carpenter | USA | `at_risk` | `Owing Money` | financial-only standing (no CSM tier) — eyeball |
| Heath Perkins | USA | `at_risk` | `Owing Money` | financial-only standing (no CSM tier) — eyeball |
| Jarrett Fortune | USA | `at_risk` | `Refunded` | financial-only standing (no CSM tier) — eyeball |
| Muhammad Omer Masood | USA | `at_risk` | `Chargeback` | financial-only standing (no CSM tier) — eyeball |
| Muhammed Mudasser | USA | `at_risk` | `Full Refund` | financial-only standing (no CSM tier) — eyeball |
| Patrick Tobin | USA | `at_risk` | `Partial Refund` | financial-only standing (no CSM tier) — eyeball |
| roula deraz | USA | `at_risk` | `Full Refund` | financial-only standing (no CSM tier) — eyeball |
| Steven Bass | USA | `at_risk` | `Chargeback` | financial-only standing (no CSM tier) — eyeball |
| Taidhg Driscoll | USA | `at_risk` | `Full Refund` | financial-only standing (no CSM tier) — eyeball |

### slack_user_id (1)

| Client | Tab | Current | CSV value | Reason |
|---|---|---|---|---|
| Fabio dirico | AUS | `null` | `U09SBPR7H0A` | CSV has slack_user_id; Gregory does not |


## Tier 3 — Scott meeting items (defer auto-apply)

### nps_standing (59)

| Client | Tab | Current | CSV value | Reason |
|---|---|---|---|---|
| Abel Asfaw | USA | `(not loaded)` | `Neutral` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Ajalynn Domingo | USA | `(not loaded)` | `Neutral` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Allison Jayme Boeshans | USA | `(not loaded)` | `Neutral` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Amaan Mehmood | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Amanda S. | USA | `(not loaded)` | `Detractor / At Risk` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Andrew Hsu | USA | `(not loaded)` | `Neutral` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Anthony Palumbo | USA | `(not loaded)` | `Neutral` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Ashan Fernando | USA | `(not loaded)` | `Neutral` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Austin Burke | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Avery Walker | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Brendan Groves | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Cindy Yu | USA | `(not loaded)` | `Neutral` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Cole Coughlin | USA | `(not loaded)` | `Detractor / At Risk` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Dadiana Perez | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Dhamen Hothi | USA | `(not loaded)` | `Neutral` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Dominique Frederick | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Edward Molina | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Elizabeth Williams | USA | `(not loaded)` | `Neutral` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Fernando G | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Frank Roselli | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Ian Drogin | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Intekhab Naser | USA | `(not loaded)` | `Detractor / At Risk` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Isabel Bledsoe | USA | `(not loaded)` | `Detractor / At Risk` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Jason Hamm | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Javi Pena | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Jenny Burnett | USA | `(not loaded)` | `Detractor / At Risk` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Jerry Thomas | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Jonathan Duran | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| josh glandorf | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| KC Lantern (Casie Weneta) | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Kenan Cantekin | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Krish Gopalani | USA | `(not loaded)` | `Neutral` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Kristen Lee | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Kurt Buechler | USA | `(not loaded)` | `Detractor / At Risk` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Luis Malo | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Mac McLaughlin | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Marcus Miller | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Mark Entwistle | USA | `(not loaded)` | `Detractor / At Risk` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Mary Kissiedu | USA | `(not loaded)` | `Neutral` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Matt Leblanc | USA | `(not loaded)` | `Detractor / At Risk` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Michael Shaw | USA | `(not loaded)` | `Detractor / At Risk` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Musa Elmaghrabi | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Naymuddullah Farhan | AUS | `(not loaded)` | `Neutral` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Nicholas V. LoScalzo | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Nico Bubalo | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Nolan | USA | `(not loaded)` | `Detractor / At Risk` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Owen Nordberg | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Rahim Ali | USA | `(not loaded)` | `Neutral` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Ryan Murphy | USA | `(not loaded)` | `Detractor / At Risk` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Sadiq Sumra | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Salman Rahman | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Samantha Bellisfield | USA | `(not loaded)` | `Neutral` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Samuel Michel | AUS | `(not loaded)` | `Detractor / At Risk` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Shivam Patel | USA | `(not loaded)` | `Neutral` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Srilekha Sikhinam | USA | `(not loaded)` | `Neutral` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Tina Hussain | USA | `(not loaded)` | `Neutral` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Tom Sauer | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Trevor Heck | USA | `(not loaded)` | `Promoter` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |
| Vid | USA | `(not loaded)` | `Neutral` | NPS Standing in CSV — Path 1 owns this column; surfaces only for Drake/Scott eyeball |

### primary_csm (4)

| Client | Tab | Current | CSV value | Reason |
|---|---|---|---|---|
| Alex Crosby | USA | `Scott Chasing` | `Aleks` | Aleks-owned (M4 Chunk C carry-over — Scott reassignment) |
| Colin Hill | USA | `null` | `Aleks` | Aleks-owned (M4 Chunk C carry-over — Scott reassignment) |
| Jose Trejo | USA | `Scott Chasing` | `Aleks` | Aleks-owned (M4 Chunk C carry-over — Scott reassignment) |
| Ming-Shih Wang | USA | `Scott Chasing` | `Aleks` | Aleks-owned (M4 Chunk C carry-over — Scott reassignment) |


## Unmatched CSV rows (8)

| Tab | CSV row | Name | Email |
|---|---|---|---|
| AUS | 10 | Anthony Huang | anthony@techmanual.io |
| USA | 87 | Clyde Vinson | (none) |
| USA | 180 | Matthew Gibson | leandeavor@gmail.com |
| AUS | 2 | Melvin Dayal | mel2.kar3@hotmail.com |
| AUS | 8 | Mishank | (none) |
| USA | 132 | Rachelle Hernandez | (none) |
| USA | 81 | Scott Stauffenberg | (none) |
| USA | 45 | Vaishali Adla | (none) |

