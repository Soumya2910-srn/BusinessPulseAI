import os
import json
import warnings
from datetime import datetime

# Filter out the PyFPDF / fpdf2 namespace warning if present
warnings.filterwarnings('ignore', category=UserWarning)

from fpdf import FPDF

# Color Palette Constants (RGB)
C_PRIMARY = (15, 23, 42)       # Slate 900 (Deep Navy)
C_ACCENT = (2, 132, 199)       # Sky 600 (Primary Blue)
C_PURPLE = (124, 58, 237)      # Violet 600
C_PINK = (219, 39, 119)        # Pink 600
C_EMERALD = (16, 185, 129)     # Emerald 500 (Positive/Green)
C_ROSE = (225, 29, 72)         # Rose 600 (Negative/Red)
C_AMBER = (217, 119, 6)        # Amber 600 (Warning)
C_BG_LIGHT = (248, 250, 252)   # Slate 50
C_BORDER = (226, 232, 240)     # Slate 200
C_TEXT_DARK = (30, 41, 59)     # Slate 800
C_TEXT_MUTED = (100, 116, 139) # Slate 500


def clean_str(val):
    """Sanitizes text for PDF encoding and cleans special unicode symbols."""
    if val is None:
        return ""
    text = str(val)
    # Replace Indian Rupee symbol with INR representation for standard font encoding
    text = text.replace('₹', 'INR ')
    # Replace common unicode quotes and dashes with ascii equivalents
    text = text.replace('–', '-').replace('—', '-').replace('“', '"').replace('”', '"')
    text = text.replace('‘', "'").replace('’', "'").replace('•', '-')
    # Keep printable ASCII/Latin-1 characters
    return text.encode('latin-1', 'replace').decode('latin-1')


def format_inr(val):
    """Formats a number in Indian denomination format."""
    try:
        val = float(val)
        is_neg = val < 0
        val = abs(val)
        int_part = int(val)
        dec_part = int(round((val - int_part) * 100))
        
        s = str(int_part)
        if len(s) <= 3:
            formatted = s
        else:
            last3 = s[-3:]
            rest = s[:-3]
            chunks = []
            while len(rest) > 2:
                chunks.append(rest[-2:])
                rest = rest[:-2]
            if rest:
                chunks.append(rest)
            chunks.reverse()
            formatted = ",".join(chunks) + "," + last3
            
        sign = "-" if is_neg else ""
        if dec_part > 0:
            return f"{sign}{formatted}.{dec_part:02d}"
        return f"{sign}{formatted}"
    except Exception:
        return str(val)


