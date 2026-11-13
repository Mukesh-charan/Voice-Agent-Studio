from PIL import Image
import os

artifact_dir = r"C:\Users\Sanjjey Arumugam\.gemini\antigravity-ide\brain\c7f8c7c6-1e2b-4583-ad3a-c21b878c75e8"
im13 = Image.open("render_page_13.png")
im13_crop = im13.crop((80, 80, 1574, 900))
im13_path = os.path.join(artifact_dir, "figure9_qtp_plots.png")
im13_crop.save(im13_path)
print("Saved figure9_qtp_plots.png to", im13_path)
