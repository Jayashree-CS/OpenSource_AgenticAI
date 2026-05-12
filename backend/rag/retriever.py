# rag/retriever.py
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations
import os
from functools import lru_cache
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_classic.chains import RetrievalQA
# SWAP: Changed OpenAI to Groq
from langchain_groq import ChatGroq 
from langchain_core.prompts import PromptTemplate
from config.rbac import is_admin, is_manager, is_employee

# ── Config ────────────────────────────────────────────────────────────────────
CHROMA_PATH      = os.getenv("CHROMA_PATH", "./chroma_db/hr_policies")
EMBED_MODEL      = os.getenv("HF_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
RETRIEVER_TOP_K  = int(os.getenv("RETRIEVER_TOP_K", "4"))


# ─────────────────────────────────────────────────────────────────────────────
# Load persisted ChromaDB (singleton)
# ─────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_vectorstore() -> Chroma:
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
    return Chroma(
        persist_directory=CHROMA_PATH,
        embedding_function=embeddings,
    )


# ─────────────────────────────────────────────────────────────────────────────
# RAG prompt
# ─────────────────────────────────────────────────────────────────────────────

RAG_PROMPT = PromptTemplate(
    input_variables=["context", "question"],
    template="""You are an HR policy assistant. Answer the question using ONLY
the provided context from official company documents.

If the answer is not in the context, say:
"I couldn't find this in our policy documents. Please contact HR directly."

Always be concise and cite which document/section the answer comes from.

Context:
{context}

Question: {question}

Answer:""",
)


# ─────────────────────────────────────────────────────────────────────────────
# Build retriever for a given user role
# ─────────────────────────────────────────────────────────────────────────────

def build_retriever(role: str):
    """
    Returns a LangChain RetrievalQA chain using Groq LLM.
    RBAC filters based on user role.
    """
    vectorstore = _get_vectorstore()

    # RBAC filter on access_level metadata tagged during ingestion.
    # Chroma's where-filter requires the ``$in`` operator for list values.
    if is_admin(role):
        # Admin can access all documents.
        search_kwargs = {"k": RETRIEVER_TOP_K}
    elif is_manager(role):
        search_kwargs = {
            "k": RETRIEVER_TOP_K,
            "filter": {"access_level": {"$in": ["employee", "manager"]}},
        }
    else:
        search_kwargs = {
            "k": RETRIEVER_TOP_K,
            "filter": {"access_level": "employee"},
        }

    base_retriever = vectorstore.as_retriever(search_kwargs=search_kwargs)

    # ── UPDATED: Now using Groq Llama 3.3 ─────────────────────────────────────
    llm = ChatGroq(
        # Llama 3.3 70B is currently the top-tier model for speed/accuracy on Groq
        model="llama-3.3-70b-versatile", 
        temperature=0.0, # Keep at 0 for factual RAG
        groq_api_key=os.getenv("GROQ_API_KEY"),
    )

    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=base_retriever,
        return_source_documents=True,
        chain_type_kwargs={"prompt": RAG_PROMPT},
    )
    return qa_chain


def retrieve_docs(query: str, k: int | None = None, role: str | None = None) -> list[str]:
    """
    Legacy helper: return raw document text snippets for prompt assembly.
    Used by chat fallback and hr_agent policy answers.

    When ``role`` is provided, the same RBAC filter used by ``build_retriever``
    is applied so employees never see manager/admin-only material.
    """
    if not query or not query.strip():
        return []
    k = k or RETRIEVER_TOP_K
    try:
        vectorstore = _get_vectorstore()
        filter_kwargs = _role_filter(role)
        docs = vectorstore.similarity_search(query.strip(), k=k, filter=filter_kwargs)
        return [d.page_content for d in docs if getattr(d, "page_content", None)]
    except Exception:
        return []


def retrieve_docs_with_sources(query: str, k: int | None = None, role: str | None = None):
    """Return ``[(text, source, page)]`` triples for citation-aware answers."""
    if not query or not query.strip():
        return []
    k = k or RETRIEVER_TOP_K
    try:
        vectorstore = _get_vectorstore()
        filter_kwargs = _role_filter(role)
        docs = vectorstore.similarity_search(query.strip(), k=k, filter=filter_kwargs)
        out = []
        for d in docs:
            text = getattr(d, "page_content", None)
            if not text:
                continue
            md = getattr(d, "metadata", {}) or {}
            out.append((text, md.get("source", "document"), md.get("page")))
        return out
    except Exception:
        return []


def _role_filter(role: str | None):
    if role is None or is_admin(role):
        return None
    if is_manager(role):
        return {"access_level": {"$in": ["employee", "manager"]}}
    return {"access_level": "employee"}


# ─────────────────────────────────────────────────────────────────────────────
# Quick test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Ensure you have your GROQ_API_KEY exported in your terminal
    retriever = build_retriever("employee")
    result = retriever.invoke("What is the notice period for resignation?")
    print("\n--- Answer from Groq ---")
    print(result["result"])
    print("\n--- Sources ---")
    for doc in result.get("source_documents", []):
        print(f"• {doc.metadata.get('source')}")