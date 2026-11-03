# PathoSearch 🔬 
**High-Resolution Digital Pathology Vector Search & CBIR Pipeline**

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![PyTorch](https://img.shields.io/badge/PyTorch-Deep_Learning-EE4C2C.svg)
![LanceDB](https://img.shields.io/badge/LanceDB-Vector_Database-000000.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-REST_API-009688.svg)
![OpenSlide](https://img.shields.io/badge/OpenSlide-WSI_Processing-lightgrey.svg)

## Overview
PathoSearch is a high-performance **Content-Based Image Retrieval (CBIR)** system engineered to process, analyze, and search massive Whole Slide Images (WSIs) used in digital pathology. 

Medical scans routinely exceed $50k \times 50k$ pixels, making them impossible to load into standard memory. PathoSearch solves this bottleneck by implementing dynamic image tiling via **OpenSlide**, extracting high-density 256x256 tissue patches while automatically filtering out irrelevant background data. These localized patches are indexed using **Microsoft's BiomedCLIP** semantic embeddings and **LanceDB**, enabling sub-millisecond similarity searches. 

Exposed via a low-latency **FastAPI** backend, this architecture empowers medical professionals to instantly identify morphologically similar cellular structures across extensive diagnostic datasets.

---

## Key Features

* **Massive Scale Image Processing:** Capable of handling $50k \times 50k$ high-resolution `.svs` and `.tiff` formats without RAM overflow, utilizing dynamic grid-chunking.
* **Smart Background Filtration:** Implements statistical heuristics to automatically identify and drop "white glass" background patches, optimizing both compute time and vector storage space.
* **Medical-Grade Deep Learning:** Replaces generic vision models with `microsoft/BiomedCLIP`, a domain-specific model pre-trained on PubMed pathology articles for highly accurate pattern recognition.
* **Sub-Millisecond Vector Search:** Leverages LanceDB for high-dimensional (512-D) cosine similarity indexing, allowing real-time retrieval of historical medical cases.
* **Coordinate Mapping:** Retains the exact $X, Y$ coordinate metadata for every embedding, allowing queried patches to be mapped back to their exact location on the original slide.

---

## Tech Stack & Architecture

### **Core Technologies**
* **Image Processing:** OpenSlide, OpenCV, Pillow (PIL)
* **Machine Learning / AI:** PyTorch, HuggingFace (`open_clip_torch`)
* **Database:** LanceDB (Serverless Vector DB), PyArrow
* **Backend:** FastAPI, Uvicorn, Python Multipart

### **Pipeline Architecture**
1. **Extraction:** `/upload_slide/` receives a massive WSI. The Extractor script slices the image at specific magnification levels.
2. **Filtration:** Pixels are evaluated; patches lacking biological tissue are discarded.
3. **Embedding:** Surviving patches pass through BiomedCLIP to generate semantic vector representations.
4. **Indexing:** Vectors and spatial metadata are committed to LanceDB.
5. **Retrieval:** `/search_patch/` receives a small cellular query, encodes it, and executes a real-time nearest-neighbor search across the index.

---

## Setup & Installation

### 1. System Dependencies (Required)
PathoSearch requires the OpenSlide C-library installed on your machine to read proprietary medical image formats.
* **Ubuntu/Debian:** `sudo apt-get install openslide-tools`
* **Mac (Homebrew):** `brew install openslide`
* **Windows:** Download the binaries from [OpenSlide.org](https://openslide.org/download/) and add them to your system PATH.

### 2. Python Environment
Clone the repository and install the dependencies:
```bash
git clone https://github.com/yourusername/PathoSearch.git
cd PathoSearch
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Run the Server
```bash
uvicorn main:app --reload
```
The API will be live at `http://127.0.0.1:8000`. 
Access the interactive Swagger documentation at `http://127.0.0.1:8000/docs`.

*(Note: The first time the server spins up, PyTorch will download the BiomedCLIP weights, which may take a few minutes depending on your connection.)*

---

## API Endpoints

### `POST /upload_slide/`
Upload a `.svs` or `.tiff` Whole Slide Image. The system will slice, filter, and index the entire slide in the background.
* **Returns:** Slide ID, dimensions, and total patches successfully indexed.

### `POST /search_patch/`
Upload a 256x256 image of a specific tissue structure or cellular anomaly.
* **Returns:** A ranked list of the top 5 most visually similar historical patches, including their exact slide IDs, $X/Y$ coordinates, and percentage similarity scores.

---

## Domain Applicability
This system was specifically designed to tackle real-world engineering challenges in Life Sciences and Healthcare laboratories. The architecture provides a scalable foundation for disease stratification, diagnostic accuracy enhancements, and efficient study management workflows.
