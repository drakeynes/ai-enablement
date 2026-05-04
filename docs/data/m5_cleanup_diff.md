# M5 cleanup — master sheet vs Gregory diff

Generated: `2026-05-04T20:47:01.458309+00:00`

## Summary

- CSV rows total (after blank-name filter): **188**
- Matched to Gregory clients: **180**
- Unmatched: **8**
- Drake silent-skipped: **0**
- Name-ambiguous (>1 Gregory match): **0**
- Field changes proposed: **314** (Tier 1: 107 / Tier 2: 144 / Tier 3: 63)
- Handover note appends: **8** (0 idempotent skips)

## Tier 1 — high-confidence auto-applies

### status (36)

| Client | Tab | Current | → Proposed | Reason |
|---|---|---|---|---|
| Abel Asfaw | USA | `paused` | `leave` | status flip → cascade will fire |
| Alex Crosby | USA | `paused` | `leave` | status flip → cascade will fire |
| Allison Jayme Boeshans | USA | `paused` | `active` | status flip |
| Amanda S. | USA | `paused` | `leave` | status flip → cascade will fire |
| Ameet Kumar | USA | `active` | `paused` | status flip → cascade will fire |
| Andy V | USA | `paused` | `leave` | status flip → cascade will fire |
| Brooke Gorman | USA | `ghost` | `leave` | status flip → cascade will fire |
| Cheston Nguyen | USA | `paused` | `leave` | status flip → cascade will fire |
| Chikezie Igwebuike | USA | `paused` | `churned` | status flip → cascade will fire |
| Christian Brooks | USA | `paused` | `leave` | status flip → cascade will fire |
| Eric Brown | USA | `paused` | `leave` | status flip → cascade will fire |
| Eric Washington | USA | `paused` | `leave` | status flip → cascade will fire |
| Evan Bautista | USA | `paused` | `leave` | status flip → cascade will fire |
| Fabio dirico | AUS | `active` | `churned` | status flip → cascade will fire |
| Giovanni Gregorio | USA | `paused` | `leave` | status flip → cascade will fire |
| Hannah Carter | USA | `paused` | `leave` | status flip → cascade will fire |
| John Keever | USA | `active` | `ghost` | status flip → cascade will fire |
| Jose Trejo | USA | `paused` | `leave` | status flip → cascade will fire |
| Justin J. Fogg | USA | `paused` | `leave` | status flip → cascade will fire |
| Kevin Black | USA | `paused` | `leave` | status flip → cascade will fire |
| Kylie Goldsmith | USA | `paused` | `leave` | status flip → cascade will fire |
| Marcus Miller | USA | `ghost` | `active` | status flip |
| Ming-Shih Wang | USA | `paused` | `leave` | status flip → cascade will fire |
| Mubeen Siddiqui | USA | `paused` | `leave` | status flip → cascade will fire |
| Nate Simon | USA | `active` | `ghost` | status flip → cascade will fire |
| Patrika Cheston | USA | `ghost` | `leave` | status flip → cascade will fire |
| Raga Mamidipaka | USA | `paused` | `leave` | status flip → cascade will fire |
| Rob Traffie | USA | `active` | `leave` | status flip → cascade will fire |
| samhealy09@gmail.com | USA | `paused` | `leave` | status flip → cascade will fire |
| Samuel Michel | AUS | `active` | `paused` | status flip → cascade will fire |
| Sarah Cherney | USA | `active` | `leave` | status flip → cascade will fire |
| Sean Rounds | USA | `paused` | `leave` | status flip → cascade will fire |
| Sonal Patel | USA | `paused` | `leave` | status flip → cascade will fire |
| Sunny Ghanathey | USA | `active` | `leave` | status flip → cascade will fire |
| Temitomi Arenyeka | USA | `paused` | `leave` | status flip → cascade will fire |
| Zach Roberts | USA | `paused` | `leave` | status flip → cascade will fire |

### csm_standing (36)

