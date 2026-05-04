# Meta Safe-Zone Checker v3

A Streamlit web app for checking Meta creative safe-zone compliance.

## Production formats

This version uses only the current formats requested:

- Feed: 1:1
- Reels: 9:16
- Stories: 9:16

No 4:5 Feed requirement is applied in this version.

## Safe-zone rules

- Feed: outer 10% caution zone on all sides.
- Reels: 14% top, 35% bottom, 6% sides.
- Stories: 14% top, 20% bottom, 6% sides.

## Expected Meta CTA/UI overlap

The app explicitly checks the lower UI/CTA region for Reels and Stories:

- Reels: bottom 35%
- Stories: bottom 20%

Detected text/logo/CTA in those regions is marked FAIL.

## What counts

The checker focuses on text/logo/CTA/legal-copy containment.

Photography, food imagery, background design, and visual bleed are allowed outside the safe zone.

## Files to upload to GitHub

Upload these files to the root of your GitHub repo:

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

## Local run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Notes

OCR is used to detect text. Very small logos, stylized logos, and low-contrast legal copy may require manual review.
