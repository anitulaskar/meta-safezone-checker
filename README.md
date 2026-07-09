# Meta Safe-Zone Checker v5 — 9:16 Only Safe-Zone Update

This Streamlit app checks Meta creative safe zones.

## Important behavior

Safe-zone pass/fail applies **only to 9:16 ads**.

For 1:1 and 4:5 Feed assets, safe-zone checking is disabled. The app still checks format and resolution.

## 9:16 safe-zone rules

For 9:16 ads in Stories, Reels, Feed, and Facebook in-stream reels:

- Top: 14%
- Bottom: 35%
- Sides: 6%
- Extra lower-right guardrail: right 21% × bottom 40%

Critical text, logos, CTAs, price/promo copy, and legal copy should remain outside these guardrails.

## What counts

The checker focuses on critical text/logo/CTA/legal-copy containment.

Photography, food imagery, background design, and visual bleed are allowed outside the safe zone.

## Files to upload to GitHub

Upload/replace these files at the root of your GitHub repo:

```text
app.py
checker.py
requirements.txt
packages.txt
README.md
.gitignore
```

## Deploy on Streamlit

1. Upload/replace these files in your GitHub repo.
2. Commit changes.
3. Streamlit should redeploy automatically.
4. If it does not, open Streamlit and click reboot/redeploy.

## Notes

OCR is used to detect text. OCR can miss stylized logos and tiny copy, so final visual review is still recommended.
