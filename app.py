
import streamlit as st
import pandas as pd
from checker import check_creative, make_zip, image_to_bytes, RULESETS

st.set_page_config(
    page_title="Meta Safe-Zone Checker",
    page_icon="✅",
    layout="wide",
)

st.title("Meta Creative Safe-Zone Checker")
st.caption("Text/logo-only safe-zone review for Feed, Reels, and Stories. Photo/background bleed is allowed.")

with st.sidebar:
    st.header("Safe-zone mode")
    ruleset_label_to_key = {
        RULESETS["unified_9x16_conservative"]["label"]: "unified_9x16_conservative",
        RULESETS["stories_only_relaxed"]["label"]: "stories_only_relaxed",
    }
    selected_ruleset_label = st.radio(
        "Choose rules",
        list(ruleset_label_to_key.keys()),
        index=0,
    )
    ruleset_key = ruleset_label_to_key[selected_ruleset_label]
    st.caption(RULESETS[ruleset_key]["description"])

    st.divider()
    st.header("Placement")
    placement_mode = st.radio(
        "Placement detection",
        ["Auto-detect from filename/shape", "Force Feed", "Force Reels", "Force Stories"],
        index=0,
    )
    st.caption("Tip: include Reels, Stories, or Feed in filenames for better auto-detection.")

    st.divider()
    st.header("Best-practice rules")
    st.write("**9:16 unified:** 14% top, 35% bottom, center 80% horizontal")
    st.write("**Stories-only relaxed:** 14% top, 14% bottom")
    st.write("**Feed image:** 4:5 preferred; 1:1 is review/legacy")
    st.write("**Critical elements:** headline, logo, CTA, price, legal copy")

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
    "This tool checks whether detected text stays inside the green safe-zone boundary. "
    "Photography/background can bleed outside. Logos and very small text may need manual review if OCR does not detect them."
)

if uploaded:
    results = []
    with st.spinner("Checking creatives..."):
        for file in uploaded:
            result = check_creative(
                file.getvalue(),
                file.name,
                placement=placement_map[placement_mode],
                ruleset_key=ruleset_key,
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
        "Upload PNG/JPG/WebP creative files. The app will check Feed, Reels, or Stories safe-zone compliance "
        "and generate annotated previews with fix suggestions."
    )

    st.code(
        """Recommended filenames:
Ad1_Feed_4x5.png
Ad1_Reels_9x16.png
Ad1_Stories_9x16.png""",
        language="text",
    )
