from app.services.chunking import chunk_text

def test_empty_text():
    assert chunk_text("") == []

def test_chunks_text():
    result = chunk_text("hello world " * 200)
    assert len(result) > 1
    assert all(result)
