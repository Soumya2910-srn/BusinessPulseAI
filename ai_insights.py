import os
import json
import re
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()

def get_api_key():
    """Retrieve Gemini or Google API key from environment."""
    load_dotenv(override=True)
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if key:
        return key.strip().strip('"').strip("'")
    return None

def compute_data_metrics(df_curr, df_prev=None):
    """
    Computes rigorous analytical metrics from current and previous month datasets.
    Returns a dictionary of raw business metrics ready for LLM consumption or deterministic insights.
    """
    metrics = {
        'current': {},
        'previous': {},
        'categories': {},
        'customer_metrics': {},
        'marketing_efficiency': {},
        'risk_indicators': {},
        'growth_vectors': {}
    }

    # Current totals
    curr_rev = float(df_curr['Revenue'].sum()) if 'Revenue' in df_curr.columns else 0.0
    curr_units = int(df_curr['Units_Sold'].sum()) if 'Units_Sold' in df_curr.columns else 0
    curr_mkt = float(df_curr['Marketing_Spend'].sum()) if 'Marketing_Spend' in df_curr.columns else 0.0
    curr_cust = int(df_curr['New_Customers'].sum()) if 'New_Customers' in df_curr.columns else 0
    curr_profit = curr_rev - curr_mkt

    metrics['current'] = {
        'revenue': round(curr_rev, 2),
        'units': curr_units,
        'marketing_spend': round(curr_mkt, 2),
        'new_customers': curr_cust,
        'profit': round(curr_profit, 2),
        'profit_margin_pct': round((curr_profit / curr_rev * 100) if curr_rev > 0 else 0.0, 1)
    }

    # Previous totals if available
    prev_rev, prev_units, prev_mkt, prev_cust = 0.0, 0, 0.0, 0
    if df_prev is not None and not df_prev.empty:
        prev_rev = float(df_prev['Revenue'].sum()) if 'Revenue' in df_prev.columns else 0.0
        prev_units = int(df_prev['Units_Sold'].sum()) if 'Units_Sold' in df_prev.columns else 0
        prev_mkt = float(df_prev['Marketing_Spend'].sum()) if 'Marketing_Spend' in df_prev.columns else 0.0
        prev_cust = int(df_prev['New_Customers'].sum()) if 'New_Customers' in df_prev.columns else 0
        prev_profit = prev_rev - prev_mkt

        rev_growth = round(((curr_rev - prev_rev) / prev_rev * 100) if prev_rev > 0 else 0.0, 1)
        units_growth = round(((curr_units - prev_units) / prev_units * 100) if prev_units > 0 else 0.0, 1)
        cust_growth = round(((curr_cust - prev_cust) / prev_cust * 100) if prev_cust > 0 else 0.0, 1)
        profit_growth = round(((curr_profit - prev_profit) / prev_profit * 100) if prev_profit != 0 else 0.0, 1)

        metrics['previous'] = {
            'revenue': round(prev_rev, 2),
            'units': prev_units,
            'marketing_spend': round(prev_mkt, 2),
            'new_customers': prev_cust,
            'profit': round(prev_profit, 2),
            'revenue_growth_pct': rev_growth,
            'units_growth_pct': units_growth,
            'customer_growth_pct': cust_growth,
            'profit_growth_pct': profit_growth
        }
    else:
        metrics['previous'] = {
            'revenue': curr_rev,
            'units': curr_units,
            'marketing_spend': curr_mkt,
            'new_customers': curr_cust,
            'profit': curr_profit,
            'revenue_growth_pct': 0.0,
            'units_growth_pct': 0.0,
            'customer_growth_pct': 0.0,
            'profit_growth_pct': 0.0
        }

    # Customer & Marketing Efficiency
    curr_cac = round((curr_mkt / curr_cust) if curr_cust > 0 else 0.0, 2)
    prev_cac = round((prev_mkt / prev_cust) if prev_cust > 0 else 0.0, 2)
    cac_change = round(((curr_cac - prev_cac) / prev_cac * 100) if prev_cac > 0 else 0.0, 1)
    rev_per_cust = round((curr_rev / curr_cust) if curr_cust > 0 else 0.0, 2)
    curr_roas = round((curr_rev / curr_mkt) if curr_mkt > 0 else 0.0, 2)
    prev_roas = round((prev_rev / prev_mkt) if prev_mkt > 0 else 0.0, 2)

    metrics['customer_metrics'] = {
        'current_cac': curr_cac,
        'previous_cac': prev_cac,
        'cac_change_pct': cac_change,
        'revenue_per_customer': rev_per_cust,
        'customer_conversion_efficiency': 'Efficient' if cac_change <= 0 else 'Rising Cost'
    }

    metrics['marketing_efficiency'] = {
        'current_roas': curr_roas,
        'previous_roas': prev_roas,
        'roas_change': round(curr_roas - prev_roas, 2),
        'marketing_share_of_revenue_pct': round((curr_mkt / curr_rev * 100) if curr_rev > 0 else 0.0, 1)
    }

    # Category Level Breakdown
    prev_cat_rev = {}
    prev_cat_units = {}
    if df_prev is not None and not df_prev.empty and 'Product_Category' in df_prev.columns:
        for cat, grp in df_prev.groupby('Product_Category'):
            prev_cat_rev[str(cat)] = float(grp['Revenue'].sum()) if 'Revenue' in grp.columns else 0.0
            prev_cat_units[str(cat)] = int(grp['Units_Sold'].sum()) if 'Units_Sold' in grp.columns else 0

    category_records = []
    if 'Product_Category' in df_curr.columns:
        for cat, grp in df_curr.groupby('Product_Category'):
            cat_name = str(cat)
            c_rev = float(grp['Revenue'].sum()) if 'Revenue' in grp.columns else 0.0
            c_units = int(grp['Units_Sold'].sum()) if 'Units_Sold' in grp.columns else 0
            c_mkt = float(grp['Marketing_Spend'].sum()) if 'Marketing_Spend' in grp.columns else 0.0
            c_cust = int(grp['New_Customers'].sum()) if 'New_Customers' in grp.columns else 0
            c_profit = c_rev - c_mkt
            c_avg_p = (c_rev / c_units) if c_units > 0 else 0.0
            c_margin = (c_profit / c_rev * 100) if c_rev > 0 else 0.0

            p_rev = prev_cat_rev.get(cat_name, c_rev)
            p_units = prev_cat_units.get(cat_name, c_units)
            c_growth = round(((c_rev - p_rev) / p_rev * 100) if p_rev > 0 else 0.0, 1)
            u_growth = round(((c_units - p_units) / p_units * 100) if p_units > 0 else 0.0, 1)
            c_roas = round((c_rev / c_mkt) if c_mkt > 0 else 0.0, 2)

            rec = {
                'category': cat_name,
                'revenue': round(c_rev, 2),
                'units': c_units,
                'marketing_spend': round(c_mkt, 2),
                'profit': round(c_profit, 2),
                'avg_price': round(c_avg_p, 2),
                'profit_margin_pct': round(c_margin, 1),
                'revenue_share_pct': round((c_rev / curr_rev * 100) if curr_rev > 0 else 0.0, 1),
                'revenue_growth_pct': c_growth,
                'units_growth_pct': u_growth,
                'roas': c_roas
            }
            category_records.append(rec)
            metrics['categories'][cat_name] = rec

    # Rank categories
    sorted_by_rev = sorted(category_records, key=lambda x: x['revenue'], reverse=True)
    sorted_by_growth = sorted(category_records, key=lambda x: x['revenue_growth_pct'], reverse=True)
    sorted_by_margin = sorted(category_records, key=lambda x: x['profit_margin_pct'], reverse=True)
    sorted_by_roas = sorted(category_records, key=lambda x: x['roas'], reverse=True)

    # Risk Indicators
    top1_share = sorted_by_rev[0]['revenue_share_pct'] if sorted_by_rev else 0.0
    top2_share = sum(r['revenue_share_pct'] for r in sorted_by_rev[:2]) if len(sorted_by_rev) >= 2 else top1_share
    
    declining_cats = [r for r in category_records if r['revenue_growth_pct'] < 0]
    low_margin_cats = [r for r in category_records if r['profit_margin_pct'] < 10 or r['profit'] < 0]

    metrics['risk_indicators'] = {
        'top1_revenue_concentration_pct': top1_share,
        'top2_revenue_concentration_pct': top2_share,
        'concentration_risk_level': 'High' if top1_share > 45 or top2_share > 70 else ('Moderate' if top1_share > 30 else 'Low'),
        'declining_categories_count': len(declining_cats),
        'declining_categories': [d['category'] for d in declining_cats],
        'low_margin_categories_count': len(low_margin_cats),
        'low_margin_categories': [d['category'] for d in low_margin_cats],
        'cac_inflation_risk': 'Critical' if cac_change > 25 else ('Moderate' if cac_change > 10 else 'Healthy')
    }

    # Growth Opportunities
    high_potential = [r for r in sorted_by_growth if r['revenue_growth_pct'] > 5]
    under_marketed = [r for r in sorted_by_roas if r['roas'] >= 3.0 and r['marketing_spend'] < (curr_mkt / max(len(category_records), 1))]

    metrics['growth_vectors'] = {
        'top_growth_category': sorted_by_growth[0]['category'] if sorted_by_growth else 'None',
        'top_growth_rate': sorted_by_growth[0]['revenue_growth_pct'] if sorted_by_growth else 0.0,
        'highest_margin_category': sorted_by_margin[0]['category'] if sorted_by_margin else 'None',
        'highest_margin_pct': sorted_by_margin[0]['profit_margin_pct'] if sorted_by_margin else 0.0,
        'under_marketed_opportunities': [r['category'] for r in under_marketed]
    }

    return metrics