class BusinessPulsePDF(FPDF):
    """Custom Executive PDF Document for BusinessPulse AI."""
    
    def __init__(self, analysis_id=None, report_title="Executive Analytics Report"):
        super().__init__(orientation='P', unit='mm', format='A4')
        self.analysis_id = analysis_id or "N/A"
        self.report_title = report_title
        self.set_auto_page_break(auto=True, margin=18)
        
        # Try loading Arial if available on Windows, otherwise standard Helvetica
        self.font_family = 'Helvetica'
        font_reg = 'C:/Windows/Fonts/arial.ttf'
        font_bold = 'C:/Windows/Fonts/arialbd.ttf'
        font_italic = 'C:/Windows/Fonts/ariali.ttf'
        font_bi = 'C:/Windows/Fonts/arialbi.ttf'
        if os.path.exists(font_reg):
            try:
                self.add_font('ArialApp', '', font_reg)
                if os.path.exists(font_bold):
                    self.add_font('ArialApp', 'B', font_bold)
                if os.path.exists(font_italic):
                    self.add_font('ArialApp', 'I', font_italic)
                if os.path.exists(font_bi):
                    self.add_font('ArialApp', 'BI', font_bi)
                self.font_family = 'ArialApp'
            except Exception:
                self.font_family = 'Helvetica'

    def header(self):
        # Top gradient-style accent bar
        self.set_fill_color(*C_ACCENT)
        self.rect(0, 0, 105, 3.5, 'F')
        self.set_fill_color(*C_PURPLE)
        self.rect(105, 0, 60, 3.5, 'F')
        self.set_fill_color(*C_PINK)
        self.rect(165, 0, 45, 3.5, 'F')

        # Header title only on pages > 1
        if self.page_no() > 1:
            self.set_y(8)
            self.set_font(self.font_family, 'B', 8)
            self.set_text_color(*C_TEXT_MUTED)
            self.cell(0, 5, clean_str(f"BUSINESSPULSE AI  |  {self.report_title}  (Analysis #{self.analysis_id})"), 0, 0, 'L')
            self.cell(0, 5, clean_str(datetime.now().strftime('%b %d, %Y')), 0, 1, 'R')
            self.set_draw_color(*C_BORDER)
            self.line(10, 14, 200, 14)
            self.ln(6)

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(*C_BORDER)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(2)
        self.set_font(self.font_family, '', 7.5)
        self.set_text_color(*C_TEXT_MUTED)
        self.cell(0, 4, clean_str("Confidential - Generated automatically by BusinessPulse AI Engine"), 0, 0, 'L')
        self.cell(0, 4, clean_str(f"Page {self.page_no()} of {{nb}}"), 0, 0, 'R')

    def section_heading(self, title, subtitle=None):
        """Draws a clean styled section header with colored indicator bar."""
        self.ln(3)
        y = self.get_y()
        self.set_fill_color(*C_ACCENT)
        self.rect(10, y, 3.5, 7, 'F')
        
        self.set_xy(16, y)
        self.set_font(self.font_family, 'B', 12)
        self.set_text_color(*C_PRIMARY)
        self.cell(0, 7, clean_str(title), 0, 1, 'L')
        
        if subtitle:
            self.set_xy(16, self.get_y())
            self.set_font(self.font_family, '', 8)
            self.set_text_color(*C_TEXT_MUTED)
            self.cell(0, 4, clean_str(subtitle), 0, 1, 'L')
            self.ln(2)
        else:
            self.ln(2)

    def draw_kpi_card(self, x, y, w, h, label, value, subtext="", change_pct=None):
        """Draws a rounded KPI stat box."""
        # Card Background
        self.set_fill_color(*C_BG_LIGHT)
        self.set_draw_color(*C_BORDER)
        self.rect(x, y, w, h, 'DF')
        
        # Top mini bar
        self.set_fill_color(*C_ACCENT)
        self.rect(x, y, w, 1.5, 'F')
        
        # Label
        self.set_xy(x + 3, y + 3.5)
        self.set_font(self.font_family, 'B', 7.5)
        self.set_text_color(*C_TEXT_MUTED)
        self.cell(w - 6, 4, clean_str(label.upper()), 0, 1, 'L')
        
        # Value
        self.set_xy(x + 3, y + 8)
        self.set_font(self.font_family, 'B', 11.5)
        self.set_text_color(*C_PRIMARY)
        self.cell(w - 6, 6, clean_str(value), 0, 1, 'L')
        
        # Subtext / growth badge
        self.set_xy(x + 3, y + 14)
        if change_pct is not None:
            try:
                pct = float(change_pct)
                is_pos = pct >= 0
                sign = "+" if is_pos else ""
                color = C_EMERALD if is_pos else C_ROSE
                self.set_font(self.font_family, 'B', 7.5)
                self.set_text_color(*color)
                self.cell(16, 4, clean_str(f"{sign}{pct}%"), 0, 0, 'L')
                
                self.set_font(self.font_family, '', 7)
                self.set_text_color(*C_TEXT_MUTED)
                self.cell(w - 22, 4, clean_str(subtext), 0, 1, 'L')
            except Exception:
                self.set_font(self.font_family, '', 7)
                self.set_text_color(*C_TEXT_MUTED)
                self.cell(w - 6, 4, clean_str(subtext), 0, 1, 'L')
        else:
            self.set_font(self.font_family, '', 7)
            self.set_text_color(*C_TEXT_MUTED)
            self.cell(w - 6, 4, clean_str(subtext), 0, 1, 'L')

    def draw_badge(self, text, severity="normal"):
        """Returns colored text configuration for status tags."""
        text = clean_str(text)
        sev = str(severity).lower()
        if "critical" in sev or "high" in sev or "danger" in sev:
            return f"[CRITICAL: {text}]"
        elif "warning" in sev or "approaching" in sev or "medium" in sev:
            return f"[WARNING: {text}]"
        elif "healthy" in sev or "normal" in sev or "balanced" in sev:
            return f"[HEALTHY: {text}]"
        return f"[{text}]"


