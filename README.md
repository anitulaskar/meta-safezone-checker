# Meta Safe-Zone Checker

A Streamlit web app for checking Meta creative safe-zone compliance.

## What it checks

- Feed 1:1
- Reels 9:16
- Stories 9:16
- Aspect ratio
- Resolution
- Text/logo safe-zone containment

Background images and photography are allowed to bleed outside the safe zone. This app focuses on text/logo-only compliance.

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

1. Create a GitHub repo.
2. Upload these files to the repo.
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
