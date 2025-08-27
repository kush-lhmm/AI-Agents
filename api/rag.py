# api/rag_lc.py
import io, os, uuid, re
from typing import List, Dict, Any

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from PyPDF2 import PdfReader

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ---------------- Config ----------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Set OPENAI_API_KEY in .env")

PERSIST_DIR = os.getenv("CHROMA_DIR", "./chroma_data")
UPLOAD_DIR  = os.getenv("UPLOAD_DIR", "./data/uploads")
os.makedirs(PERSIST_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

COLLECTION = os.getenv("CHROMA_COLLECTION", "docs") 
EMB_MODEL  = os.getenv("EMB_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "8000"))

# Embeddings (HF)
embeddings = HuggingFaceEmbeddings(
    model_name=EMB_MODEL,
    encode_kwargs={"normalize_embeddings": True}  # cosine-friendly
)

# Vector store (auto-persistent)
store = Chroma(
    collection_name=COLLECTION,
    persist_directory=PERSIST_DIR,
    embedding_function=embeddings,
)

# OpenAI LLM for synthesis
from openai import OpenAI
oai = OpenAI(api_key=OPENAI_API_KEY)

router = APIRouter(tags=["RAG"])

# ---------------- Models ----------------
class UploadResp(BaseModel):
    ok: bool
    doc_id: str
    pages: int
    chunks: int

class QueryIn(BaseModel):
    doc_id: str
    question: str
    k: int = 6  # top-k dense
    return_contexts: bool = True

class ContextItem(BaseModel):
    chunk_id: str
    page: int
    text: str

class QueryResp(BaseModel):
    answer: str
    citations: List[Dict[str, Any]]
    contexts: List[ContextItem] = []

# ---------------- Helpers ----------------
def parse_pdf(file_bytes: bytes) -> List[Dict[str, Any]]:
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, p in enumerate(reader.pages, start=1):
        txt = (p.extract_text() or "").strip()
        if not txt:
            continue
        txt = re.sub(r"\s+", " ", txt)  # simple normalize
        pages.append({"page": i, "text": txt})
    if not pages:
        raise ValueError("No extractable text found.")
    return pages

# chunker (LangChain)
splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=120,
    separators=["\n\n", "\n", ". ", " ", ""],
)

SYSTEM_PROMPT = (
    "You are a retrieval-grounded assistant.\n"
    "- ONLY use the supplied CONTEXT (from the uploaded PDF).\n"
    "- If the answer is not clearly supported, reply exactly: 'Not found in the provided document.'\n"
    "- Include page numbers when possible. Be precise and concise."
)

def build_context_for_llm(snippets: List[Dict[str, Any]]) -> str:
    buf, used = [], 0
    for s in snippets:
        piece = f"(p.{s['page']}) {s['text']}".strip()
        if used + len(piece) + 2 > MAX_CONTEXT_CHARS:
            break
        buf.append(piece)
        used += len(piece) + 2
    return "\n\n".join(buf)

def synthesize(question: str, snippets: List[Dict[str, Any]]) -> str:
    if not snippets:
        return "Not found in the provided document."
    context_text = build_context_for_llm(snippets)
    resp = oai.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Question:\n{question}\n\nCONTEXT:\n{context_text}"},
        ],
    )
    return resp.choices[0].message.content.strip()

# ---------------- Routes ----------------
@router.post("/upload", response_model=UploadResp)
async def upload(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported.")
    pdf = await file.read()

    # save original (optional)
    doc_id = str(uuid.uuid4())
    with open(os.path.join(UPLOAD_DIR, f"{doc_id}.pdf"), "wb") as f:
        f.write(pdf)

    try:
        pages = parse_pdf(pdf)

        texts, metas, ids = [], [], []
        idx = 0
        for p in pages:
            chunks = splitter.split_text(p["text"])
            for ch in chunks:
                texts.append(ch)
                metas.append({"doc_id": doc_id, "page": p["page"]})
                ids.append(f"{doc_id}-{idx:06d}")
                idx += 1

        if not texts:
            raise ValueError("Empty after chunking.")

        # single collection, filter by doc_id during query
        store.add_texts(texts=texts, metadatas=metas, ids=ids)

        return UploadResp(ok=True, doc_id=doc_id, pages=len(pages), chunks=len(texts))
    except Exception as e:
        raise HTTPException(400, f"Ingestion failed: {e}")

@router.post("/query", response_model=QueryResp)
def query(q: QueryIn):
    # Dense similarity with metadata filter (single collection)
    retriever = store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": q.k, "filter": {"doc_id": q.doc_id}},
    )
    docs = retriever.get_relevant_documents(q.question)

    if not docs:
        return QueryResp(answer="Not found in the provided document.", citations=[], contexts=[])

    # Build snippets for LLM + UI
    snippets = [{"text": d.page_content, "page": int(d.metadata.get("page", -1))} for d in docs]
    answer = synthesize(q.question, snippets)

    citations = []
    contexts: List[ContextItem] = []
    for d in docs:
        citations.append({
            "page": int(d.metadata.get("page", -1)),
            "doc_id": d.metadata.get("doc_id", q.doc_id),
            "chunk_id": d.metadata.get("id", ""),  # may be empty; Chroma returns id separately
        })
        if q.return_contexts:
            contexts.append(ContextItem(
                chunk_id=d.metadata.get("id", ""),
                page=int(d.metadata.get("page", -1)),
                text=d.page_content
            ))

    return QueryResp(answer=answer, citations=citations, contexts=contexts)
