import streamlit as st
import pandas as pd
from checker import check_creative, make_zip, image_to_bytes

st.set_page_config(
    page_title="Meta Safe-Zone Checker",
    page_icon="✅",
    layout="wide",
)

st.title("Meta Creative Safe-Zone Checker")
st.caption("Text/logo-only safe-zone review for Feed, Reels, and Stories. Photo/background bleed is allowed.")

with st.sidebar:
    st.header("Rules")
    st.write("**Feed:** 10% caution zone on all sides")
    st.write("**Reels:** 14% top, 35% bottom, 6% sides")
    st.write("**Stories:** 14% top, 20% bottom, 6% sides")
    st.divider()
    placement_mode = st.radio(
        "Placement detection",
        ["Auto-detect from filename/shape", "Force Feed", "Force Reels", "Force Stories"],
        index=0,
    )
    st.caption("Tip: include Reels, Stories, or Feed in filenames for better auto-detection.")

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
    "This tool checks whether detected text is inside the green safe-zone boundary. "
    "Logos and very small text may need manual review if OCR does not detect them."
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
                "Status": r.status,
                "Size": f"{r.width}×{r.height}",
                "Aspect": r.aspect_ratio_status,
                "Resolution": r.resolution_status,
                "Text/Logo": r.text_logo_status,
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
            st.write(f"**Placement:** {r.placement.upper()}  |  **Size:** {r.width}×{r.height}")
            st.write(r.reason)
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
        "Upload your PNG/JPG/WebP creative files. The app will check Feed, Reels, or Stories safe-zone compliance "
        "and generate annotated previews."
    )

    st.code(
        """Recommended filenames:
Ad1_Feed.png
Ad1_Reels.png
Ad1_Stories.png""",
        language="text",
    )
