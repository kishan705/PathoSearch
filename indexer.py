import torch
import open_clip
import pyarrow as pa
from database import get_lancedb_connection

# Load BiomedCLIP
MODEL_NAME = "hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224"
device = torch.device("mps" if torch.cuda.is_available() else "cpu")

print(f"Loading BiomedCLIP on {device}...")
model, _, preprocess = open_clip.create_model_and_transforms(MODEL_NAME)
model.to(device)
model.eval()

def index_wsi_patches(slide_id, patches):
    """Passes patches through BiomedCLIP and stores vectors in LanceDB."""
    db = get_lancedb_connection()
    
    # Define Vector DB schema for pathology patches
    schema = pa.schema([
        pa.field("vector", pa.list_(pa.float32(), 512)), # BiomedCLIP base outputs 512-d
        pa.field("slide_id", pa.string()),
        pa.field("x_coord", pa.int32()),
        pa.field("y_coord", pa.int32())
    ])
    
    table_name = "pathology_patches"
    if table_name not in db.table_names():
        table = db.create_table(table_name, schema=schema)
    else:
        table = db.open_table(table_name)
    
    batch_size = 32
    records = []
    
    with torch.no_grad():
        for i in range(0, len(patches), batch_size):
            batch = patches[i:i+batch_size]
            
            # Preprocess images
            images = torch.stack([preprocess(p["image"]) for p in batch]).to(device)
            
            # Extract Medical Vision Features
            image_features = model.encode_image(images)
            image_features = image_features / image_features.norm(p=2, dim=-1, keepdim=True)
            vectors = image_features.cpu().numpy().tolist()
            
            # Attach X,Y coordinate metadata so doctors know where the patch came from
            for j, vec in enumerate(vectors):
                records.append({
                    "vector": vec,
                    "slide_id": slide_id,
                    "x_coord": batch[j]["x"],
                    "y_coord": batch[j]["y"]
                })
                
    if records:
        table.add(records)
        print(f"Successfully indexed {len(records)} patches for slide {slide_id}")

def search_patch(image_patch, top_k=5):
    """Takes a single 256x256 image patch and finds visually similar historical cases."""
    db = get_lancedb_connection()
    table = db.open_table("pathology_patches")
    
    with torch.no_grad():
        image_tensor = preprocess(image_patch).unsqueeze(0).to(device)
        image_features = model.encode_image(image_tensor)
        image_features = image_features / image_features.norm(p=2, dim=-1, keepdim=True)
        query_vector = image_features[0].cpu().numpy().tolist()
        
    # Execute Vector Similarity Search
    results = table.search(query_vector).limit(top_k).to_list()
    return results
