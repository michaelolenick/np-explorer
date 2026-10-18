# Fundraising event classification

How the two event board groups decide which events count. The code is `app/event_class.py`; the
table it fills is `event_classes` (built by `load.py event-classes`, and nightly after new filings).
Keep this file and the code in step.

No AI and no judgment calls at run time: fixed keyword rules applied to three things the return
itself reports.

1. The event's own description (Schedule G Part II, columns a and b: the two largest events by
   gross receipts).
2. The organization's NTEE code.
3. The organization's name.

The labels describe the words on the form, not the event. They are not a finding that anything is
improper.

## The two groups

| Group | Board title | Who is in it |
|---|---|---|
| A | Fundraising event costs: *Galas, parties and soirees* | Organization-years with an itemized event whose description has a party-style word |
| B | Fundraising events beyond the mission: *The Side Show* | Organization-years with fundraising events, except where every itemized event is the charity's own program |

Group B contains everything in group A. Unclear calls stay in B and are flagged. Events the form
doesn't itemize (the "all other events" column) count as fundraising events, because the form defines
them that way.

## Step 1: category

The first rule that matches wins, in this order.

| Order | Category | Words (whole words, any case) |
|---|---|---|
| 0 | hospitality | egg hunt, Easter egg hunt, scavenger hunt, treasure hunt (party games, not hunting) |
| 1 | raffle/auction | raffle, lottery, drawing, bingo, casino, poker, 50/50, sweepstakes, auction, calendar, split the pot |
| 2 | gala/party | gala, ball, soiree, party, dinner, luncheon, lunch, reception, benefit, banquet, cocktail, brunch, fete, masquerade, cabaret, dance, prom, tea, wine, tasting, oyster roast, crawfish, cookout, cook-off, BBQ, barbecue, fish fry, feast, casino night, derby party |
| 3 | sports outing | golf, tournament, classic, scramble, tee, fishing, fish, bass, angler, rodeo, shoot, shootout, clays, skeet, trap, hunt, hunting, bowling, tennis, pickleball, softball, baseball, basketball, volleyball, hockey, regatta, sailing, derby |
| 4 | walk/run/ride | walk, walkathon, run, 5K, 10K, half marathon, marathon, race, relay, ride, bike, cycling, trek, climb, plunge, swim, triathlon, ruck, stair |
| 5 | hospitality | hospitality, tailgate, suite, concert, festival, fair, show, tour, cruise, carnival, picnic, social, mixer, happy hour, parade, exhibit, performance |
| 6 | other | anything else ("FUNDRAISING", "SPECIAL EVENTS", "CONCESSIONS", "VARIOUS") |

**Gala flag (group A):** the description contains any gala/party word above. Auctions count, so a
"Wine Auction" is category raffle/auction and still a gala.

## Step 2: related to the mission?

Schedule G Part II lists fundraising events by definition, so the default is **not the program**.
An event is the program only when the organization is that kind of organization.

| Category | Program (left out of B) | Unclear (kept in B, flagged) | Otherwise |
|---|---|---|---|
| sports outing | NTEE major group N (sports and recreation), or the organization's name names the sport the event is (an anglers club's bass tournament) | Conservation or wildlife organization (NTEE C or D) running a hunting, fishing or shooting event | Fundraising outing |
| walk/run/ride | NTEE N and the name says running, cycling, track, triathlon, swimming, athletics or sports | Any other NTEE N organization: the race may be its program | Fundraising walk, run or ride |
| hospitality | Arts and culture (NTEE A) holding a concert, festival, show, performance, exhibit or tour; or an organization named as a fair, exposition or rodeo holding one | none | Fundraising hospitality or entertainment |
| gala/party, raffle/auction, other | never | never | Fundraising event |

**Health-charity walks and runs are fundraising events, not the program.** The Heart Walk, Relay for
Life and Light the Night raise money for medical work; walking isn't the work. They are in group B.

Each row in `event_classes` keeps its reason in plain words (for example "NTEE E30, not a sports
organization: fundraising outing"). The Biggest single events board shows that reason.

## Counts (built 2026-10-18, all years, 1,602,982 itemized events)

| Category | Events | Program | Unclear | Not the program | Gala flag |
|---|---:|---:|---:|---:|---:|
| other | 783,045 | 0 | 0 | 783,045 | 0 |
| gala/party | 293,142 | 0 | 0 | 293,142 | 293,142 |
| sports outing | 251,868 | 20,528 | 508 | 230,832 | 0 |
| raffle/auction | 112,396 | 0 | 0 | 112,396 | 75,621 |
| hospitality | 88,688 | 7,899 | 0 | 80,789 | 7 |
| walk/run/ride | 73,843 | 927 | 2,469 | 70,447 | 0 |
| **Total** | **1,602,982** | **29,354** | **2,977** | **1,570,651** | **368,770** |

In group B: 1,573,628 events (98.2%). Gala flag: 368,770 events (23.0%).

## Calls worth a second look

- **Special Olympics polar bear plunges** (NTEE N72) are unclear: the organization is a sports
  organization, but the plunge is a fundraiser, not Special Olympics competition. The rule keeps them
  in B, flagged.
- **Coastal Conservation Association fishing tournaments** (NTEE C01) are unclear: angling is close
  to the group's cause. They stay in B, flagged.
- **"Other" is the biggest category**, at about half of all events. Most descriptions are just
  "FUNDRAISING", "SPECIAL EVENTS" or "CONCESSIONS". They are in B, because the form calls them
  fundraising events, and never in A.
- **Name matches count as program.** 6,522 events are program because the organization's name names
  the sport (a golf association's golf tournament). A charity that happens to have "Golf" in its name
  would be counted as program too.

## Changing the rules

Edit `app/event_class.py`, add a case to `tests/test_event_class.py`, update this file, then run
`load.py event-classes` and `load.py boards --only <the ten event slugs>`.
