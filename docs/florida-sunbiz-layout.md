# Florida Sunbiz quarterly corporate file (cordata.zip)

Source: Florida Division of Corporations public SFTP, `/Public/doc/Quarterly/Cor/cordata.zip` (quarterly: January,
April, July, October). How to download it and load it: loader/florida_registry.py (`.venv/bin/python -m loader.florida_registry`, `--limit N`
and `--member N` for test runs).

- Members `cordata0.txt` .. `cordata9.txt`, about 1.87 GB each, 18.7 GB in all, compressed with Deflate64 (method 9).
  Python's zipfile can't read Deflate64: stream each member with `unzip -p cordata.zip cordataN.txt`.
- One record per line: 1,440 characters, then CR LF (1,442 bytes on disk). No header row. Latin-1.
- Layout: the state's definition at https://dos.sunbiz.org/data-definitions/cor.html (not shipped in the archive),
  checked against 12 records from cordata0, cordata5 and cordata9 on 2026-10-24.
- Dates are MMDDYYYY. Blank fields are spaces.

## Record (positions are 1-based, inclusive)

| # | Field | Start | Length | End | Notes |
|---|---|---|---|---|---|
| 1 | Document (corporation) number | 1 | 12 | 12 | e.g. L16000216990 (L = LLC, P = profit corp, N = nonprofit, F = foreign, ...) |
| 2 | Entity name | 13 | 192 | 204 | |
| 3 | Status | 205 | 1 | 205 | A active, I inactive |
| 4 | Filing type | 206 | 15 | 220 | DOMP domestic profit, DOMNP domestic nonprofit, FLAL Florida LLC, FORP foreign profit, ... |
| 5-10 | Principal address 1, address 2, city, state, ZIP, country | 221 | 126 | 346 | 42, 42, 28, 2, 10, 2 |
| 11-16 | Mailing address 1, address 2, city, state, ZIP, country | 347 | 126 | 472 | 42, 42, 28, 2, 10, 2 |
| 17 | File (formation) date | 473 | 8 | 480 | MMDDYYYY |
| 18 | FEI number (EIN) | 481 | 14 | 494 | sometimes "NOT APPLICABLE" |
| 19 | More than six officers flag | 495 | 1 | 495 | Y: officers beyond the six blocks aren't in the file |
| 20 | Last transaction date | 496 | 8 | 503 | MMDDYYYY |
| 21 | State or country of incorporation | 504 | 2 | 505 | |
| 22-30 | Annual report year and date, three times | 506 | 39 | 544 | year 4, filler 1, date 8 (MMDDYYYY) |
| 31 | Registered agent name | 545 | 42 | 586 | a person: last 20, first 14, middle 8 |
| 32 | Registered agent type | 587 | 1 | 587 | P person, C corporation |
| 33-36 | Registered agent address, city, state, ZIP+4 | 588 | 81 | 668 | 42, 28, 2, 9 |
| 37-78 | Officers: six blocks of 128 | 669 | 768 | 1436 | blocks start at 669, 797, 925, 1053, 1181, 1309 |
| 79 | Filler | 1437 | 4 | 1440 | |

## Officer block (128 characters, positions relative to the block start)

| Field | Start | Length | Notes |
|---|---|---|---|
| Title | 1 | 4 | free text, truncated: MGR, MGRM, AMBR, P, VP, D, "P, T", Mana, OWNE, Pres |
| Type | 5 | 1 | P person, C corporation |
| Name | 6 | 42 | a person: last 20, first 14, middle 8 |
| Address | 48 | 42 | |
| City | 90 | 28 | |
| State | 118 | 2 | |
| ZIP+4 | 120 | 9 | |

Officers go to a child table (biz_people), one row per non-blank block, in block order.