| Client | Tab | Current | → Proposed | Reason |
|---|---|---|---|---|
| Abel Asfaw | USA | `at_risk` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Alex Crosby | USA | `at_risk` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Ameet Kumar | USA | `at_risk` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Basem Romio | USA | `at_risk` | `problem` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Braden Threlkeld | USA | `at_risk` | `happy` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Cheston Nguyen | USA | `at_risk` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Chris Ferrente | USA | `at_risk` | `problem` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Christian Brooks | USA | `at_risk` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Colin Hill | USA | `at_risk` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Dinesh | AUS | `null` | `at_risk` | csm_standing flip |
| Eric Washington | USA | `at_risk` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Ethan Clark | USA | `at_risk` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Evan Bautista | USA | `at_risk` | `happy` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Fabio dirico | AUS | `null` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Giovanni Gregorio | USA | `at_risk` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Guillermo Budde | USA | `at_risk` | `problem` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Hannah Carter | USA | `at_risk` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |
| James Tran | AUS | `null` | `content` | csm_standing flip |
| John Keever | USA | `content` | `at_risk` | csm_standing flip |
| Jose Trejo | USA | `at_risk` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Kevin Black | USA | `at_risk` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Krish Gopalani | USA | `at_risk` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Kylie Goldsmith | USA | `at_risk` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Le-Minh Khieu | USA | `at_risk` | `happy` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Marcus Miller | USA | `at_risk` | `happy` | csm_standing flip |
| Mark Dawson | USA | `at_risk` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Mary Kissiedu | USA | `at_risk` | `content` | csm_standing flip |
| Nate Simon | USA | `content` | `at_risk` | csm_standing flip |
| Raga Mamidipaka | USA | `at_risk` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Salman Rahman | USA | `happy` | `content` | csm_standing flip |
| samhealy09@gmail.com | USA | `at_risk` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Samuel Michel | AUS | `content` | `at_risk` | csm_standing flip |
| Sean Mullaney | USA | `at_risk` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |
| Sunny Ghanathey | USA | `content` | `at_risk` | csm_standing flip |
| Yeshlin Singh | AUS | `null` | `content` | csm_standing flip |
| Zach Roberts | USA | `at_risk` | `content` | csm_standing flip (cascade will likely overwrite to at_risk) |

### primary_csm (22)

| Client | Tab | Current | → Proposed | Reason |
|---|---|---|---|---|
| Abel Asfaw | USA | `Lou Perez` | `Scott Chasing` | primary_csm reassignment |
| Adeeb Mohammed | USA | `Lou Perez` | `Scott Chasing` | primary_csm reassignment |
| Amanda S. | USA | `Scott Wilson` | `Scott Chasing` | primary_csm reassignment |
| Andrew Hsu | USA | `Nico Sandoval` | `Scott Wilson` | primary_csm reassignment |
| Basem Romio | USA | `Lou Perez` | `Scott Chasing` | primary_csm reassignment |
| Brooke Gorman | USA | `Scott Wilson` | `Scott Chasing` | primary_csm reassignment |
| Chikezie Igwebuike | USA | `Lou Perez` | `Scott Chasing` | primary_csm reassignment |
| Fabio dirico | AUS | `Nico Sandoval` | `Scott Wilson` | primary_csm reassignment (cascade will likely set to Scott Chasing) |
| Jason Hamm | USA | `Lou Perez` | `Scott Chasing` | primary_csm reassignment |
| John Keever | USA | `Lou Perez` | `Scott Chasing` | primary_csm reassignment |
| Krish Gopalani | USA | `Lou Perez` | `Scott Chasing` | primary_csm reassignment |
| Kurt Buechler | USA | `Scott Wilson` | `Nico Sandoval` | primary_csm reassignment |
| Mac McLaughlin | USA | `Scott Wilson` | `Nico Sandoval` | primary_csm reassignment |
| Marcus Miller | USA | `Lou Perez` | `Nico Sandoval` | primary_csm reassignment |
| Michael Garner | USA | `Scott Wilson` | `Nico Sandoval` | primary_csm reassignment |
| Patrika Cheston | USA | `Scott Wilson` | `Scott Chasing` | primary_csm reassignment |
| Rahim Ali | USA | `Nico Sandoval` | `Scott Wilson` | primary_csm reassignment |
| Shivam Patel | USA | `Scott Wilson` | `Lou Perez` | primary_csm reassignment |
| Shyam Srinivas | AUS | `Lou Perez` | `Scott Chasing` | primary_csm reassignment |
| Sierra Waldrep | USA | `Scott Wilson` | `Nico Sandoval` | primary_csm reassignment |
| Srilekha Sikhinam | USA | `Scott Wilson` | `Nico Sandoval` | primary_csm reassignment |
| Swapnil Napuri | USA | `null` | `Scott Wilson` | primary_csm reassignment |

