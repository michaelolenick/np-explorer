"""Step 1 of discovery: scan EDGAR quarterly form indexes for student loan ABS filers.

Writes ~/sla-data/index_hits.tsv: form, company, cik, date, path for every filing
whose company name looks like a student loan securitization vehicle or sponsor.
"""

import gzip
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from loader import sec  # noqa: E402

NAME = re.compile(r"STUDENT LOAN|EDUCATION LOAN|EDUCATION FUNDING|STUDENT FUNDING|PRIVATE EDUCATION|"
                  r"COLLEGIATE|ACCESS GROUP|GOAL CAPITAL|EDUCATION LOANS INC|SLM |SLM$|NAVIENT|NELNET|"
                  r"SMB PRIVATE|SOFI|COLLEGE AVE|BRAZOS|EDLINC|STUDENT LOAN FINANCE|FIRST MARBLEHEAD|"
                  r"COLLEGE LOAN|EDUCATIONAL FUNDING|HIGHER EDUCATION|KEYCORP STUDENT|SLC STUDENT|"
                  r"CHASE EDUCATION|WACHOVIA STUDENT|PNC STUDENT|EDUCATION CREDIT|STUDENT ASSET|"
                  r"GCO EDUCATION|NORTHSTAR|PHEAA|EDSOUTH|EDFINANCIAL|ACADEMIC LOAN|NEXTSTUDENT|"
                  r"COMMONBOND|EARNEST|LAUREL ROAD|CITIZENS STUDENT|MRU STUDENT|EDUCATION LENDING", re.I)
FORMS = {"10-D", "10-D/A", "10-K", "10-K/A", "424B5", "424H", "424B3", "424B2", "ABS-15G", "ABS-15G/A",
         "ABS-EE", "8-K", "SF-3", "SF-1", "S-3", "S-3/A", "FWP", "15-15D", "15-12G", "D"}


def main():
    out = open(sec.CACHE / "index_hits.tsv", "w")
    n = 0
    for year in range(1994, 2027):
        for q in range(1, 5):
            url = f"{sec.WWW}/Archives/edgar/full-index/{year}/QTR{q}/form.gz"
            try:
                path = sec.fetch_path(url)
            except sec.NotFound:
                continue
            # Stream: the cache file is our gzip around the SEC's gzip; never hold the whole index.
            with gzip.open(path, "rb") as outer, gzip.GzipFile(fileobj=outer, mode="rb") as inner:
                # form.idx is fixed width: the form type is the first 12 characters. Check it first
                # (cheap) so the name pattern only runs on the few lines with a form we want.
                lines = [l.decode("latin-1") for l in inner
                         if l[:12].decode("latin-1").strip() in FORMS and NAME.search(l.decode("latin-1"))]
            for line in lines:
                if not line[:1].strip() or line.startswith(("Form Type", "----")):
                    continue
                parts = re.split(r"\s{2,}", line.strip())
                if len(parts) < 5:
                    continue
                form, company, cik, date, path = parts[0], " ".join(parts[1:-3]), parts[-3], parts[-2], parts[-1]
                if form in FORMS and NAME.search(company):
                    out.write(f"{form}\t{company}\t{cik}\t{date}\t{path}\n")
                    n += 1
            print(year, q, n, flush=True)
    out.close()


if __name__ == "__main__":
    main()
