from backend.rag.ingestion import chunk_text


def test_short_text_single_chunk():
    chunks = chunk_text("Une phrase courte.", size=800, overlap=120)
    assert chunks == ["Une phrase courte."]


def test_empty_text_no_chunks():
    assert chunk_text("   \n\n  ", size=800, overlap=120) == []


def test_long_text_is_split_and_bounded():
    text = "\n\n".join(f"Paragraphe {i} sur la cure thermale à Dax. " * 5 for i in range(20))
    chunks = chunk_text(text, size=300, overlap=40)
    assert len(chunks) > 1
    assert all(len(c) <= 300 + 40 + 80 for c in chunks)


def test_overlap_carries_context():
    text = "\n\n".join(f"Bloc {i} " * 40 for i in range(5))
    chunks = chunk_text(text, size=200, overlap=30)
    assert len(chunks) >= 2
    assert chunks[0][-20:].strip() in chunks[1]
