
import streamlit as st
import pandas as pd
from checker import check_creative, make_zip, image_to_bytes

st.set_page_config(
    page_title="Meta Safe-Zone Checker",
    page_icon="✅",
    layout="wide",
)

st.title("Meta Creative Safe-Zone Checker")
st.caption("Production rules: 1:1 Feed and 9:16 Reels/Stories. Photo/background bleed is allowed; text/logo/CTA/legal copy must stay safe.")

with st.sidebar:
    st.header("Rules")
    st.write("**Feed:** 1:1 only")
    st.write("Safe zone: outer 10% edge zone is risky for text/logo/CTA.")
    st.write("**Reels:** 9:16 only")
    st.write("Safe zone: 14% top, 35% bottom, 6% sides.")
    st.write("**Stories:** 9:16 only")
    st.write("Safe zone: 14% top, 20% bottom, 6% sides.")
    st.divider()
    st.warning("Expected Meta CTA/UI overlap is checked for Reels and Stories. Text/logo/CTA in that bottom zone is marked FAIL.")
    st.divider()
    placement_mode = st.radio(
        "Placement detection",
        ["Auto-detect from filename/shape", "Force Feed", "Force Reels", "Force Stories"],
        index=0,
    )
    st.caption("Tip: include Feed, Reels, or Stories in filenames for better auto-detection.")

placement_map = {
    "Auto-detect from filename/shape": None,
    "Force Feed": "feed",
    "Force Reels": "reels",
    "Force Stories": "stories",
}

uploaded = st.file_uploader(
    "Upload creative images",
    type=["png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
)

st.info(
    "This checker is text/logo-only. Images and background design can extend beyond the safe zone. "
    "Critical elements include headline, logo, CTA, price, promo copy, and legal copy."
)

if uploaded:
    results = []
    with st.spinner("Checking creatives..."):
        for file in uploaded:
            result = check_creative(
                file.getvalue(),
                file.name,
                placement=placement_map[placement_mode],
            )
            results.append(result)

    rows = []
    for r in results:
        rows.append(
            {
                "File": r.filename,
                "Placement": r.placement,
                "Rule": r.rule_label,
                "Status": r.status,
                "Size": f"{r.width}×{r.height}",
                "Aspect": r.aspect_ratio_status,
                "Resolution": r.resolution_status,
                "Text/Logo": r.text_logo_status,
                "Meta CTA/UI": r.meta_cta_status,
                "Suggestions": "; ".join(r.suggestions),
                "Reason": r.reason,
            }
        )

    st.subheader("Summary")
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    zip_bytes = make_zip(results)
    st.download_button(
        "Download annotated previews + CSV",
        data=zip_bytes,
        file_name="meta_safezone_report.zip",
        mime="application/zip",
    )

    st.subheader("Annotated previews")

    for r in results:
        status_icon = {
            "PASS": "🟢",
            "FAIL": "🔴",
            "REVIEW": "🟡",
        }.get(r.status, "⚪")

        with st.container(border=True):
            st.markdown(f"### {status_icon} {r.status} — {r.filename}")
            st.write(f"**Placement:** {r.placement.upper()}  |  **Rule:** {r.rule_label}  |  **Size:** {r.width}×{r.height}")
            st.write(r.reason)
            st.markdown("**Suggestions**")
            for s in r.suggestions:
                st.write(f"- {s}")
            st.image(r.annotated_image, use_container_width=True)
            st.download_button(
                f"Download annotated preview — {r.filename}",
                data=image_to_bytes(r.annotated_image),
                file_name=f"{r.filename.rsplit('.', 1)[0]}_annotated.jpg",
                mime="image/jpeg",
                key=f"download_{r.filename}",
            )
else:
    st.subheader("How to use")
    st.write(
        "Upload PNG/JPG/WebP creative files. The app will check 1:1 Feed or 9:16 Reels/Stories safe-zone compliance "
        "and generate annotated previews with fix suggestions."
    )

    st.code(
        """Recommended filenames:
Ad1_Feed_1x1.png
Ad1_Reels_9x16.png
Ad1_Stories_9x16.png""",
        language="text",
    )
