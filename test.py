from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# Same config you used earlier
PERSIST_DIR = "vector_store_tata"
COLLECTION = "tata_sampann_passages"  

store = Chroma(
    collection_name=COLLECTION,
    persist_directory=PERSIST_DIR,
    embedding_function=HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2"),
)

# Get one document back (with embeddings)
results = store.get(include=["embeddings", "metadatas", "documents"], limit=1)

print("Document:", results["documents"][0])
print("Metadata:", results["metadatas"][0])
print("Embedding array :", results["embeddings"])
print("Length of embedding vector:", len(results["embeddings"][0]))
