# Zillow to Census Metro Crosswalk Report

**886 of 907 Zillow metros matched (97.7%).**

| Match method | Metros | Meaning |
|---|---|---|
| both_agree | 669 | Name match and county vote point to the same metro |
| name_only | 197 | Matched by principal city and state |
| unmatched | 21 | No match; excluded from joined analysis |
| county_vote_only | 18 | Matched through the metro's counties |
| manual_override | 2 | Hand-checked in docs/crosswalk_overrides.csv |

## Needs review

Add fixes to `docs/crosswalk_overrides.csv` (columns: zillow_region_id, cbsa_code, note).

| Zillow ID | Zillow name | Name match | County vote | Chosen CBSA title |
|---|---|---|---|---|
| 394932 | Ogdensburg, NY |  |  |  |
| 753877 | Cullowhee, NC |  |  |  |
| 394989 | Point Pleasant, WV |  |  |  |
| 394608 | Fort Polk South, LA |  |  |  |
| 394819 | Malone, NY |  |  |  |
| 753866 | Big Stone Gap, VA |  |  |  |
| 753878 | Dayton, TN |  |  |  |
| 753892 | Jackson, OH |  |  |  |
| 394481 | Coffeyville, KS |  |  |  |
| 394383 | Berlin, NH |  |  |  |
| 394921 | North Vernon, IN |  |  |  |
| 394381 | Bennettsville, SC |  |  |  |
| 395214 | Wauchula, FL |  |  |  |
| 394841 | Maysville, KY |  |  |  |
| 394676 | Helena, AR |  |  |  |
| 753880 | Fairfield, IA |  |  |  |
| 394767 | Lamesa, TX |  |  |  |
| 394642 | Grants, NM |  |  |  |
| 394706 | Indianola, MS |  |  |  |
| 394965 | Parsons, KS |  |  |  |
| 786253 | Brownsville, TN |  |  |  |