def generate_analysis_pdf_bytes(analysis_record, user=None):
    """
    Builds a professional executive PDF report from an AnalysisHistory database record.
    Returns the generated PDF file bytes.
    """
    analytics = json.loads(analysis_record.analytics_json)
    summary = analytics.get('summary', {})
    cat_stats = analytics.get('category_stats', {})
    insights = analytics.get('insights', {})
    forecasting = analytics.get('forecasting', {})
    
    pdf = BusinessPulsePDF(
        analysis_id=analysis_record.id,
        report_title="Executive Performance & Predictive Analytics Report"
    )
    pdf.alias_nb_pages()
    
    # ═════════════════════════════════════════════════════════════════════════
    # PAGE 1: COVER HEADER, METADATA & EXECUTIVE KPI SCORECARD
    # ═════════════════════════════════════════════════════════════════════════
    pdf.add_page()
    
    # Top Brand Banner
    pdf.set_y(10)
    pdf.set_font(pdf.font_family, 'B', 20)
    pdf.set_text_color(*C_PRIMARY)
    pdf.cell(120, 8, clean_str("BusinessPulse AI"), 0, 0, 'L')
    
    pdf.set_font(pdf.font_family, 'B', 8.5)
    pdf.set_text_color(*C_ACCENT)
    pdf.cell(70, 8, clean_str(f"ANALYSIS REPORT #{analysis_record.id}"), 0, 1, 'R')
    
    pdf.set_font(pdf.font_family, '', 9.5)
    pdf.set_text_color(*C_TEXT_MUTED)
    pdf.cell(0, 5, clean_str("Automated Executive Business Intelligence, AI Insights & Inventory Optimization"), 0, 1, 'L')
    pdf.ln(3)
    
    # Metadata Box
    pdf.set_fill_color(*C_BG_LIGHT)
    pdf.set_draw_color(*C_BORDER)
    pdf.rect(10, pdf.get_y(), 190, 20, 'DF')
    
    my_y = pdf.get_y() + 2.5
    pdf.set_xy(14, my_y)
    pdf.set_font(pdf.font_family, 'B', 8)
    pdf.set_text_color(*C_TEXT_MUTED)
    pdf.cell(32, 4.5, clean_str("GENERATED FOR:"), 0, 0)
    pdf.set_font(pdf.font_family, 'B', 8.5)
    pdf.set_text_color(*C_PRIMARY)
    username = user.username if user else "Business User"
    email = user.email if user else "user@businesspulse.ai"
    pdf.cell(60, 4.5, clean_str(f"{username} ({email})"), 0, 0)
    
    pdf.set_font(pdf.font_family, 'B', 8)
    pdf.set_text_color(*C_TEXT_MUTED)
    pdf.cell(28, 4.5, clean_str("REPORT DATE:"), 0, 0)
    pdf.set_font(pdf.font_family, '', 8.5)
    pdf.set_text_color(*C_PRIMARY)
    created_str = analysis_record.created_at.strftime('%b %d, %Y - %I:%M %p') if hasattr(analysis_record, 'created_at') and analysis_record.created_at else datetime.now().strftime('%b %d, %Y')
    pdf.cell(60, 4.5, clean_str(created_str), 0, 1)
    
    pdf.set_xy(14, my_y + 5.5)
    pdf.set_font(pdf.font_family, 'B', 8)
    pdf.set_text_color(*C_TEXT_MUTED)
    pdf.cell(32, 4.5, clean_str("BASELINE DATASET:"), 0, 0)
    pdf.set_font(pdf.font_family, '', 8)
    pdf.set_text_color(*C_PRIMARY)
    pdf.cell(60, 4.5, clean_str(analysis_record.prev_filename or "Previous Period CSV"), 0, 0)
    
    pdf.set_font(pdf.font_family, 'B', 8)
    pdf.set_text_color(*C_TEXT_MUTED)
    pdf.cell(28, 4.5, clean_str("CURRENT DATASET:"), 0, 0)
    pdf.set_font(pdf.font_family, '', 8)
    pdf.set_text_color(*C_PRIMARY)
    pdf.cell(60, 4.5, clean_str(analysis_record.curr_filename or "Current Period CSV"), 0, 1)
    
    pdf.set_xy(14, my_y + 10.5)
    pdf.set_font(pdf.font_family, 'B', 8)
    pdf.set_text_color(*C_TEXT_MUTED)
    pdf.cell(32, 4.5, clean_str("INTELLIGENCE ENGINE:"), 0, 0)
    engine_name = "Gemini Pro AI Model" if insights.get('engine') == 'gemini_ai_engine' else "Deterministic Heuristic Engine"
    pdf.set_font(pdf.font_family, 'B', 8)
    pdf.set_text_color(*C_PURPLE)
    pdf.cell(60, 4.5, clean_str(engine_name), 0, 1)
    
    pdf.set_y(pdf.get_y() + 6)
    
    # ── KPI Cards Grid (4 columns) ─────────────────────────────────────────────
    pdf.section_heading("Executive Key Performance Indicators", "Comparative baseline vs current period performance")
    
    card_w = 45
    card_h = 20
    spacing = 3.3
    start_x = 10
    start_y = pdf.get_y()
    
    # Card 1: Total Revenue
    curr_rev = summary.get('curr_revenue', 0.0)
    prev_rev = summary.get('prev_revenue', 0.0)
    rev_growth = summary.get('revenue_growth', 0.0)
    pdf.draw_kpi_card(
        start_x, start_y, card_w, card_h,
        "Total Revenue",
        f"INR {format_inr(curr_rev)}",
        f"vs INR {format_inr(prev_rev)}",
        rev_growth
    )
    
    # Card 2: Units Sold
    curr_units = summary.get('curr_units', 0)
    prev_units = summary.get('prev_units', 0)
    units_growth = summary.get('units_growth', 0.0)
    pdf.draw_kpi_card(
        start_x + (card_w + spacing), start_y, card_w, card_h,
        "Units Sold",
        f"{curr_units:,}",
        f"vs {prev_units:,}",
        units_growth
    )
    
    # Card 3: Customers
    curr_cust = summary.get('curr_customers', 0)
    prev_cust = summary.get('prev_customers', 0)
    cust_growth = summary.get('customers_growth', 0.0)
    pdf.draw_kpi_card(
        start_x + (card_w + spacing) * 2, start_y, card_w, card_h,
        "New Customers",
        f"{curr_cust:,}",
        f"vs {prev_cust:,}",
        cust_growth
    )
    
    # Card 4: ML Forecast
    fc_rev = summary.get('forecasted_revenue', 0.0)
    ml_growth = summary.get('ml_projected_growth', rev_growth)
    pdf.draw_kpi_card(
        start_x + (card_w + spacing) * 3, start_y, card_w, card_h,
        "ML Next Month",
        f"INR {format_inr(fc_rev)}",
        "Predictive Target",
        ml_growth
    )
    
    pdf.set_y(start_y + card_h + 4)
    
    # ── Executive Summary Narrative ──────────────────────────────────────────
    exec_text = insights.get('executive_summary', '')
    if exec_text:
        pdf.set_fill_color(240, 249, 255) # Light Sky
        pdf.set_draw_color(186, 230, 253)
        narrative_y = pdf.get_y()
        
        pdf.set_font(pdf.font_family, 'B', 8.5)
        pdf.set_text_color(*C_ACCENT)
        pdf.cell(0, 5, clean_str("EXECUTIVE STRATEGY BRIEF"), 0, 1)
        
        pdf.set_font(pdf.font_family, '', 8.5)
        pdf.set_text_color(*C_TEXT_DARK)
        pdf.multi_cell(0, 4.2, clean_str(exec_text))
        pdf.ln(3)

    # ── Product Category Breakdown Table ──────────────────────────────────────
    pdf.section_heading("Product Category Revenue Breakdown", "Current period sales volume, average price and margin contribution")
    
    headers = ["Category", "Revenue (INR)", "Units Sold", "Avg Price (INR)", "Profit (INR)", "Margin %"]
    col_w = [42, 38, 26, 30, 32, 22]
    
    # Header Row
    pdf.set_fill_color(*C_PRIMARY)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(pdf.font_family, 'B', 8)
    for i, h in enumerate(headers):
        align = 'L' if i == 0 else 'R'
        pdf.cell(col_w[i], 6.5, clean_str(h), 0, 0, align, True)
    pdf.ln(6.5)
    
    # Table Rows
    pdf.set_font(pdf.font_family, '', 8)
    pdf.set_text_color(*C_TEXT_DARK)
    total_rev = curr_rev if curr_rev > 0 else 1.0
    
    row_count = 0
    for cat_name, stats in cat_stats.items():
        row_count += 1
        fill = (row_count % 2 == 0)
        pdf.set_fill_color(248, 250, 252) if fill else pdf.set_fill_color(255, 255, 255)
        
        c_rev = stats.get('revenue', 0.0)
        c_units = stats.get('units', 0)
        c_price = stats.get('avg_price', 0.0)
        c_profit = stats.get('profit', 0.0)
        margin = round((c_profit / c_rev * 100) if c_rev > 0 else 0, 1)
        
        pdf.cell(col_w[0], 5.8, clean_str(cat_name), 'B', 0, 'L', fill)
        pdf.cell(col_w[1], 5.8, clean_str(format_inr(c_rev)), 'B', 0, 'R', fill)
        pdf.cell(col_w[2], 5.8, clean_str(f"{c_units:,}"), 'B', 0, 'R', fill)
        pdf.cell(col_w[3], 5.8, clean_str(format_inr(c_price)), 'B', 0, 'R', fill)
        pdf.cell(col_w[4], 5.8, clean_str(format_inr(c_profit)), 'B', 0, 'R', fill)
        pdf.cell(col_w[5], 5.8, clean_str(f"{margin}%"), 'B', 1, 'R', fill)

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE 2: AI STRATEGIC INSIGHTS, OPPORTUNITIES & RISK ASSESSMENT
    # ═════════════════════════════════════════════════════════════════════════
    pdf.add_page()
    
    pdf.section_heading("Growth Opportunities & Strategic Drivers", "High-potential revenue levers identified by the analytics engine")
    
    # Revenue Trends Drivers
    rev_trends = insights.get('revenue_trends', {})
    if isinstance(rev_trends, dict):
        trend_summary = rev_trends.get('summary', '')
        if trend_summary:
            pdf.set_font(pdf.font_family, 'I', 8)
            pdf.set_text_color(*C_TEXT_MUTED)
            pdf.multi_cell(0, 4, clean_str(trend_summary))
            pdf.ln(2)
            
        drivers = rev_trends.get('primary_drivers', [])
        if drivers:
            pdf.set_font(pdf.font_family, 'B', 8)
            pdf.set_text_color(*C_EMERALD)
            pdf.cell(0, 4.5, clean_str("Growth Accelerators:"), 0, 1)
            pdf.set_font(pdf.font_family, '', 8)
            pdf.set_text_color(*C_TEXT_DARK)
            for d in drivers[:3]:
                pdf.set_x(14)
                pdf.multi_cell(186, 4, clean_str(f"- {d}"))
            pdf.ln(2)

    # Growth Opportunities Table/List
    growth_opps = insights.get('growth_opportunities', [])
    if growth_opps:
        pdf.set_font(pdf.font_family, 'B', 8.5)
        pdf.set_text_color(*C_PRIMARY)
        pdf.cell(0, 5, clean_str("Target Growth Opportunities:"), 0, 1)
        
        for opp in growth_opps[:3]:
            pdf.set_fill_color(*C_BG_LIGHT)
            pdf.set_draw_color(*C_BORDER)
            y_box = pdf.get_y()
            
            title = opp.get('title') or opp.get('target_category') or 'Growth Opportunity'
            cat = opp.get('category', 'Cross-Category')
            impact = opp.get('impact', 'High')
            action = opp.get('action', '')
            gain = opp.get('projected_gain', 0)
            
            pdf.set_font(pdf.font_family, 'B', 8)
            pdf.set_text_color(*C_ACCENT)
            gain_str = f" | Projected Gain: INR {format_inr(gain)}" if gain else ""
            pdf.cell(0, 4.5, clean_str(f"* {title} [{cat}] - Impact: {impact}{gain_str}"), 0, 1)
            
            if action:
                pdf.set_font(pdf.font_family, '', 7.8)
                pdf.set_text_color(*C_TEXT_DARK)
                pdf.set_x(14)
                pdf.multi_cell(0, 3.8, clean_str(f"Action: {action}"))
            pdf.ln(1.5)
        pdf.ln(2)

    # Underperforming Products Table
    low_prods = insights.get('low_performing_products', [])
    if low_prods:
        pdf.section_heading("Underperforming Segments & Remediation", "Identified margin drags and operational bottlenecks")
        
        pdf.set_fill_color(254, 242, 242) # Red/Rose tint
        pdf.set_font(pdf.font_family, 'B', 7.5)
        pdf.set_text_color(*C_ROSE)
        pdf.cell(40, 5, clean_str("Product / Category"), 0, 0, 'L', True)
        pdf.cell(60, 5, clean_str("Identified Issue"), 0, 0, 'L', True)
        pdf.cell(20, 5, clean_str("Severity"), 0, 0, 'C', True)
        pdf.cell(70, 5, clean_str("Recommended Action"), 0, 1, 'L', True)
        
        pdf.set_font(pdf.font_family, '', 7.5)
        pdf.set_text_color(*C_TEXT_DARK)
        for lp in low_prods[:4]:
            p_name = lp.get('category') or lp.get('product') or 'Item'
            issue = lp.get('issue', 'Margin compression')
            sev = lp.get('severity', 'Medium')
            act = lp.get('action', 'Review pricing structure')
            
            pdf.cell(40, 5, clean_str(p_name), 'B', 0, 'L')
            pdf.cell(60, 5, clean_str(issue[:45]), 'B', 0, 'L')
            pdf.cell(20, 5, clean_str(sev), 'B', 0, 'C')
            pdf.cell(70, 5, clean_str(act[:52]), 'B', 1, 'L')
        pdf.ln(3)

    # Risk Assessment Matrix
    risks = insights.get('risk_analysis', [])
    if risks:
        pdf.section_heading("Enterprise Risk Assessment Matrix", "Evaluation of concentration, demand volatility and supply chain exposure")
        
        for r in risks[:3]:
            r_type = r.get('risk_type', 'Risk')
            sev = r.get('severity', 'Warning')
            impact = r.get('impact', '')
            mitigation = r.get('mitigation', '')
            
            color = C_ROSE if 'crit' in str(sev).lower() else C_AMBER
            pdf.set_font(pdf.font_family, 'B', 8)
            pdf.set_text_color(*color)
            pdf.cell(0, 4.5, clean_str(f"[{sev.upper()}]  {r_type}"), 0, 1)
            
            pdf.set_font(pdf.font_family, '', 7.8)
            pdf.set_text_color(*C_TEXT_DARK)
            if impact:
                pdf.set_x(14)
                pdf.multi_cell(186, 3.8, clean_str(f"Impact: {impact}"))
            if mitigation:
                pdf.set_font(pdf.font_family, 'I', 7.5)
                pdf.set_text_color(*C_TEXT_MUTED)
                pdf.set_x(14)
                pdf.multi_cell(186, 3.8, clean_str(f"Mitigation: {mitigation}"))
            pdf.ln(1.5)

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE 3: PREDICTIVE FORECASTING & INVENTORY OPTIMIZATION
    # ═════════════════════════════════════════════════════════════════════════
    pdf.add_page()
    
    # ── Multi-Period Sales Forecast ───────────────────────────────────────────
    pdf.section_heading("Predictive Multi-Period Revenue Forecast", "Statistical projection models with 95% confidence intervals")
    
    sales_fc = forecasting.get('sales_forecast', {})
    periods = sales_fc.get('period_projections', [])
    
    if periods:
        fc_headers = ["Forecast Horizon", "Conservative (INR)", "Expected Baseline (INR)", "Optimistic (INR)"]
        fc_cols = [45, 48, 49, 48]
        
        pdf.set_fill_color(*C_PRIMARY)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font(pdf.font_family, 'B', 8)
        for i, h in enumerate(fc_headers):
            align = 'L' if i == 0 else 'R'
            pdf.cell(fc_cols[i], 6, clean_str(h), 0, 0, align, True)
        pdf.ln(6)
        
        pdf.set_font(pdf.font_family, '', 8)
        pdf.set_text_color(*C_TEXT_DARK)
        for i, p in enumerate(periods):
            fill = (i % 2 == 1)
            pdf.set_fill_color(248, 250, 252) if fill else pdf.set_fill_color(255, 255, 255)
            
            lbl = p.get('label') or f"Period {p.get('period_index', i+1)}"
            exp = p.get('expected_revenue', 0.0)
            cons = p.get('conservative', exp * 0.9)
            opt = p.get('optimistic', exp * 1.15)
            
            pdf.cell(fc_cols[0], 5.8, clean_str(lbl), 'B', 0, 'L', fill)
            pdf.cell(fc_cols[1], 5.8, clean_str(format_inr(cons)), 'B', 0, 'R', fill)
            pdf.cell(fc_cols[2], 5.8, clean_str(format_inr(exp)), 'B', 0, 'R', fill)
            pdf.cell(fc_cols[3], 5.8, clean_str(format_inr(opt)), 'B', 1, 'R', fill)
        pdf.ln(3)

    # ── Marketing Sensitivity Matrix ──────────────────────────────────────────
    mkt_sens = sales_fc.get('marketing_sensitivity', [])
    if mkt_sens:
        pdf.set_font(pdf.font_family, 'B', 8.5)
        pdf.set_text_color(*C_PRIMARY)
        pdf.cell(0, 5, clean_str("Marketing Budget Sensitivity & ROI Simulator:"), 0, 1)
        
        m_headers = ["Spend Adjustment", "Marketing Budget (INR)", "Projected Revenue (INR)", "Estimated ROI %"]
        m_cols = [45, 48, 49, 48]
        
        pdf.set_fill_color(*C_ACCENT)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font(pdf.font_family, 'B', 7.5)
        for i, h in enumerate(m_headers):
            align = 'L' if i == 0 else 'R'
            pdf.cell(m_cols[i], 5.5, clean_str(h), 0, 0, align, True)
        pdf.ln(5.5)
        
        pdf.set_font(pdf.font_family, '', 7.5)
        pdf.set_text_color(*C_TEXT_DARK)
        for i, m in enumerate(mkt_sens[:5]):
            fill = (i % 2 == 1)
            pdf.set_fill_color(248, 250, 252) if fill else pdf.set_fill_color(255, 255, 255)
            
            chg = m.get('marketing_change_pct', 0)
            sign = "+" if chg > 0 else ""
            lbl = f"{sign}{chg}% Budget" if chg != 0 else "Baseline Budget"
            b_val = m.get('marketing_budget', 0.0)
            r_val = m.get('projected_revenue', 0.0)
            roi_val = m.get('estimated_roi_pct', 0.0)
            
            pdf.cell(m_cols[0], 5, clean_str(lbl), 'B', 0, 'L', fill)
            pdf.cell(m_cols[1], 5, clean_str(format_inr(b_val)), 'B', 0, 'R', fill)
            pdf.cell(m_cols[2], 5, clean_str(format_inr(r_val)), 'B', 0, 'R', fill)
            pdf.cell(m_cols[3], 5, clean_str(f"{roi_val:,.1f}%"), 'B', 1, 'R', fill)
        pdf.ln(4)

    # ── Inventory Optimization & Stock Health ─────────────────────────────────
    inv_fc = forecasting.get('inventory_forecast', {})
    inv_items = inv_fc.get('items', [])
    if not inv_items and isinstance(inv_fc, dict):
        # Support dict format if items list isn't explicit
        inv_items = [v for k, v in inv_fc.items() if isinstance(v, dict) and 'days_of_stock_remaining' in v]

    pdf.section_heading("Inventory Optimization & Stockout Risk", "Run rates, days of stock remaining, safety stock and reorder targets")
    
    # Inventory Summary Stat Line
    health_score = inv_fc.get('inventory_health_score', '92%')
    critical_alerts = inv_fc.get('critical_stockout_alerts', 0)
    lead_time = inv_fc.get('lead_time_days_assumed', 10)
    
    pdf.set_font(pdf.font_family, 'B', 8)
    pdf.set_text_color(*C_TEXT_MUTED)
    pdf.cell(0, 4.5, clean_str(f"System Health: {health_score}  |  Critical Alerts: {critical_alerts}  |  Assumed Supplier Lead Time: {lead_time} Days"), 0, 1)
    pdf.ln(1.5)
    
    if inv_items:
        i_headers = ["Category", "Run Rate/Day", "Days Left", "Risk Status", "Safety Stock", "Reorder Point", "Restock Capital"]
        i_cols = [34, 25, 20, 26, 25, 27, 33]
        
        pdf.set_fill_color(*C_PRIMARY)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font(pdf.font_family, 'B', 7.5)
        for i, h in enumerate(i_headers):
            align = 'L' if i in (0, 3) else 'R'
            pdf.cell(i_cols[i], 6, clean_str(h), 0, 0, align, True)
        pdf.ln(6)
        
        pdf.set_font(pdf.font_family, '', 7.5)
        pdf.set_text_color(*C_TEXT_DARK)
        for idx, it in enumerate(inv_items):
            fill = (idx % 2 == 1)
            pdf.set_fill_color(248, 250, 252) if fill else pdf.set_fill_color(255, 255, 255)
            
            c_name = it.get('category', 'Category')
            run_rate = it.get('daily_run_rate', 0.0)
            days_left = it.get('days_of_stock_remaining', 0)
            status = it.get('risk_status') or it.get('stockout_risk_status') or 'Healthy'
            s_stock = it.get('safety_stock', 0)
            rop = it.get('reorder_point', 0)
            cap = it.get('estimated_restock_capital_inr') or it.get('restock_capital_required') or 0.0
            
            # Status badge formatting
            st_clean = clean_str(status)
            if 'crit' in status.lower():
                st_disp = f"* {st_clean}"
            elif 'warn' in status.lower():
                st_disp = f"! {st_clean}"
            else:
                st_disp = st_clean
                
            pdf.cell(i_cols[0], 5.5, clean_str(c_name), 'B', 0, 'L', fill)
            pdf.cell(i_cols[1], 5.5, clean_str(f"{run_rate:,.1f}"), 'B', 0, 'R', fill)
            pdf.cell(i_cols[2], 5.5, clean_str(f"{days_left}d"), 'B', 0, 'R', fill)
            pdf.cell(i_cols[3], 5.5, clean_str(st_disp), 'B', 0, 'L', fill)
            pdf.cell(i_cols[4], 5.5, clean_str(f"{s_stock:,}"), 'B', 0, 'R', fill)
            pdf.cell(i_cols[5], 5.5, clean_str(f"{rop:,}"), 'B', 0, 'R', fill)
            pdf.cell(i_cols[6], 5.5, clean_str(f"INR {format_inr(cap)}"), 'B', 1, 'R', fill)
        pdf.ln(3)

    # ── Prioritized Action Recommendations ─────────────────────────────────────
    recs = insights.get('smart_recommendations', [])
    if recs:
        pdf.section_heading("Actionable Implementation Roadmap", "Chronological priorities synthesized for management execution")
        for rec in recs[:3]:
            pri = rec.get('priority', 'Action')
            action = rec.get('action', '')
            timeframe = rec.get('timeframe') or ('0-30 Days' if 'immed' in pri.lower() else '30-90 Days')
            
            pdf.set_font(pdf.font_family, 'B', 8)
            pdf.set_text_color(*C_PURPLE)
            pdf.cell(0, 4.5, clean_str(f"[{pri.upper()} | {timeframe}]"), 0, 1)
            
            pdf.set_font(pdf.font_family, '', 7.8)
            pdf.set_text_color(*C_TEXT_DARK)
            pdf.set_x(14)
            pdf.multi_cell(186, 3.8, clean_str(action))
            pdf.ln(1)

    # Return raw PDF bytes
    return bytes(pdf.output())
