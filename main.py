from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import io
import os
import uuid
from PIL import Image
from extractor import extract_tissue_patches
from indexer import index_wsi_patches, search_patch

app = FastAPI(title="PathoSearch Digital Pathology API")

UPLOAD_DIR = "./temp_slides"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/upload_slide/")
async def upload_slide(file: UploadFile = File(...)):
    """Upload a Whole Slide Image (.svs) and index its tissue patches."""
    slide_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{slide_id}_{file.filename}")
    
    # Save the massive file locally
    with open(file_path, "wb") as f:
        f.write(await file.read())
        
    print(f"Extracting patches from {file.filename}...")
    patches, dimensions = extract_tissue_patches(file_path)
    
    if not patches:
        return JSONResponse({"error": "No valid tissue patches found."})
        
    print(f"Indexing {len(patches)} patches with BiomedCLIP...")
    index_wsi_patches(slide_id, patches)
    
    return {
        "status": "success", 
        "slide_id": slide_id, 
        "patches_indexed": len(patches), 
        "original_dimensions": dimensions
    }

@app.post("/search_patch/")
async def search(file: UploadFile = File(...)):
    """Upload a small tissue patch to find visually similar historical cases."""
    image_bytes = await file.read()
    query_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    
    # Run the similarity search
    results = search_patch(query_image, top_k=5)
    
    matches = []
    for r in results:
        matches.append({
            "slide_id": r["slide_id"],
            "x_coord": r["x_coord"],
            "y_coord": r["y_coord"],
            "similarity_score": round((1.0 - r["_distance"]) * 100, 2) # Format as percentage
        })
        
    return {"query_results": matches}