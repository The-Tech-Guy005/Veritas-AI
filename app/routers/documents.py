from fastapi import APIRouter, UploadFile, File, HTTPException
from uuid import uuid4
from app.config import settings
from app.schemas import DocumentUploadResponse
from app.services.extractors import extract_text
from app.services.chunking import chunk_text
from app.services.vector_store import add_chunks, list_documents

router = APIRouter()

@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)):
    filename = file.filename or "uploaded_file"
    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds configured upload size limit.")
    try:
        extracted = extract_text(filename, content)
        chunks = chunk_text(extracted)
        if not chunks:
            raise ValueError("No text could be extracted from this file.")
        document_id = str(uuid4())
        count = add_chunks(document_id, filename, chunks)
        return {
            "document_id": document_id,
            "filename": filename,
            "chunks_added": count,
            "status": "indexed"
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Document processing failed: " + type(exc).__name__)

@router.get("/documents")
def documents():
    return {"documents": list_documents()}