def generate_fallback_insights(metrics):
    """
    Generates rich, rule-based deterministic business insights when LLM is unavailable or offline.
    Guarantees consistent JSON output structure adhering strictly to the schema.
    """
    curr = metrics['current']
    prev = metrics['previous']
    cust = metrics['customer_metrics']
    mkt = metrics['marketing_efficiency']
    risks = metrics['risk_indicators']
    growth = metrics['growth_vectors']
    cats = list(metrics['categories'].values())

    # Sort categories for insights
    sorted_rev = sorted(cats, key=lambda x: x['revenue'], reverse=True)
    sorted_growth = sorted(cats, key=lambda x: x['revenue_growth_pct'], reverse=True)
    sorted_roas = sorted(cats, key=lambda x: x['roas'], reverse=True)
    sorted_margin = sorted(cats, key=lambda x: x['profit_margin_pct'])

    top_cat = sorted_rev[0]['category'] if sorted_rev else "Core Products"
    fastest_cat = sorted_growth[0]['category'] if sorted_growth else "Primary Segment"
    fastest_rate = sorted_growth[0]['revenue_growth_pct'] if sorted_growth else 0.0
    lagging_cat = sorted_margin[0]['category'] if sorted_margin else "Secondary Items"

    rev_change = prev.get('revenue_growth_pct', 0.0)
    rev_direction = "surged by" if rev_change > 0 else "declined by"
    profit_health_eval = "Healthy" if curr['profit_margin_pct'] >= 40 else ("Adequate" if curr['profit_margin_pct'] >= 20 else "Under Pressure")

    # 1. Executive Summary
    exec_summary = (
        f"Total revenue reached ₹{curr['revenue']:,.2f} with a net profit of ₹{curr['profit']:,.2f} "
        f"({curr['profit_margin_pct']}% margin). Revenue {rev_direction} {abs(rev_change)}% month-over-month. "
        f"Top volume was led by {top_cat}, while {fastest_cat} emerged as the fastest-growing category (+{fastest_rate}%). "
        f"Customer acquisition cost stands at ₹{cust['current_cac']:.2f} with an overall ROAS of {mkt['current_roas']}x."
    )

    # 2. Revenue Trends
    revenue_trends = {
        "summary": f"Business generated ₹{curr['revenue']:,.2f} compared to ₹{prev['revenue']:,.2f} in the prior period ({rev_change:+.1f}% YoY/MoM).",
        "key_drivers": [
            f"{top_cat} contributed {sorted_rev[0]['revenue_share_pct']}% of aggregate revenue (₹{sorted_rev[0]['revenue']:,.2f})." if sorted_rev else "Consistent revenue spread across baseline inventory.",
            f"{fastest_cat} demonstrated strong demand momentum with {fastest_rate:+.1f}% growth." if sorted_growth else "Steady sales pacing across all lines.",
            f"Marketing investment of ₹{curr['marketing_spend']:,.2f} generated ₹{curr['profit']:,.2f} in gross operating profit."
        ],
        "profit_health": f"Profit margin stands at {curr['profit_margin_pct']}% ({profit_health_eval}), supported by a marketing return on ad spend (ROAS) of {mkt['current_roas']}x."
    }

    # 3. Growth Opportunities (distinct actionable vectors)
    growth_opportunities = []
    if sorted_growth:
        growth_opportunities.append({
            "title": f"Scale High-Momentum Demand in {fastest_cat}",
            "category": fastest_cat,
            "impact": "High",
            "potential_revenue_gain": f"₹{(sorted_growth[0]['revenue'] * 0.25):,.2f}",
            "description": f"{fastest_cat} is expanding at {fastest_rate:+.1f}%. Increasing inventory availability and targeted digital campaigns could capture substantial unmet market demand.",
            "action_item": f"Allocate 15-20% incremental marketing budget to {fastest_cat} and optimize supply pipeline."
        })

    if sorted_roas and sorted_roas[0]['roas'] > 2.0:
        high_roas_cat = sorted_roas[0]['category']
        growth_opportunities.append({
            "title": f"Capitalize on High ROAS Efficiency in {high_roas_cat}",
            "category": high_roas_cat,
            "impact": "High",
            "potential_revenue_gain": f"₹{(sorted_roas[0]['revenue'] * 0.20):,.2f}",
            "description": f"{high_roas_cat} generates an outstanding ROAS of {sorted_roas[0]['roas']}x on modest ad spend (₹{sorted_roas[0]['marketing_spend']:,.2f}). It is currently under-leveraged.",
            "action_item": f"Ramp up paid channels for {high_roas_cat} to capture high-margin acquisition volume."
        })

    growth_opportunities.append({
        "title": "Optimized Customer Acquisition Expansion",
        "category": "Cross-Category",
        "impact": "Medium",
        "potential_revenue_gain": f"₹{(curr['revenue'] * 0.12):,.2f}",
        "description": f"Average revenue per customer is ₹{cust['revenue_per_customer']:,.2f} against a CAC of ₹{cust['current_cac']:,.2f}, yielding a favorable LTV-to-CAC foundation.",
        "action_item": "Introduce post-purchase loyalty rewards and category cross-selling bundles to raise basket size."
    })

    # 4. Low Performing Products
    low_performing_products = []
    # Identify categories with lowest margin or negative growth
    for c in sorted_margin[:2]:
        issue_str = []
        if c['profit_margin_pct'] < 20:
            issue_str.append(f"Compressed margin ({c['profit_margin_pct']}%)")
        if c['revenue_growth_pct'] < 0:
            issue_str.append(f"Declining sales ({c['revenue_growth_pct']}%)")
        if c['roas'] < 1.5:
            issue_str.append(f"Low ad conversion ({c['roas']}x ROAS)")
        if not issue_str:
            issue_str.append("Lower relative revenue contribution")

        low_performing_products.append({
            "category": c['category'],
            "issue": "; ".join(issue_str),
            "severity": "High" if c['profit'] < 0 or c['revenue_growth_pct'] < -15 else "Medium",
            "margin_impact": f"Current profit ₹{c['profit']:,.2f} with {c['profit_margin_pct']}% margin",
            "remediation": f"Audit supplier procurement costs for {c['category']}, discontinue low-velocity SKUs, or re-negotiate ad placements."
        })

    # 5. Customer Insights
    cac_change_str = f"increased by {abs(cust['cac_change_pct'])}%" if cust['cac_change_pct'] > 0 else f"improved by {abs(cust['cac_change_pct'])}%"
    customer_insights = {
        "acquisition_health": f"Acquired {curr['new_customers']} new customers this period ({prev['customer_growth_pct']:+.1f}% vs prior month).",
        "cac_analysis": f"Blended Customer Acquisition Cost is ₹{cust['current_cac']:.2f}, which {cac_change_str} compared to prior period (₹{cust['previous_cac']:.2f}).",
        "revenue_per_customer": f"Average customer spend is ₹{cust['revenue_per_customer']:,.2f}, delivering strong payback against acquisition expenses.",
        "actionable_takeaway": "Focus acquisition ad dollars on categories with the highest repeat purchase likelihood and cross-sell potential."
    }

    # 6. Risk Analysis
    risk_analysis = []
    if risks['concentration_risk_level'] in ['High', 'Moderate']:
        risk_analysis.append({
            "risk_type": "Revenue Concentration Risk",
            "severity": "Critical" if risks['concentration_risk_level'] == 'High' else "Warning",
            "impact": f"Top category ({top_cat}) accounts for {risks['top1_revenue_concentration_pct']}% of total revenue. Any disruption in this vertical will heavily impact cash flows.",
            "mitigation": "Diversify marketing investments into secondary growth categories to establish balanced multi-pillar revenue streams."
        })

    if cust['cac_change_pct'] > 15:
        risk_analysis.append({
            "risk_type": "Rising Customer Acquisition Cost (CAC Inflation)",
            "severity": "Warning",
            "impact": f"CAC rose {cust['cac_change_pct']}% from ₹{cust['previous_cac']:.2f} to ₹{cust['current_cac']:.2f}, threatening unit economics if conversion rates plateau.",
            "mitigation": "Refine audience targeting, pause underperforming ad sets, and implement referral loops to lower blended CAC."
        })

    if risks['declining_categories']:
        risk_analysis.append({
            "risk_type": "Sales Contraction in Specific Verticals",
            "severity": "Moderate",
            "impact": f"{', '.join(risks['declining_categories'])} recorded negative month-over-month revenue velocity.",
            "mitigation": "Execute inventory clearance for stagnant SKUs and reallocate working capital into fast-moving product lines."
        })
    else:
        risk_analysis.append({
            "risk_type": "Supply Chain & Stockout Vulnerability",
            "severity": "Moderate",
            "impact": f"Accelerated demand in {fastest_cat} creates stockout vulnerability if supplier lead times exceed 14 days.",
            "mitigation": "Establish safety stock thresholds and automate supplier reorder triggers."
        })

    # 7. Smart Recommendations
    smart_recommendations = [
        {
            "priority": "Immediate",
            "action": f"Reallocate 15% of marketing budget from {lagging_cat} to {fastest_cat} and {top_cat}.",
            "expected_outcome": "Estimated 8-12% uplift in overall ROAS within 30 days.",
            "target_area": "Marketing & Budget Allocation"
        },
        {
            "priority": "Short-term",
            "action": f"Establish automated replenishment for top sellers in {top_cat} to safeguard peak period fulfilment.",
            "expected_outcome": "Eliminates potential revenue loss from stockout occurrences.",
            "target_area": "Inventory & Operations"
        },
        {
            "priority": "Long-term",
            "action": "Implement customer retention and automated re-engagement workflows for new buyers.",
            "expected_outcome": "Increases customer lifetime value (LTV) and compresses effective CAC by 15-20%.",
            "target_area": "Customer Retention & CRM"
        }
    ]

    return {
        "engine": "statistical_heuristic_engine",
        "executive_summary": exec_summary,
        "revenue_trends": revenue_trends,
        "growth_opportunities": growth_opportunities,
        "low_performing_products": low_performing_products,
        "customer_insights": customer_insights,
        "risk_analysis": risk_analysis,
        "smart_recommendations": smart_recommendations,
        "computed_metrics": metrics
    }

