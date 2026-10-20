import os
import openslide
from PIL import Image, ImageStat

def extract_tissue_patches(wsi_path, patch_size=(256, 256), level=0, bg_threshold=220, max_patches=1000):
    """
    Extracts 256x256 patches from a massive Whole Slide Image (WSI).
    Skips mostly white glass/background patches to save vector database space.
    """
    slide = openslide.OpenSlide(wsi_path)
    width, height = slide.level_dimensions[level]
    
    patches = []
    
    # Iterate over the massive image in small grid chunks
    for y in range(0, height, patch_size[1]):
        for x in range(0, width, patch_size[0]):
            
            # Stop if we hit the limit (useful for testing/prototyping)
            if len(patches) >= max_patches:
                break
                
            # read_region pulls just that specific 256x256 chunk into RAM
            patch = slide.read_region((x, y), level, patch_size).convert("RGB")
            
            # Simple background filtering: calculate average pixel intensity
            stat = ImageStat.Stat(patch)
            avg_color = sum(stat.mean) / len(stat.mean)
            
            # 255 is pure white. Anything < 220 means it contains biological tissue/dye
            if avg_color < bg_threshold:  
                patches.append({
                    "image": patch,
                    "x": x,
                    "y": y,
                    "level": level
                })
                
        if len(patches) >= max_patches:
            break
            
    return patches, slide.dimensions