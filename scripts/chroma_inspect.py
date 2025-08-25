from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

COLLECTION = "tata_sampann_passages"
PERSIST_DIR = "vector_store_tata"
EMB = "sentence-transformers/all-MiniLM-L6-v2"

store = Chroma(
    collection_name=COLLECTION,
    persist_directory=PERSIST_DIR,
    embedding_function=HuggingFaceEmbeddings(model_name=EMB),
)
coll = store._client.get_collection(COLLECTION) 
count = coll.count()
print(f"docs in collection: {count}")

if count:
    docs = store.similarity_search("sample", k=3)
    for i, d in enumerate(docs, 1):
        print(f"\n[{i}] {d.metadata.get('sku_id')} | {d.metadata.get('section_path')}")
        print(d.page_content[:200])
