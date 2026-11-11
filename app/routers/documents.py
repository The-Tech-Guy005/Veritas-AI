from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from uuid import uuid4
from app.config import settings
from app.schemas import DocumentUploadResponse
from app.services.extractors import extract_text
from app.services.chunking import chunk_text
from app.services.vector_store import add_chunks, list_documents

router = APIRouter()

@router.post("/documents/upload", response_model=DocumentUploadResponse, summary="Upload & index document with access controls")
async def upload_document(
    file: UploadFile = File(...),
    classification: str = Form("internal", description="Document classification: public, internal, confidential, or restricted"),
    access_roles: str = Form("public,internal", description="Comma-separated roles allowed access (e.g. 'public,researcher,finance')"),
    owner_id: Optional[str] = Form(None, description="Optional document owner/creator user ID")
):
    """
    Ingests document files (.pdf, .docx, .txt, .csv, and .pptx), chunks content,
    and indexes into the semantic vector store with document-level access controls.
    """
    filename = file.filename or "uploaded_file"
    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds configured upload size limit.")
    try:
        extracted = extract_text(filename, content)
        chunks = chunk_text(extracted)
        if not chunks:
            raise ValueError("No text could be extracted from this file.")
        
        roles_list = [r.strip().lower() for r in access_roles.split(",") if r.strip()]
        document_id = str(uuid4())
        
        count = add_chunks(
            document_id=document_id,
            filename=filename,
            chunks=chunks,
            classification=classification.strip().lower(),
            access_roles=roles_list,
            owner_id=owner_id,
            source_type="knowledge_base",
            authority_level="high" if "internal" in roles_list else "medium"
        )
        return {
            "document_id": document_id,
            "filename": filename,
            "chunks_added": count,
            "status": "indexed",
            "classification": classification.strip().lower(),
            "access_roles": roles_list
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Document processing failed: " + type(exc).__name__)


@router.get("/documents", summary="List indexed documents")
def documents(
    user_roles: Optional[str] = Query(None, description="Comma-separated user roles for access control filtering"),
    user_id: Optional[str] = Query(None, description="Optional requesting user ID")
):
    """
    Returns indexed documents filtered according to user roles and access control permissions.
    """
    roles_list = [r.strip() for r in user_roles.split(",") if r.strip()] if user_roles else None
    return {"documents": list_documents(user_roles=roles_list, user_id=user_id)}
