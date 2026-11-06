import io
import zipfile
import streamlit as st
import pymupdf as fitz
from PIL import Image

# --------------------------------------------------------------------------
# Page Configuration & Styling
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="PDF 1.7 Converter (< 1MB)",
    page_icon="📄",
    layout="wide"
)

st.title("📄 PDF to %PDF-1.7 Converter")
st.markdown("""
Convert any PDF to **%PDF-1.7**, locked to **Portrait**, in full **Colour**, and compressed strictly to **less than 1 MB** (Depository & RTA Compliant).
""")

# --------------------------------------------------------------------------
# Conversion Engine
# --------------------------------------------------------------------------
MAX_BYTES = 1_000_000  # Strictly less than 1 MB
SETTINGS = [
    (150, 85), (120, 75), (100, 65), (85, 55), (72, 48),
    (60, 40), (48, 32), (40, 28), (36, 22)
]

def starting_setting(page_count):
    if page_count <= 5: return 0
    if page_count <= 15: return 1
    if page_count <= 30: return 2
    if page_count <= 60: return 3
    return 4

def render_attempt_in_memory(source_doc, dpi, quality):
    output_doc = fitz.open()
    try:
        for page in source_doc:
            rect = page.rect
            if rect.width <= 0 or rect.height <= 0:
                raise ValueError("A page has invalid dimensions")

            # Enforce Portrait orientation
            width, height = sorted((rect.width, rect.height))
            new_page = output_doc.new_page(width=width, height=height)

            pix = page.get_pixmap(
                matrix=fitz.Matrix(dpi / 72, dpi / 72),
                colorspace=fitz.csRGB,
                alpha=False,
                annots=True
            )
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=quality, optimize=True)

            new_page.insert_image(new_page.rect, stream=buffer.getvalue(), keep_proportion=True)

        return output_doc.tobytes(garbage=4, deflate=True)
    finally:
        output_doc.close()

def convert_pdf_bytes(file_bytes):
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        if doc.needs_pass:
            raise ValueError("File is password-protected. Unlock it first.")
        pages = doc.page_count
        if pages == 0:
            raise ValueError("Document has 0 pages.")

        start_idx = starting_setting(pages)
        for idx in range(start_idx, len(SETTINGS)):
            dpi, quality = SETTINGS[idx]
            out_bytes = render_attempt_in_memory(doc, dpi, quality)
            size = len(out_bytes)

            if size < MAX_BYTES:
                # Validate PDF 1.7 header
                if not out_bytes.startswith(b"%PDF-1.7"):
                    raise RuntimeError("Header is not %PDF-1.7")
                return out_bytes, size, dpi, pages

        # Fallback to lowest setting if still oversized
        dpi, quality = SETTINGS[-1]
        out_bytes = render_attempt_in_memory(doc, dpi, quality)
        return out_bytes, len(out_bytes), dpi, pages

# --------------------------------------------------------------------------
# UI & Workflow
# --------------------------------------------------------------------------
uploaded_files = st.file_uploader(
    "Upload one or more PDF files",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    st.info(f"📁 {len(uploaded_files)} file(s) selected for processing.")
    
    if st.button("🚀 Convert to PDF 1.7 (< 1 MB)", type="primary"):
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for idx, uploaded_file in enumerate(uploaded_files):
            file_name = uploaded_file.name
            orig_size_kb = len(uploaded_file.getvalue()) / 1024
            status_text.text(f"Processing ({idx+1}/{len(uploaded_files)}): {file_name} ...")

            try:
                converted_bytes, final_size, dpi, pages = convert_pdf_bytes(uploaded_file.getvalue())
                final_size_kb = final_size / 1024
                is_under_1mb = final_size < MAX_BYTES
                version_str = converted_bytes[:8].decode("latin-1", errors="ignore")

                results.append({
                    "name": file_name,
                    "orig_size": f"{orig_size_kb:.1f} KB",
                    "final_size": f"{final_size_kb:.1f} KB",
                    "status": "✅ Success (< 1MB)" if is_under_1mb else "⚠️ Warning (> 1MB)",
                    "header": version_str,
                    "data": converted_bytes,
                    "error": None
                })
            except Exception as e:
                results.append({
                    "name": file_name,
                    "orig_size": f"{orig_size_kb:.1f} KB",
                    "final_size": "-",
                    "status": "❌ Failed",
                    "header": "-",
                    "data": None,
                    "error": str(e)
                })

            progress_bar.progress((idx + 1) / len(uploaded_files))

        status_text.success("🎉 Processing complete!")

        # ------------------------------------------------------------------
        # Display Results Table
        # ------------------------------------------------------------------
        st.subheader("Conversion Summary")
        table_data = [
            {
                "File Name": r["name"],
                "Original Size": r["orig_size"],
                "Output Size": r["final_size"],
                "PDF Header": r["header"],
                "Status": r["status"]
            }
            for r in results
        ]
        st.dataframe(table_data, use_container_width=True)

        # ------------------------------------------------------------------
        # Download Buttons
        # ------------------------------------------------------------------
        successful_conversions = [r for r in results if r["data"] is not None]

        if len(successful_conversions) > 1:
            # Create a single ZIP archive for bulk download
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for r in successful_conversions:
                    zip_file.writestr(r["name"], r["data"])
            
            st.download_button(
                label="📦 Download All Converted PDFs (ZIP)",
                data=zip_buffer.getvalue(),
                file_name="Converted_PDF_1.7_Documents.zip",
                mime="application/zip",
                type="primary"
            )

        st.subheader("Individual Downloads")
        cols = st.columns(3)
        for i, r in enumerate(successful_conversions):
            with cols[i % 3]:
                st.download_button(
                    label=f"⬇️ {r['name']}",
                    data=r["data"],
                    file_name=r["name"],
                    mime="application/pdf",
                    key=f"dl_{i}"
                )