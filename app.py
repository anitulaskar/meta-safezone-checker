
import streamlit as st
import pandas as pd
from checker import check_creative, make_zip, image_to_bytes

st.set_page_config(
    page_title="Meta Safe-Zone Checker",
    page_icon="✅",
    layout="wide",
)

st.title("Meta Creative Safe-Zone Checker")
st.caption("Updated rule: safe-zone pass/fail applies only to 9:16 ads. 1:1 and 4:5 Feed safe-zone checks are disabled.")

with st.sidebar:
    st.header("9:16 safe-zone rules")
    st.write("Applies to Stories, Reels, Feed 9:16, and Facebook in-stream reels.")
    st.write("- Top: 14%")
    st.write("- Bottom: 35%")
    st.write("- Sides: 6%")
    st.write("- Extra lower-right guardrail: right 21% × bottom 40%")
    st.divider()
    st.header("1:1 and 4:5 Feed")
    st.success("Safe-zone pass/fail disabled for these formats per current workflow.")
    st.write("The app still checks aspect ratio and resolution.")
    st.divider()
    st.header("Text overlay best practices")
    st.write("- Use clean, large, high-contrast type")
    st.write("- Don’t obstruct key visuals")
    st.write("- Avoid too many messages")
    st.write("- Keep key text/logos/CTAs inside 9:16 safe zones")
    st.divider()

    placement_mode = st.radio(
        "Placement detection",
        [
            "Auto-detect from filename/shape",
            "Force 9:16 safe-zone check",
            "Force Feed 1:1",
            "Force Feed 4:5",
        ],
        index=0,
    )

placement_map = {
    "Auto-detect from filename/shape": None,
    "Force 9:16 safe-zone check": "nine_sixteen",
    "Force Feed 1:1": "feed_1x1",
    "Force Feed 4:5": "feed_4x5",
}

uploaded = st.file_uploader(
    "Upload creative images",
    type=["png", "jpg", "jpeg", "webp"],
    accept_multiple_files=True,
)

st.info(
    "The checker focuses on critical text/logo/CTA/legal-copy containment for 9:16 assets. "
    "Photography, background design, and visual bleed are allowed outside safe zones. "
    "OCR can miss stylized logos and tiny copy, so final visual review is still recommended."
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
                "Safe zone": r.safe_zone_status,
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
        "Upload PNG/JPG/WebP creative files. 9:16 assets will get the updated Meta safe-zone guardrail check. "
        "1:1 and 4:5 Feed assets will not be failed for safe zones."
    )

    st.code(
        """Recommended filenames:
Ad1_Reels_9x16.png
Ad1_Stories_9x16.png
Ad1_Feed_1x1.png
Ad1_Feed_4x5.png""",
        language="text",
    )
