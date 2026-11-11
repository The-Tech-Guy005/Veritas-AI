"""
Multi-Format Document Text Extractor
Supports PDF, DOCX, TXT, CSV, and PPTX (PowerPoint presentations).
"""

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

import pandas as pd
import fitz
from docx import Document

SUPPORTED = {".pdf", ".docx", ".txt", ".csv", ".pptx"}


def _extract_pptx_xml(content: bytes) -> str:
    """
    Extracts text from a PPTX file using standard library zipfile and XML parsing.
    Parses all slides in numerical order, extracting title, body text, tables, and notes.
    Works independently of external C-extensions.
    """
    slides_text: List[str] = []
    
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        # Find all slide files
        slide_names = [f for f in z.namelist() if re.match(r"^ppt/slides/slide\d+\.xml$", f)]
        
        # Sort numerically by slide number (slide1, slide2, ..., slide10)
        def _slide_num(name: str) -> int:
            m = re.search(r"slide(\d+)\.xml", name)
            return int(m.group(1)) if m else 999999
        
        slide_names.sort(key=_slide_num)
        
        for idx, slide_path in enumerate(slide_names, 1):
            slide_xml = z.read(slide_path)
            slide_lines: List[str] = []
            
            try:
                root = ET.fromstring(slide_xml)
                for elem in root.iter():
                    if elem.tag.endswith("}p") or elem.tag == "p":
                        para_texts = [
                            node.text for node in elem.iter()
                            if (node.tag.endswith("}t") or node.tag == "t") and node.text
                        ]
                        if para_texts:
                            line = "".join(para_texts).strip()
                            if line:
                                slide_lines.append(line)
            except Exception:
                # Regex fallback if XML parsing encounters non-standard entities
                decoded = slide_xml.decode("utf-8", errors="replace")
                raw_matches = re.findall(r"<[a-zA-Z0-9:]*t[^>]*>(.*?)</[a-zA-Z0-9:]*t>", decoded)
                slide_lines = [m.strip() for m in raw_matches if m.strip()]
            
            if slide_lines:
                slide_content = "\n".join(slide_lines)
                slides_text.append(f"--- Slide {idx} ---\n{slide_content}")

        # Check for speaker notes
        note_names = [f for f in z.namelist() if re.match(r"^ppt/notesSlides/notesSlide\d+\.xml$", f)]
        note_names.sort(key=_slide_num)
        for idx, note_path in enumerate(note_names, 1):
            note_xml = z.read(note_path)
            root = ET.fromstring(note_xml)
            note_lines = []
            for elem in root.iter():
                if elem.tag.endswith("}p") or elem.tag == "p":
                    para_texts = [
                        node.text for node in elem.iter()
                        if (node.tag.endswith("}t") or node.tag == "t") and node.text
                    ]
                    if para_texts:
                        line = "".join(para_texts).strip()
                        if line and not line.isdigit():  # skip bare slide numbers in notes
                            note_lines.append(line)
            if note_lines:
                slides_text.append(f"--- Slide {idx} Notes ---\n" + "\n".join(note_lines))

    if not slides_text:
        return "Empty presentation or slides contain no text elements."

    return "\n\n".join(slides_text)


def _extract_pptx(content: bytes) -> str:
    """
    Attempts to extract text using python-pptx if installed,
    falling back to robust native zip/XML parser.
    """
    try:
        from pptx import Presentation
        prs = Presentation(io.BytesIO(content))
        slides_text = []
        for idx, slide in enumerate(prs.slides, 1):
            slide_lines = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        text = paragraph.text.strip()
                        if text:
                            slide_lines.append(text)
            if slide_lines:
                slides_text.append(f"--- Slide {idx} ---\n" + "\n".join(slide_lines))
        if slides_text:
            return "\n\n".join(slides_text)
    except ImportError:
        pass
    except Exception:
        pass

    # Use native OpenXML zip extractor
    return _extract_pptx_xml(content)


def extract_text(filename: str, content: bytes) -> str:
    """
    Extracts text from supported document formats.
    Supported: .pdf, .docx, .txt, .csv, .pptx
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"Unsupported file type '{suffix}'. Upload PDF, DOCX, TXT, CSV, or PPTX.")

    if suffix == ".pdf":
        with fitz.open(stream=content, filetype="pdf") as pdf:
            return "\n".join(page.get_text() for page in pdf)

    if suffix == ".docx":
        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())

    if suffix == ".txt":
        return content.decode("utf-8-sig", errors="replace")

    if suffix == ".csv":
        frame = pd.read_csv(io.BytesIO(content), dtype=str).fillna("")
        return frame.to_csv(index=False)

    if suffix == ".pptx":
        return _extract_pptx(content)

    raise ValueError(f"Unsupported file type '{suffix}'.")
