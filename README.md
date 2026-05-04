# Meta Safe-Zone Checker v4

A Streamlit web app for checking Meta creative safe-zone compliance.

## Production formats

This version uses only:

- Feed: 1:1
- Reels: 9:16
- Stories: 9:16

## Safe-zone rules

- Feed: critical text/logo inside central 80% of the 1:1 frame.
- Reels: 14% top, 20% bottom, 6% sides.
- Stories: 14% top, 20% bottom, 6% sides.

## CTA overlap behavior

This version removes CTA-overlap failure logic.

Meta CTA buttons are rendered by the platform UI and are not treated as part of the uploaded creative. The checker focuses on the creative itself.

## What counts

The checker focuses on text/logo/CTA/legal-copy containment.

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
