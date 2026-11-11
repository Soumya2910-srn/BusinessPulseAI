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

def get_rag_response(user_id, user_query, ml_summary=None, insights=None, forecasting=None):
    """
    Processes user query using FAISS retrieval, adds ML model summary, AI insights engine data,
    and forecasting analytics, then queries Gemini LLM.
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
- Forecast for Next Month Revenue: ₹{ml_summary.get('forecasted_revenue', 0):,.2f}
"""

    # Format AI Insights context
    insights_context = "AI Insights Engine: No structured insights loaded."
    if insights:
        exec_sum = insights.get('executive_summary', '')
        growth_ops = [f"- {op.get('title')}: {op.get('description')} (Action: {op.get('action_item')})" 
                      for op in insights.get('growth_opportunities', [])]
        low_perfs = [f"- {lp.get('category')} ({lp.get('severity')} severity): {lp.get('issue')} (Remedy: {lp.get('remediation')})" 
                     for lp in insights.get('low_performing_products', [])]
        risks = [f"- {r.get('risk_type')} ({r.get('severity')}): {r.get('impact')} (Mitigation: {r.get('mitigation')})" 
                 for r in insights.get('risk_analysis', [])]
        recs = [f"- [{rec.get('priority')}] {rec.get('action')} (Expected: {rec.get('expected_outcome')})" 
                for rec in insights.get('smart_recommendations', [])]
        cust_info = insights.get('customer_insights', {})

        insights_context = f"""
Executive Summary: {exec_sum}

Growth Opportunities:
{chr(10).join(growth_ops) if growth_ops else "None identified."}

Low Performing Products:
{chr(10).join(low_perfs) if low_perfs else "All categories performing well."}

Customer & CAC Insights:
- Acquisition: {cust_info.get('acquisition_health', 'N/A')}
- CAC Analysis: {cust_info.get('cac_analysis', 'N/A')}
- Revenue Per Customer: {cust_info.get('revenue_per_customer', 'N/A')}

Key Risks:
{chr(10).join(risks) if risks else "No critical risks detected."}

Smart Strategic Recommendations:
{chr(10).join(recs) if recs else "Maintain current course."}
"""

    # Format Forecasting context
    forecasting_context = "Forecasting Engine: No projections loaded."
    if forecasting:
        sf = forecasting.get('sales_forecast', {})
        df_cast = forecasting.get('demand_forecast', {})
        inv = forecasting.get('inventory_forecast', {})
        
        inv_alerts = [f"- {it.get('category')}: {it.get('risk_status')} ({it.get('days_of_stock_remaining')} days stock left, reorder {it.get('recommended_reorder_units')} units)" 
                      for it in inv.get('items', []) if it.get('risk_status') in ['Critical', 'Warning']]
        
        demand_items = [f"- {d.get('category')}: {d.get('projected_units')} units ({d.get('growth_pct'):+.1f}% trend: {d.get('trend_status')})" 
                        for d in df_cast.get('category_demand', [])[:5]]

        forecasting_context = f"""
Sales & Revenue Forecast:
- Next Month Expected: ₹{sf.get('next_month_forecast', 0):,.2f} (Conservative: ₹{sf.get('conservative_forecast', 0):,.2f}, Optimistic: ₹{sf.get('optimistic_forecast', 0):,.2f})
- Direction: {sf.get('trend_direction', 'Steady')}

Demand Forecast:
- Total Projected Units: {df_cast.get('total_projected_units', 0):,} ({df_cast.get('aggregate_demand_growth_pct', 0):+.1f}% growth)
Top Category Projections:
{chr(10).join(demand_items) if demand_items else "No category projections available."}

Inventory & Stockout Forecast:
- Critical Alerts: {inv.get('critical_stockout_alerts', 0)}
- Total Restock Capital Required: ₹{inv.get('total_restock_capital_required', 0):,.2f}
Items Needing Attention:
{chr(10).join(inv_alerts) if inv_alerts else "All stock levels healthy."}
"""

    prompt_template = ChatPromptTemplate.from_template(
        """You are BusinessPulse AI, an intelligent business intelligence, analytics, and executive advisory assistant.
You help business owners, analysts, and decision-makers understand their sales, revenue, marketing, performance, forecasts, and inventory data.

Analyze the user's question using the retrieved data records, machine learning outputs, AI insights, and forecasting models below.
*IMPORTANT:* If the user's question is a simple greeting (e.g., 'Hello', 'Hi') or a pleasantry (e.g., 'Thank you'), respond politely and naturally without summarizing the dataset, and ask how you can help them with their data today.

=== BUSINESS METRICS SUMMARY ===
{ml_context}

=== AI INSIGHTS ENGINE (GROWTH, RISKS, LOW PERFORMERS, RECOMMENDATIONS) ===
{insights_context}

=== FORECASTING ENGINE (SALES, DEMAND, INVENTORY & RESTOCKING) ===
{forecasting_context}

=== RELEVANT RETRIEVED DATA CHUNKS (FROM FAISS) ===
{context}

=== USER QUESTION ===
{question}

Provide a concise, professional, and well-structured answer in Markdown format. Use Indian Rupees (₹) for currency amounts where applicable. Cite specific figures, risk alerts, growth opportunities, and forecast projections when answering user questions."""
    )

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=api_key, temperature=0.3)
        chain = prompt_template | llm | StrOutputParser()
        
        response = chain.invoke({
            "ml_context": ml_context,
            "insights_context": insights_context,
            "forecasting_context": forecasting_context,
            "context": retrieved_context,
            "question": user_query
        })
        return response
    except Exception as e:
        return f"❌ **Error generating AI response**: {str(e)}"