def generate_ai_insights(df_curr, df_prev=None):
    """
    Primary interface for AI Insights Engine.
    Computes rigorous analytical metrics, then attempts Gemini LLM synthesis.
    Falls back gracefully to deterministic rule-based insights if LLM is unavailable.
    """
    metrics = compute_data_metrics(df_curr, df_prev)
    api_key = get_api_key()

    if not api_key:
        print("[AI Insights] No Gemini API key detected. Generating deterministic statistical insights.")
        return generate_fallback_insights(metrics)

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser

        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=api_key,
            temperature=0.2
        )

        prompt_str = """You are BusinessPulse AI's Chief Analytics Officer and Executive Business Intelligence Engine.
Analyze the following business metrics extracted from company sales, revenue, marketing spend, and customer data:

=== BUSINESS METRICS SUMMARY ===
{metrics_json}

Your task is to generate deep, executive-grade business insights structured strictly in valid JSON format.
Adhere strictly to this JSON schema without any markdown wrapping or external text:
{{
  "executive_summary": "High-level summary of financial health, growth, and top priorities (2-3 sentences)",
  "revenue_trends": {{
    "summary": "Detailed narrative of revenue and profit dynamics",
    "key_drivers": ["Driver 1 with specific amounts and metrics", "Driver 2", "Driver 3"],
    "profit_health": "Evaluation of profit margins and marketing efficiency"
  }},
  "growth_opportunities": [
    {{
      "title": "Clear opportunity title",
      "category": "Target product category or segment",
      "impact": "High | Medium | Low",
      "potential_revenue_gain": "Estimated ₹ gain or percentage",
      "description": "Specific observation on why this opportunity exists",
      "action_item": "Concrete actionable next step"
    }}
  ],
  "low_performing_products": [
    {{
      "category": "Product category name",
      "issue": "Specific underperformance issue (margin, sales drop, high CAC)",
      "severity": "High | Medium | Low",
      "margin_impact": "Profit or margin details",
      "remediation": "Recommended corrective action"
    }}
  ],
  "customer_insights": {{
    "acquisition_health": "Assessment of customer acquisition velocity",
    "cac_analysis": "Evaluation of Customer Acquisition Cost (CAC) and trend",
    "revenue_per_customer": "Analysis of average revenue per customer",
    "actionable_takeaway": "Specific recommendation for customer monetization"
  }},
  "risk_analysis": [
    {{
      "risk_type": "Risk classification (e.g., Concentration, Margin, Churn, Stockout)",
      "severity": "Critical | Warning | Moderate",
      "impact": "Concrete financial or operational danger",
      "mitigation": "Pre-emptive risk mitigation strategy"
    }}
  ],
  "smart_recommendations": [
    {{
      "priority": "Immediate | Short-term | Long-term",
      "action": "Clear, direct imperative action",
      "expected_outcome": "Measurable business outcome",
      "target_area": "Business domain (e.g., Marketing, Pricing, Inventory, CRM)"
    }}
  ]
}}

Ensure all monetary values use Indian Rupee (₹) context and exact figures provided in the metrics. Return ONLY the valid JSON."""

        prompt = ChatPromptTemplate.from_template(prompt_str)
        chain = prompt | llm | StrOutputParser()

        metrics_clean = json.dumps(metrics, indent=2)
        raw_response = chain.invoke({"metrics_json": metrics_clean})

        # Clean JSON markdown fences
        cleaned = re.sub(r'^```(?:json)?\s*', '', raw_response.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r'\s*```$', '', cleaned.strip(), flags=re.MULTILINE)

        parsed_json = json.loads(cleaned)
        parsed_json["engine"] = "gemini_ai_engine"
        parsed_json["computed_metrics"] = metrics
        return parsed_json

    except Exception as e:
        print(f"[AI Insights] Gemini generation error ({e}). Falling back to deterministic engine.")
        fallback = generate_fallback_insights(metrics)
        fallback["engine_warning"] = f"LLM generation failed: {str(e)}"
        return fallback