### trustpilot_status (13)

| Client | Tab | Current | → Proposed | Reason |
|---|---|---|---|---|
| Allison Jayme Boeshans | USA | `ask` | `no` | trustpilot flip |
| Dante Newton | USA | `asked` | `ask` | trustpilot flip |
| Dinesh | AUS | `null` | `yes` | trustpilot flip |
| James Tran | AUS | `null` | `no` | trustpilot flip |
| Naymuddullah Farhan | AUS | `null` | `ask` | trustpilot flip |
| Nicholas V. LoScalzo | USA | `ask` | `yes` | trustpilot flip |
| Ruphael G | USA | `ask` | `yes` | trustpilot flip |
| Sadiq Sumra | USA | `asked` | `yes` | trustpilot flip |
| Samuel Michel | AUS | `null` | `no` | trustpilot flip |
| Shivam Patel | USA | `asked` | `ask` | trustpilot flip |
| Shyam Srinivas | AUS | `null` | `no` | trustpilot flip |
| Trevor Heck | USA | `asked` | `ask` | trustpilot flip |
| Yeshlin Singh | AUS | `null` | `no` | trustpilot flip |

### handover note append (8)

Each listed client gets the following text appended to `clients.notes`:

```
These clients have been handed over to advisors.
Nico-owned handovers: Marcus Miller, Mac McLaughlin, Srilekha Sikhinam, Kurt Buechler, Michael Garner, Sierra Waldrep, Matthew Gibson
Lou-owned handover: Shivam Patel
```

| Client | Existing notes? | Idempotent skip? |
|---|---|---|
| Marcus Miller | no | no — will append |
| Mac McLaughlin | no | no — will append |
| Srilekha Sikhinam | no | no — will append |
| Kurt Buechler | no | no — will append |
| Michael Garner | no | no — will append |
| Sierra Waldrep | no | no — will append |
| Shivam Patel | no | no — will append |
| Nico Bubalo | no | no — will append |


## Tier 2 — eyeball required

### slack_channel_id (126)

