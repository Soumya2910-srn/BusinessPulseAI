import os
import json
import pandas as pd
from dotenv import load_dotenv

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# Load environment variables
load_dotenv()

# In-memory store for vector databases per user
USER_VECTOR_STORES = {}

def get_gemini_api_key():
    """Retrieve Gemini / Google API Key from environment."""
    load_dotenv(override=True)
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if key:
        return key.strip().strip('"').strip("'")
    return None

def get_embeddings():
    """Returns Google GenAI embeddings if API key available, else HuggingFace embeddings."""
    api_key = get_gemini_api_key()
    if api_key:
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            return GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", google_api_key=api_key)
        except Exception as e:
            print(f"Failed to initialize Google embeddings: {e}. Falling back to HuggingFace.")
    
    # Fallback to local huggingface embeddings
    from langchain_huggingface import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

def create_documents_from_csv(file_path, month_label="Current Month"):
    """Reads a CSV file and converts each row into a descriptive Document."""
    df = pd.read_csv(file_path)
    docs = []
    
    for idx, row in df.iterrows():
        content = f"Dataset Period: {month_label}\n"
        content += f"Row ID: {idx + 1}\n"
        for col in df.columns:
            content += f"{col}: {row[col]}\n"
        
        metadata = {
            "source": os.path.basename(file_path),
            "period": month_label,
            "row": idx
        }
        docs.append(Document(page_content=content.strip(), metadata=metadata))
    
    return docs

def build_vector_store(user_id, prev_csv_path=None, curr_csv_path=None):
    """
    Builds a FAISS vector store from the uploaded CSV datasets and stores it for the user session.
    """
    docs = []
    if prev_csv_path and os.path.exists(prev_csv_path):
        docs.extend(create_documents_from_csv(prev_csv_path, month_label="Previous Month"))
        
    if curr_csv_path and os.path.exists(curr_csv_path):
        docs.extend(create_documents_from_csv(curr_csv_path, month_label="Current Month"))
        
    if not docs:
        return None

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    split_docs = text_splitter.split_documents(docs)

    embeddings = get_embeddings()
    vector_store = FAISS.from_documents(split_docs, embeddings)
    
    USER_VECTOR_STORES[user_id] = vector_store
    return vector_store

def ensure_user_vector_store(user_id):
    """If user has no vector store yet, load default sample datasets if available."""
    if user_id not in USER_VECTOR_STORES:
        prev_p = "previous_month_dataset.csv"
        curr_p = "current_month_dataset.csv"
        if os.path.exists(prev_p) and os.path.exists(curr_p):
            try:
                build_vector_store(user_id, prev_p, curr_p)
            except Exception as e:
                print(f"Error auto-building default vector store: {e}")

def get_rag_response(user_id, user_query, ml_summary=None):
    """
    Processes user query using FAISS retrieval, adds ML model summary, and queries Gemini LLM.
    """
    api_key = get_gemini_api_key()
    if not api_key:
        return (
            "⚠️ **API Key Missing**: Please configure your `GEMINI_API_KEY` in the `.env` file "
            "to enable AI-powered chat with your datasets."
        )

    ensure_user_vector_store(user_id)
    vector_store = USER_VECTOR_STORES.get(user_id)
    retrieved_context = ""
    
    if vector_store:
        try:
            retriever = vector_store.as_retriever(search_kwargs={"k": 5})
            matched_docs = retriever.invoke(user_query)
            retrieved_context = "\n\n---\n\n".join([doc.page_content for doc in matched_docs])
        except Exception as e:
            retrieved_context = f"Error retrieving vector documents: {e}"
    else:
        retrieved_context = "No specific dataset chunks available in vector index. Rely on overall summary."

    # Format ML / trained model additional info
    ml_context = "No trained ML model metrics available."
    if ml_summary:
        ml_context = f"""
- Previous Month Total Revenue: ₹{ml_summary.get('prev_revenue', 0):,.2f}
- Current Month Total Revenue: ₹{ml_summary.get('curr_revenue', 0):,.2f}
- Revenue Growth Rate: {ml_summary.get('revenue_growth', 0)}%
- Total Units Sold (Prev vs Curr): {ml_summary.get('prev_units', 0)} vs {ml_summary.get('curr_units', 0)} ({ml_summary.get('units_growth', 0)}% growth)
- New Customers Acquired (Prev vs Curr): {ml_summary.get('prev_customers', 0)} vs {ml_summary.get('curr_customers', 0)} ({ml_summary.get('customers_growth', 0)}% growth)
- Marketing Spend (Prev vs Curr): ₹{ml_summary.get('prev_marketing', 0):,.2f} vs ₹{ml_summary.get('curr_marketing', 0):,.2f}
- Linear Regression ML Model Forecast for Next Month Revenue: ₹{ml_summary.get('forecasted_revenue', 0):,.2f}
"""

    prompt_template = ChatPromptTemplate.from_template(
        """You are BusinessPulse AI, an intelligent business intelligence and analytics assistant.
You help business owners, analysts, and decision-makers understand their sales, revenue, marketing, and performance data.

Analyze the user's question using the retrieved data records and the trained machine learning model outputs below.
*IMPORTANT:* If the user's question is a simple greeting (e.g., 'Hello', 'Hi') or a pleasantry (e.g., 'Thank you'), respond politely and naturally without summarizing the dataset, and ask how you can help them with their data today.

=== TRAINED ML MODEL & DATASET SUMMARY ===
{ml_context}

=== RELEVANT RETRIEVED DATA CHUNKS (FROM FAISS) ===
{context}

=== USER QUESTION ===
{question}

Provide a concise, professional, and well-structured answer in Markdown format. Use Indian Rupees (₹) for currency amounts where applicable. If specific information isn't available, mention what can be inferred from the summary metrics."""
    )

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=api_key, temperature=0.3)
        chain = prompt_template | llm | StrOutputParser()
        
        response = chain.invoke({
            "ml_context": ml_context,
            "context": retrieved_context,
            "question": user_query
        })
        return response
    except Exception as e:
        return f"❌ **Error generating AI response**: {str(e)}"

