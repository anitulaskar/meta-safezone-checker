# Meta Safe-Zone Checker v2

A Streamlit web app for checking Meta creative safe-zone compliance.

## What changed in v2

This version uses 2026-oriented Meta creative best practices from the Billo safe-zone guide:

- 9:16 vertical creative should use a unified conservative safe zone when it may run across Reels and Stories.
- Critical elements should avoid the top 14%, bottom 20%-35%, and side edges.
- Conservative production QA uses the full 35% bottom risk zone and keeps critical elements in the center 80% horizontally.
- Feed images should default to 4:5, such as 1080×1350 or 1440×1800.
- 1:1 Feed is still treated as supported/legacy, but it is marked REVIEW rather than ideal.
- Background imagery may bleed; headline, logo, CTA, price, and legal copy should stay inside the green safe zone.

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

1. Create or open your GitHub repo.
2. Upload these files to the repo root.
3. Go to Streamlit Community Cloud.
4. Click New app.
5. Choose your repo.
6. Set main file path to `app.py`.
7. Deploy.

## Local run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Notes

OCR is used to detect text. Very small logos or stylized marks may require manual review.
