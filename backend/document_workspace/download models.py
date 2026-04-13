from pathlib import Path
from transformers import TrOCRProcessor, VisionEncoderDecoderModel

MODELS = {
   
    "trocr-large-handwritten": "microsoft/trocr-large-handwritten",
}

SAVE_DIR = Path(__file__).parent / "models"
SAVE_DIR.mkdir(exist_ok=True)

for name, hub_id in MODELS.items():
    save_path = SAVE_DIR / name

    if save_path.exists():
        print(f"[SKIP] {name} already exists")
        continue

    print(f"[DOWNLOADING] {hub_id}")

    processor = TrOCRProcessor.from_pretrained(hub_id)
    model = VisionEncoderDecoderModel.from_pretrained(hub_id)

    processor.save_pretrained(save_path)
    model.save_pretrained(save_path)

    print(f"[DONE] Saved to {save_path}")

print("\nAdd this to your .env:")
print("TROCR_HANDWRITTEN_PATH=./models/trocr-large-handwritten")