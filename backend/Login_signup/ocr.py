import fitz  # PyMuPDF
import pytesseract
import cv2
import numpy as np
from PIL import Image
import io

# Optional if tesseract not in PATH
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


# ================= OCR FUNCTION =================
def ocr_pil_image(pil_image):
    try:
        open_cv_image = np.array(pil_image)
        gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)

        text = pytesseract.image_to_string(gray)
        return text
    except Exception as e:
        return f"[OCR ERROR: {str(e)}]\n"


# ================= PDF PROCESSING =================
def extract_pdf_hybrid(pdf_path):

    doc = fitz.open(pdf_path)
    final_text = ""

    for page_index in range(len(doc)):
        page = doc[page_index]

        final_text += f"\n========== PAGE {page_index+1} ==========\n"

        # -------- Extract normal text --------
        text = page.get_text()
        if text.strip():
            final_text += "\n[TEXT LAYER]\n"
            final_text += text

        # -------- Extract images and OCR --------
        image_list = page.get_images(full=True)

        if image_list:
            final_text += "\n[IMAGE OCR]\n"

        for img_index, img in enumerate(image_list):

            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]

            pil_image = Image.open(io.BytesIO(image_bytes))

            ocr_text = ocr_pil_image(pil_image)

            final_text += f"\n--- Image {img_index+1} ---\n"
            final_text += ocr_text

    return final_text


# ================= MAIN =================
if __name__ == "__main__":

    pdf_file = input("Enter PDF path: ")

    result = extract_pdf_hybrid(pdf_file)

    with open("output_text.txt", "w", encoding="utf-8") as f:
        f.write(result)

    print("✅ Extraction completed! Saved as output_text.txt")