| Client | Tab | Current | CSV value | Reason |
|---|---|---|---|---|
| Abel Asfaw | USA | `(not loaded — see slack_channels table)` | `C0A972VJQ9F` | CSV has slack_channel_id; verify against slack_channels table |
| Adam Macdonald | USA | `(not loaded — see slack_channels table)` | `C09U6J6D41J` | CSV has slack_channel_id; verify against slack_channels table |
| Adeeb Mohammed | USA | `(not loaded — see slack_channels table)` | `C0AK6EYSPH8` | CSV has slack_channel_id; verify against slack_channels table |
| Ajalynn Domingo | USA | `(not loaded — see slack_channels table)` | `C098NBQ5G4E` | CSV has slack_channel_id; verify against slack_channels table |
| Allison Jayme Boeshans | USA | `(not loaded — see slack_channels table)` | `C0ACD6PHHAB` | CSV has slack_channel_id; verify against slack_channels table |
| Amaan Mehmood | USA | `(not loaded — see slack_channels table)` | `C0ABXD8JA9E` | CSV has slack_channel_id; verify against slack_channels table |
| Amanda S. | USA | `(not loaded — see slack_channels table)` | `C09TFBHTEMN` | CSV has slack_channel_id; verify against slack_channels table |
| Ameet Kumar | USA | `(not loaded — see slack_channels table)` | `C0AKAQ7SBGU` | CSV has slack_channel_id; verify against slack_channels table |
| Andrew Hsu | USA | `(not loaded — see slack_channels table)` | `C09FWPWKS31` | CSV has slack_channel_id; verify against slack_channels table |
| Annie Yang | USA | `(not loaded — see slack_channels table)` | `C0AFLHE74MD` | CSV has slack_channel_id; verify against slack_channels table |
| Anthony Palumbo | USA | `(not loaded — see slack_channels table)` | `C094XG0BNKZ` | CSV has slack_channel_id; verify against slack_channels table |
| Art Nuno | USA | `(not loaded — see slack_channels table)` | `C0AQQFG5UEP` | CSV has slack_channel_id; verify against slack_channels table |
| Ashan Fernando | USA | `(not loaded — see slack_channels table)` | `C094XF7AN95` | CSV has slack_channel_id; verify against slack_channels table |
| Austin Burke | USA | `(not loaded — see slack_channels table)` | `C09U7T04PC4` | CSV has slack_channel_id; verify against slack_channels table |
| Avery Walker | USA | `(not loaded — see slack_channels table)` | `C099DQM2A3W` | CSV has slack_channel_id; verify against slack_channels table |
| Basem Romio | USA | `(not loaded — see slack_channels table)` | `C09CKPWPMC4` | CSV has slack_channel_id; verify against slack_channels table |
| Braden Threlkeld | USA | `(not loaded — see slack_channels table)` | `C097Q3KV1PW` | CSV has slack_channel_id; verify against slack_channels table |
| Brendan Groves | USA | `(not loaded — see slack_channels table)` | `C0A980QEB55` | CSV has slack_channel_id; verify against slack_channels table |
| Brian Arellano | USA | `(not loaded — see slack_channels table)` | `C0ALJ8UN1FH` | CSV has slack_channel_id; verify against slack_channels table |
| Brooke Gorman | USA | `(not loaded — see slack_channels table)` | `C0ACH39750U` | CSV has slack_channel_id; verify against slack_channels table |
| Cheston Nguyen | USA | `(not loaded — see slack_channels table)` | `C095M97K4UT` | CSV has slack_channel_id; verify against slack_channels table |
| Chikezie Igwebuike | USA | `(not loaded — see slack_channels table)` | `C09JT3QUX1C` | CSV has slack_channel_id; verify against slack_channels table |
| Chris Hainlen | USA | `(not loaded — see slack_channels table)` | `C0AVDP5R9H9` | CSV has slack_channel_id; verify against slack_channels table |
| Cindy Yu | USA | `(not loaded — see slack_channels table)` | `C09F4LWQNAK` | CSV has slack_channel_id; verify against slack_channels table |
| Cole Coughlin | USA | `(not loaded — see slack_channels table)` | `C099JMLFE8G` | CSV has slack_channel_id; verify against slack_channels table |
| connor savage | USA | `(not loaded — see slack_channels table)` | `C097VJRM9T2` | CSV has slack_channel_id; verify against slack_channels table |
| Dadiana Perez | USA | `(not loaded — see slack_channels table)` | `C0AAUBW2MQX` | CSV has slack_channel_id; verify against slack_channels table |
| Dante Newton | USA | `(not loaded — see slack_channels table)` | `C0A2EUPELUU` | CSV has slack_channel_id; verify against slack_channels table |
| Darin Goodrum | USA | `(not loaded — see slack_channels table)` | `C0AN8EMK4MN` | CSV has slack_channel_id; verify against slack_channels table |
| DeJuan Buchanan | USA | `(not loaded — see slack_channels table)` | `Brendan Groves` | CSV has slack_channel_id; verify against slack_channels table |
| Dhamen Hothi | USA | `(not loaded — see slack_channels table)` | `C0AFEC456JG` | CSV has slack_channel_id; verify against slack_channels table |
| Dinesh | AUS | `(not loaded — see slack_channels table)` | `C09RYFEC2CS` | CSV has slack_channel_id; verify against slack_channels table |
| Dominique Frederick | USA | `(not loaded — see slack_channels table)` | `C0ARHGX7M0U` | CSV has slack_channel_id; verify against slack_channels table |
| Edward Molina | USA | `(not loaded — see slack_channels table)` | `C09DGEACT1C` | CSV has slack_channel_id; verify against slack_channels table |
| Elan Kamen | USA | `(not loaded — see slack_channels table)` | `C097LHRATPA` | CSV has slack_channel_id; verify against slack_channels table |
| Elizabeth Williams | USA | `(not loaded — see slack_channels table)` | `C0AMA4SPK7V` | CSV has slack_channel_id; verify against slack_channels table |
| Emmanuel DharaCharles | USA | `(not loaded — see slack_channels table)` | `C09FC41H3C4` | CSV has slack_channel_id; verify against slack_channels table |
| Eric Brown | USA | `(not loaded — see slack_channels table)` | `C09Q2KGFXEH` | CSV has slack_channel_id; verify against slack_channels table |
| Eric Washington | USA | `(not loaded — see slack_channels table)` | `C09J702HP8S` | CSV has slack_channel_id; verify against slack_channels table |
| Evan Bautista | USA | `(not loaded — see slack_channels table)` | `C09D5H0E14H` | CSV has slack_channel_id; verify against slack_channels table |
| Fabio dirico | AUS | `(not loaded — see slack_channels table)` | `C09S9MRHTK8` | CSV has slack_channel_id; verify against slack_channels table |
| Fernando G | USA | `(not loaded — see slack_channels table)` | `C09TYEPLGBX` | CSV has slack_channel_id; verify against slack_channels table |
| Frank Roselli | USA | `(not loaded — see slack_channels table)` | `C0AP2V1K3RB` | CSV has slack_channel_id; verify against slack_channels table |
| Giovanni Gregorio | USA | `(not loaded — see slack_channels table)` | `C09AB9Q4S3G` | CSV has slack_channel_id; verify against slack_channels table |
| Hannah Carter | USA | `(not loaded — see slack_channels table)` | `C09A0SQPXL3` | CSV has slack_channel_id; verify against slack_channels table |
| Hazel Castillo | USA | `(not loaded — see slack_channels table)` | `C09GGQC7PJQ` | CSV has slack_channel_id; verify against slack_channels table |
| Ian Drogin | USA | `(not loaded — see slack_channels table)` | `C09N0PRJUA1` | CSV has slack_channel_id; verify against slack_channels table |
| Intekhab Naser | USA | `(not loaded — see slack_channels table)` | `C09H4QDQH7S` | CSV has slack_channel_id; verify against slack_channels table |
| Isabel Bledsoe | USA | `(not loaded — see slack_channels table)` | `C09KB99K4BW` | CSV has slack_channel_id; verify against slack_channels table |
| James Cowley | USA | `(not loaded — see slack_channels table)` | `C0ATF3UUW3A` | CSV has slack_channel_id; verify against slack_channels table |
| James Tran | AUS | `(not loaded — see slack_channels table)` | `C0ACXSN211V` | CSV has slack_channel_id; verify against slack_channels table |
| Jason Hamm | USA | `(not loaded — see slack_channels table)` | `C09L833N86A` | CSV has slack_channel_id; verify against slack_channels table |
| Javi Pena | USA | `(not loaded — see slack_channels table)` | `C09GA380JRM` | CSV has slack_channel_id; verify against slack_channels table |
| Jenny Burnett | USA | `(not loaded — see slack_channels table)` | `C0AF40ARZHD` | CSV has slack_channel_id; verify against slack_channels table |
| Jerry Thomas | USA | `(not loaded — see slack_channels table)` | `C095Q3DTJC9` | CSV has slack_channel_id; verify against slack_channels table |
| Jim Buddle | USA | `(not loaded — see slack_channels table)` | `C0ARR4HQ090` | CSV has slack_channel_id; verify against slack_channels table |
| Joel Barrera | USA | `(not loaded — see slack_channels table)` | `C0B0L1D4REC` | CSV has slack_channel_id; verify against slack_channels table |
| John Keever | USA | `(not loaded — see slack_channels table)` | `C0AN4NKDKD0` | CSV has slack_channel_id; verify against slack_channels table |
| Jonathan Duran | USA | `(not loaded — see slack_channels table)` | `C09U83GQQ0L` | CSV has slack_channel_id; verify against slack_channels table |
| Jordan Lucas | USA | `(not loaded — see slack_channels table)` | `C09GBQ1BMJS` | CSV has slack_channel_id; verify against slack_channels table |
| josh glandorf | USA | `(not loaded — see slack_channels table)` | `C09UYD6C3U6` | CSV has slack_channel_id; verify against slack_channels table |
| Josh Jeanes | USA | `(not loaded — see slack_channels table)` | `C0AUL3YAEQG` | CSV has slack_channel_id; verify against slack_channels table |
| KC Lantern (Casie Weneta) | USA | `(not loaded — see slack_channels table)` | `C0AHGSSES3V` | CSV has slack_channel_id; verify against slack_channels table |
| Kenan Cantekin | USA | `(not loaded — see slack_channels table)` | `C099JR5D5S5` | CSV has slack_channel_id; verify against slack_channels table |
| Kevin Black | USA | `(not loaded — see slack_channels table)` | `C09KZ8VSUGM` | CSV has slack_channel_id; verify against slack_channels table |
| Kevin Hartley | USA | `(not loaded — see slack_channels table)` | `C09MPBTHNF4` | CSV has slack_channel_id; verify against slack_channels table |
| KEVIN ROY | USA | `(not loaded — see slack_channels table)` | `C0AUF6DHG92` | CSV has slack_channel_id; verify against slack_channels table |
| Krish Gopalani | USA | `(not loaded — see slack_channels table)` | `C0AGYKHESUA` | CSV has slack_channel_id; verify against slack_channels table |
| Kristen Lee | USA | `(not loaded — see slack_channels table)` | `C0AEV95NUJC` | CSV has slack_channel_id; verify against slack_channels table |
| Kurt Buechler | USA | `(not loaded — see slack_channels table)` | `C0ALMUN68F7` | CSV has slack_channel_id; verify against slack_channels table |
| Luis Malo | USA | `(not loaded — see slack_channels table)` | `C0AAQGPK6EA` | CSV has slack_channel_id; verify against slack_channels table |
| Mac McLaughlin | USA | `(not loaded — see slack_channels table)` | `C09JKU7RRQB` | CSV has slack_channel_id; verify against slack_channels table |
| Marcus Miller | USA | `(not loaded — see slack_channels table)` | `C09FF8J5QLR` | CSV has slack_channel_id; verify against slack_channels table |
| Mark Dawson | USA | `(not loaded — see slack_channels table)` | `C0ASD3DLMSN` | CSV has slack_channel_id; verify against slack_channels table |
| Mark Entwistle | USA | `(not loaded — see slack_channels table)` | `C0AM168HAAY` | CSV has slack_channel_id; verify against slack_channels table |
| Mary Kissiedu | USA | `(not loaded — see slack_channels table)` | `C09CW6SPSA0` | CSV has slack_channel_id; verify against slack_channels table |
| Matt Leblanc | USA | `(not loaded — see slack_channels table)` | `C096K8AHFT8` | CSV has slack_channel_id; verify against slack_channels table |
| Maurya Yenugachenna | USA | `(not loaded — see slack_channels table)` | `C0AB0LSK072` | CSV has slack_channel_id; verify against slack_channels table |
| Michael Garner | USA | `(not loaded — see slack_channels table)` | `C0ASJ4PR9FT` | CSV has slack_channel_id; verify against slack_channels table |
| Michael Shaw | USA | `(not loaded — see slack_channels table)` | `C09FW0CEQLB` | CSV has slack_channel_id; verify against slack_channels table |
| Moctar Toure | USA | `(not loaded — see slack_channels table)` | `C0ARZJB2CLA` | CSV has slack_channel_id; verify against slack_channels table |
| Mohammed Nawaz | USA | `(not loaded — see slack_channels table)` | `C0AT5386Y94` | CSV has slack_channel_id; verify against slack_channels table |
| Mubeen Siddiqui | USA | `(not loaded — see slack_channels table)` | `C097VJUBBDW` | CSV has slack_channel_id; verify against slack_channels table |
| Musa Elmaghrabi | USA | `(not loaded — see slack_channels table)` | `C09FA7EQRDL` | CSV has slack_channel_id; verify against slack_channels table |
| Nate Simon | USA | `(not loaded — see slack_channels table)` | `C09VD053TR6` | CSV has slack_channel_id; verify against slack_channels table |
| Naymuddullah Farhan | AUS | `(not loaded — see slack_channels table)` | `C09UGQMA64R` | CSV has slack_channel_id; verify against slack_channels table |
| Nic Kieper | USA | `(not loaded — see slack_channels table)` | `C0ANEP37ZBM` | CSV has slack_channel_id; verify against slack_channels table |
| Nicholas V. LoScalzo | USA | `(not loaded — see slack_channels table)` | `C0A8707RR8V` | CSV has slack_channel_id; verify against slack_channels table |
| Nico Bubalo | USA | `(not loaded — see slack_channels table)` | `C0AMFRUSUH5` | CSV has slack_channel_id; verify against slack_channels table |
| Nicolas Cabrera | USA | `(not loaded — see slack_channels table)` | `C09D591J95G` | CSV has slack_channel_id; verify against slack_channels table |
| Nolan | USA | `(not loaded — see slack_channels table)` | `C09UDFLNB3J` | CSV has slack_channel_id; verify against slack_channels table |
| Owen Nordberg | USA | `(not loaded — see slack_channels table)` | `C094XG2BG15` | CSV has slack_channel_id; verify against slack_channels table |
| Patrika Cheston | USA | `(not loaded — see slack_channels table)` | `C0ANG6A5ERG` | CSV has slack_channel_id; verify against slack_channels table |
| Rahim Ali | USA | `(not loaded — see slack_channels table)` | `C097U728M6U` | CSV has slack_channel_id; verify against slack_channels table |
| Ric Underwood | USA | `(not loaded — see slack_channels table)` | `C0APJ6D1LLE` | CSV has slack_channel_id; verify against slack_channels table |
| Rifat Chowdhury | USA | `(not loaded — see slack_channels table)` | `C0AT4FS2AFJ` | CSV has slack_channel_id; verify against slack_channels table |
| Rob Traffie | USA | `(not loaded — see slack_channels table)` | `C0AE4MV6N86` | CSV has slack_channel_id; verify against slack_channels table |
| Robert Ferruggia | USA | `(not loaded — see slack_channels table)` | `C0AT1865Z6K` | CSV has slack_channel_id; verify against slack_channels table |
| Rocky Manrique | USA | `(not loaded — see slack_channels table)` | `C09FDRVQS13` | CSV has slack_channel_id; verify against slack_channels table |
| Rubin Linder | USA | `(not loaded — see slack_channels table)` | `C0ADY6NTKHN` | CSV has slack_channel_id; verify against slack_channels table |
| Ruphael G | USA | `(not loaded — see slack_channels table)` | `C09UMFVQNMU` | CSV has slack_channel_id; verify against slack_channels table |
| Russell Broadstone | USA | `(not loaded — see slack_channels table)` | `C09P17CJS9Y` | CSV has slack_channel_id; verify against slack_channels table |
| Ryan Murphy | USA | `(not loaded — see slack_channels table)` | `C0AGD751BDZ` | CSV has slack_channel_id; verify against slack_channels table |
| Saavan Patel | USA | `(not loaded — see slack_channels table)` | `C0A5RNZ2BB9` | CSV has slack_channel_id; verify against slack_channels table |
| Sadiq Sumra | USA | `(not loaded — see slack_channels table)` | `C09F6706L75` | CSV has slack_channel_id; verify against slack_channels table |
| Salman Rahman | USA | `(not loaded — see slack_channels table)` | `C0APECED2HM` | CSV has slack_channel_id; verify against slack_channels table |
| Samantha Bellisfield | USA | `(not loaded — see slack_channels table)` | `C097YTPLKC1` | CSV has slack_channel_id; verify against slack_channels table |
| samee s | USA | `(not loaded — see slack_channels table)` | `C0A0SHLG328` | CSV has slack_channel_id; verify against slack_channels table |
| samhealy09@gmail.com | USA | `(not loaded — see slack_channels table)` | `C09J5S16145` | CSV has slack_channel_id; verify against slack_channels table |
| Samuel Michel | AUS | `(not loaded — see slack_channels table)` | `C0A0FDX1G0N` | CSV has slack_channel_id; verify against slack_channels table |
| Sarah Cherney | USA | `(not loaded — see slack_channels table)` | `C09BN66F14M` | CSV has slack_channel_id; verify against slack_channels table |
| Sean Rounds | USA | `(not loaded — see slack_channels table)` | `C09APUUGX5Y` | CSV has slack_channel_id; verify against slack_channels table |
| Shivam Patel | USA | `(not loaded — see slack_channels table)` | `C097MMAM3K4` | CSV has slack_channel_id; verify against slack_channels table |
| Shyam Srinivas | AUS | `(not loaded — see slack_channels table)` | `C0A0371JYUS` | CSV has slack_channel_id; verify against slack_channels table |
| Sierra Waldrep | USA | `(not loaded — see slack_channels table)` | `C0AVBEBE5ND` | CSV has slack_channel_id; verify against slack_channels table |
| Srilekha Sikhinam | USA | `(not loaded — see slack_channels table)` | `C0AK7B29TEY` | CSV has slack_channel_id; verify against slack_channels table |
| Sunny Ghanathey | USA | `(not loaded — see slack_channels table)` | `C095Q3X3N95` | CSV has slack_channel_id; verify against slack_channels table |
| Swapnil Napuri | USA | `(not loaded — see slack_channels table)` | `C0B08QELQMD` | CSV has slack_channel_id; verify against slack_channels table |
| Temitomi Arenyeka | USA | `(not loaded — see slack_channels table)` | `C09FC41H3C3` | CSV has slack_channel_id; verify against slack_channels table |
| Tina Hussain | USA | `(not loaded — see slack_channels table)` | `C0ALWP2QV16` | CSV has slack_channel_id; verify against slack_channels table |
| Tom Sauer | USA | `(not loaded — see slack_channels table)` | `C0ACL9ELGN5` | CSV has slack_channel_id; verify against slack_channels table |
| Trevor Heck | USA | `(not loaded — see slack_channels table)` | `C0AEEPVK36W` | CSV has slack_channel_id; verify against slack_channels table |
| Vid | USA | `(not loaded — see slack_channels table)` | `C09Q80XQ1KK` | CSV has slack_channel_id; verify against slack_channels table |
| Yeshlin Singh | AUS | `(not loaded — see slack_channels table)` | `C09T2T4PT41` | CSV has slack_channel_id; verify against slack_channels table |
| Yogesh Dhaybar | USA | `(not loaded — see slack_channels table)` | `C0AVD0D9ZPC` | CSV has slack_channel_id; verify against slack_channels table |
| Yohann Navarro | USA | `(not loaded — see slack_channels table)` | `C0ABXUSGUNP` | CSV has slack_channel_id; verify against slack_channels table |

### email (2)

| Client | Tab | Current | CSV value | Reason |
|---|---|---|---|---|
| Cheston Nguyen | USA | `cheston@395northai.com` | `cheston.nguyen@gmail.com` | CSV email differs from Gregory primary; not in alternate_emails |
| Yeshlin Singh | AUS | `yeshlin_singh@yahoo.com` | `yeshlinp@gmail.com` | CSV email differs from Gregory primary; not in alternate_emails |

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
| Alex Crosby | USA | `null` | `Aleks` | Aleks-owned (M4 Chunk C carry-over — Scott reassignment) |
| Colin Hill | USA | `null` | `Aleks` | Aleks-owned (M4 Chunk C carry-over — Scott reassignment) |
| Jose Trejo | USA | `null` | `Aleks` | Aleks-owned (M4 Chunk C carry-over — Scott reassignment) |
| Ming-Shih Wang | USA | `null` | `Aleks` | Aleks-owned (M4 Chunk C carry-over — Scott reassignment) |


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

