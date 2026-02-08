import os
import argparse
import numpy as np
import onnxruntime as ort
from PIL import Image
from huggingface_hub import hf_hub_download
import csv
from tqdm import tqdm

# Constants for WD14 Tagger
REPO_ID = "SmilingWolf/wd-v1-4-convnext-tagger-v2"
MODEL_FILENAME = "model.onnx"
TAGS_FILENAME = "selected_tags.csv"

def preprocess_image(image, size=448):
    image = image.convert("RGB")
    image = image.resize((size, size), Image.BICUBIC)
    img_array = np.array(image, dtype=np.float32)
    # BGR to RGB if needed, but PIL is RGB. 
    # WD14 expects BGR? No, usually RGB normalized.
    # Checking standard preprocessing for WD14 ONNX:
    # It usually expects generic normalization.
    # Let's assume standard input: [1, size, size, 3] -> [1, 3, size, size] ?
    # WD14 ConvNext v2 usually expects [N, size, size, 3] and BGR.
    
    # Correct preprocessing for SmilingWolf models:
    # BGR, Not normalized (0-255) or normalized?
    # Reference: https://github.com/toriato/stable-diffusion-webui-wd14-tagger/blob/master/tagger/interrogator.py
    # It converts to BGR and keeps it float32.
    
    img_array = img_array[:, :, ::-1] # RGB to BGR
    img_array = np.expand_dims(img_array, axis=0)
    return img_array

def load_tags(path):
    tags = []
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            tags.append(row[1]) # tag name is usually 2nd column
    return tags

def main():
    parser = argparse.ArgumentParser(description="Auto-tag images using WD14 Tagger (ONNX)")
    parser.add_argument("--dir", type=str, required=True, help="Path to dataset directory")
    parser.add_argument("--thresh", type=float, default=0.35, help="Confidence threshold")
    args = parser.parse_args()

    print(f"Downloading model from {REPO_ID}...")
    model_path = hf_hub_download(repo_id=REPO_ID, filename=MODEL_FILENAME)
    tags_path = hf_hub_download(repo_id=REPO_ID, filename=TAGS_FILENAME)
    
    print("Loading ONNX model...")
    # Use CUDA provider if available
    providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
    sess = ort.InferenceSession(model_path, providers=providers)
    
    tags = load_tags(tags_path)
    input_name = sess.get_inputs()[0].name
    label_name = sess.get_outputs()[0].name

    image_exts = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')
    files = [f for f in os.listdir(args.dir) if f.lower().endswith(image_exts)]
    
    print(f"Found {len(files)} images. Starting tagging...")
    
    for filename in tqdm(files):
        img_path = os.path.join(args.dir, filename)
        txt_path = os.path.splitext(img_path)[0] + ".txt"
        
        # Skip if txt exists? No, overwrite or append? Overwrite for now.
        
        try:
            img = Image.open(img_path)
            # WD14 usually takes 448x448
            data = preprocess_image(img, size=448)
            
            probs = sess.run([label_name], {input_name: data})[0][0]
            
            # Filter tags
            active_tags = []
            for i, p in enumerate(probs):
                if p >= args.thresh and i < len(tags): # Ensure index bounds
                    # Skip 'rating' tags if they are at the end, usually general tags are first
                    # In v2 CSV: tag_id, name, category, count
                    # We just took names.
                    # Usually tags[4:] are the descriptive ones.
                    if i > 3: # Skip rating/general meta tags often at start
                        active_tags.append(tags[i])
            
            tag_string = ", ".join(active_tags)
            
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(tag_string)
                
        except Exception as e:
            print(f"Error processing {filename}: {e}")

    print("Tagging complete!")

if __name__ == "__main__":
    main()