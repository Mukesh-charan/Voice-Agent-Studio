from PIL import Image
import os

artifact_dir = r"C:\Users\Sanjjey Arumugam\.gemini\antigravity-ide\brain\c7f8c7c6-1e2b-4583-ad3a-c21b878c75e8"

im5 = Image.open("render_page_5.png")
# Figure 1 is at the top of page 5
fig1_crop = im5.crop((80, 80, 1574, 950))
fig1_path = os.path.join(artifact_dir, "figure1_architecture.png")
fig1_crop.save(fig1_path)
print("Saved figure1_architecture.png to", fig1_path)

# Let's inspect where QTP eval figure is in page 12 or 13
im12 = Image.open("render_page_12.png")
# Check if top or bottom
im12_crop = im12.crop((80, 80, 1574, 1100))
im12_path = os.path.join(artifact_dir, "figure_qtp_eval.png")
im12_crop.save(im12_path)
print("Saved figure_qtp_eval.png to", im12_path)
