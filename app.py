import streamlit as st
import pandas as pd
import numpy as np
from docx import Document
import io
import re
from datetime import datetime
import json
import time

# Import có điều kiện
try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

# Cấu hình trang
st.set_page_config(
    page_title="Hệ Thống Thẩm Định Phương Án Kinh Doanh",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS tùy chỉnh
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        padding: 1rem 0;
        background: linear-gradient(90deg, #e3f2fd 0%, #bbdefb 100%);
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding: 0 24px;
        background-color: #f0f2f6;
        border-radius: 5px 5px 0 0;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1f77b4;
        color: white;
    }
    div[data-testid="stNumberInput"] input {
        font-weight: bold;
        color: #1f77b4;
    }
</style>
""", unsafe_allow_html=True)

# Khởi tạo session state
if 'data_extracted' not in st.session_state:
    st.session_state.data_extracted = False
if 'customer_info' not in st.session_state:
    st.session_state.customer_info = {}
if 'financial_info' not in st.session_state:
    st.session_state.financial_info = {}
if 'collateral_info' not in st.session_state:
    st.session_state.collateral_info = {}
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'data_modified' not in st.session_state:
    st.session_state.data_modified = False
if 'uploaded_content' not in st.session_state:
    st.session_state.uploaded_content = ""
if 'last_request_time' not in st.session_state:
    st.session_state.last_request_time = 0

# Hàm định dạng số
def format_number(num):
    """Định dạng số với dấu chấm phân cách hàng nghìn"""
    try:
        return "{:,.0f}".format(float(num)).replace(",", ".")
    except:
        return str(num)

def parse_number(text):
    """Chuyển đổi text thành số"""
    try:
        clean_text = str(text).replace(".", "").replace(",", ".")
        return float(clean_text)
    except:
        return 0

# Hàm trích xuất thông tin từ file docx
def extract_info_from_docx(file):
    """Trích xuất thông tin từ file docx"""
    doc = Document(file)
    full_text = '\n'.join([para.text for para in doc.paragraphs])
    st.session_state.uploaded_content = full_text
    
    customer_info = {}
    financial_info = {}
    collateral_info = {}
    
    # Trích xuất thông tin khách hàng
    name_match = re.search(r'Họ và tên:\s*([^\n\r-]+)', full_text)
    if name_match:
        customer_info['name'] = name_match.group(1).strip()
    
    cccd_match = re.search(r'(?:CMND/)?CCCD(?:/hộ chiếu)?:\s*(\d+)', full_text)
    if cccd_match:
        customer_info['cccd'] = cccd_match.group(1).strip()
    
    address_match = re.search(r'Nơi cư trú:\s*([^\n\r]+)', full_text)
    if address_match:
        customer_info['address'] = address_match.group(1).strip()
    
    phone_match = re.search(r'Số điện thoại:\s*(\d+)', full_text)
    if phone_match:
        customer_info['phone'] = phone_match.group(1).strip()
    
    email_match = re.search(r'Email:\s*([^\s\n\r]+)', full_text)
    if email_match:
        customer_info['email'] = email_match.group(1).strip()
    
    # Trích xuất thông tin tài chính
    total_need_match = re.search(r'Tổng nhu cầu vốn:\s*([\d.,]+)\s*đồng', full_text)
    if total_need_match:
        financial_info['total_need'] = parse_number(total_need_match.group(1))
    
    equity_match = re.search(r'Vốn đối ứng[^:]*:\s*([\d.,]+)\s*đồng', full_text)
    if equity_match:
        financial_info['equity'] = parse_number(equity_match.group(1))
    
    loan_match = re.search(r'Vốn vay[^:]*số tiền:\s*([\d.,]+)\s*đồng', full_text)
    if loan_match:
        financial_info['loan_amount'] = parse_number(loan_match.group(1))
    
    interest_match = re.search(r'Lãi suất:\s*([\d.,]+)%', full_text)
    if interest_match:
        financial_info['interest_rate'] = float(interest_match.group(1).replace(',', '.'))
    
    term_match = re.search(r'Thời hạn vay:\s*(\d+)\s*tháng', full_text)
    if term_match:
        financial_info['loan_term'] = int(term_match.group(1))
    
    purpose_match = re.search(r'Mục đích vay:\s*([^\n\r]+)', full_text)
    if purpose_match:
        financial_info['purpose'] = purpose_match.group(1).strip()
    
    income_patterns = [
        r'Tổng thu nhập[^:]*:\s*([\d.,]+)\s*đồng',
        r'Thu nhập[^:]*:\s*([\d.,]+)\s*đồng/tháng'
    ]
    for pattern in income_patterns:
        income_match = re.search(pattern, full_text)
        if income_match:
            financial_info['monthly_income'] = parse_number(income_match.group(1))
            break
    
    expense_match = re.search(r'Tổng chi phí hàng tháng:\s*([\d.,]+)', full_text)
    if expense_match:
        financial_info['monthly_expense'] = parse_number(expense_match.group(1))
    
    project_income_match = re.search(r'Thu nhập từ kinh doanh[^:]*:\s*([\d.,]+)\s*đồng/tháng', full_text)
    if project_income_match:
        financial_info['project_income'] = parse_number(project_income_match.group(1))
    
    # Trích xuất thông tin tài sản đảm bảo
    collateral_type_match = re.search(r'Tài sản \d+:\s*([^\n\r.]+)', full_text)
    if collateral_type_match:
        collateral_info['type'] = collateral_type_match.group(1).strip()
    
    collateral_value_patterns = [
        r'Giá trị:\s*([\d.,]+)\s*đồng',
        r'Giá trị[^:]*:\s*([\d.,]+)\s*đồng'
    ]
    for pattern in collateral_value_patterns:
        collateral_value_match = re.search(pattern, full_text)
        if collateral_value_match:
            collateral_info['value'] = parse_number(collateral_value_match.group(1))
            break
    
    collateral_address_match = re.search(r'Địa chỉ:\s*([^\n\r]+?)(?:Diện tích|Giấy|Tỷ lệ|\n|$)', full_text)
    if collateral_address_match:
        collateral_info['address'] = collateral_address_match.group(1).strip()
    
    area_match = re.search(r'Diện tích đất:\s*([\d.,]+)\s*m', full_text)
    if area_match:
        collateral_info['area'] = parse_number(area_match.group(1))
    
    return customer_info, financial_info, collateral_info

# Hàm tính toán các chỉ tiêu tài chính
def calculate_financial_metrics(financial_info):
    """Tính toán các chỉ tiêu tài chính"""
    metrics = {}
    
    loan_amount = financial_info.get('loan_amount', 0)
    interest_rate = financial_info.get('interest_rate', 0) / 100 / 12
    loan_term = financial_info.get('loan_term', 0)
    monthly_income = financial_info.get('monthly_income', 0)
    monthly_expense = financial_info.get('monthly_expense', 0)
    
    if loan_amount > 0 and loan_term > 0:
        monthly_principal = loan_amount / loan_term
        
        repayment_schedule = []
        remaining_balance = loan_amount
        
        for month in range(1, loan_term + 1):
            interest_payment = remaining_balance * interest_rate
            principal_payment = monthly_principal
            total_payment = principal_payment + interest_payment
            remaining_balance -= principal_payment
            
            repayment_schedule.append({
                'Tháng': month,
                'Dư nợ đầu kỳ': remaining_balance + principal_payment,
                'Trả gốc': principal_payment,
                'Trả lãi': interest_payment,
                'Tổng trả': total_payment,
                'Dư nợ cuối kỳ': max(0, remaining_balance)
            })
        
        metrics['repayment_schedule'] = pd.DataFrame(repayment_schedule)
        metrics['monthly_principal'] = monthly_principal
        metrics['first_month_interest'] = loan_amount * interest_rate
        metrics['first_month_payment'] = monthly_principal + metrics['first_month_interest']
        metrics['total_interest'] = sum([row['Trả lãi'] for row in repayment_schedule])
        metrics['total_payment'] = loan_amount + metrics['total_interest']
        metrics['net_income'] = monthly_income - monthly_expense
        metrics['debt_service_ratio'] = (metrics['first_month_payment'] / monthly_income * 100) if monthly_income > 0 else 0
        metrics['surplus'] = metrics['net_income'] - metrics['first_month_payment']
        metrics['dscr'] = (metrics['net_income'] / metrics['first_month_payment']) if metrics['first_month_payment'] > 0 else 0
        
    return metrics

# Hàm cấu hình Gemini API
def configure_gemini(api_key):
    """Cấu hình Gemini API"""
    if not GENAI_AVAILABLE:
        return False
    try:
        genai.configure(api_key=api_key)
        return True
    except Exception as e:
        st.error(f"Lỗi cấu hình Gemini API: {str(e)}")
        return False

# Hàm retry với exponential backoff
def retry_with_backoff(func, max_retries=3, initial_delay=2):
    """Retry function with exponential backoff"""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower():
                if attempt < max_retries - 1:
                    delay = initial_delay * (2 ** attempt)
                    # Tìm retry_delay trong error message
                    retry_match = re.search(r'retry in ([\d.]+)s', error_str)
                    if retry_match:
                        delay = float(retry_match.group(1)) + 1
                    
                    st.warning(f"⏳ Rate limit reached. Đang chờ {delay:.0f} giây trước khi thử lại... (Lần {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                else:
                    raise Exception(f"Đã thử {max_retries} lần nhưng vẫn gặp lỗi rate limit. Vui lòng:\n"
                                  f"1. Đợi vài phút rồi thử lại\n"
                                  f"2. Chọn model khác (gemini-1.5-flash hoặc gemini-1.5-pro)\n"
                                  f"3. Kiểm tra quota tại: https://ai.dev/usage")
            else:
                raise e
    return None

# Hàm phân tích bằng Gemini với retry logic
def analyze_with_gemini(api_key, data_source, data_content, model_name='gemini-1.5-flash'):
    """Phân tích dữ liệu bằng Gemini với retry logic"""
    if not GENAI_AVAILABLE:
        return "⚠️ Thư viện Google Generative AI chưa được cài đặt.\nVui lòng chạy: pip install google-generativeai"
    
    # Rate limiting - đảm bảo ít nhất 2 giây giữa các request
    current_time = time.time()
    time_since_last = current_time - st.session_state.last_request_time
    if time_since_last < 2:
        time.sleep(2 - time_since_last)
    
    try:
        configure_gemini(api_key)
        
        def make_request():
            model = genai.GenerativeModel(model_name)
            
            if data_source == "file":
                prompt = f"""
Bạn là chuyên gia phân tích tín dụng ngân hàng. Hãy phân tích chi tiết phương án vay vốn dưới đây:

{data_content}

Yêu cầu phân tích:
1. Đánh giá tổng quan về phương án
2. Phân tích điểm mạnh và điểm yếu
3. Đánh giá khả năng trả nợ
4. Phân tích rủi ro
5. Kết luận và đề xuất

Hãy trình bày ngắn gọn nhưng đầy đủ và chuyên sâu.
"""
            else:
                prompt = f"""
Bạn là chuyên gia phân tích tín dụng ngân hàng. Hãy phân tích các chỉ tiêu tài chính sau:

{data_content}

Yêu cầu phân tích:
1. Đánh giá các chỉ tiêu tài chính quan trọng
2. So sánh với tiêu chuẩn ngân hàng
3. Phân tích khả năng trả nợ và dòng tiền
4. Đánh giá mức độ rủi ro
5. Kết luận và khuyến nghị

Hãy trình bày ngắn gọn nhưng đầy đủ và chuyên sâu.
"""
            
            response = model.generate_content(prompt)
            st.session_state.last_request_time = time.time()
            return response.text
        
        return retry_with_backoff(make_request)
        
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "quota" in error_msg.lower():
            return f"""
⚠️ **LỖI RATE LIMIT / QUOTA**

API key của bạn đã vượt quá giới hạn sử dụng.

**Giải pháp:**
1. **Đợi một lúc** (thường là 1-2 phút) rồi thử lại
2. **Chọn model khác** ở dropdown bên dưới (gemini-1.5-flash hoặc gemini-1.5-pro)
3. **Kiểm tra usage**: https://ai.dev/usage?tab=rate-limit
4. **Tạo API key mới**: https://aistudio.google.com/app/apikey

**Chi tiết lỗi:** {error_msg}
"""
        else:
            return f"❌ Lỗi phân tích: {error_msg}"

# Hàm xuất Excel
def export_to_excel(repayment_schedule):
    """Xuất bảng kế hoạch trả nợ ra Excel"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df = repayment_schedule.copy()
        for col in ['Dư nợ đầu kỳ', 'Trả gốc', 'Trả lãi', 'Tổng trả', 'Dư nợ cuối kỳ']:
            df[col] = df[col].apply(lambda x: format_number(x))
        df.to_excel(writer, sheet_name='Kế hoạch trả nợ', index=False)
    return output.getvalue()

# Hàm xuất báo cáo thẩm định
def export_appraisal_report(customer_info, financial_info, collateral_info, metrics, analysis_file, analysis_metrics):
    """Xuất báo cáo thẩm định ra Word"""
    doc = Document()
    
    title = doc.add_heading('BÁO CÁO THẨM ĐỊNH PHƯƠNG ÁN VAY VỐN', 0)
    title.alignment = 1
    
    doc.add_heading('I. THÔNG TIN KHÁCH HÀNG', 1)
    doc.add_paragraph(f"Họ và tên: {customer_info.get('name', 'N/A')}")
    doc.add_paragraph(f"CCCD: {customer_info.get('cccd', 'N/A')}")
    doc.add_paragraph(f"Địa chỉ: {customer_info.get('address', 'N/A')}")
    doc.add_paragraph(f"Số điện thoại: {customer_info.get('phone', 'N/A')}")
    doc.add_paragraph(f"Email: {customer_info.get('email', 'N/A')}")
    
    doc.add_heading('II. THÔNG TIN TÀI CHÍNH', 1)
    doc.add_paragraph(f"Mục đích vay: {financial_info.get('purpose', 'N/A')}")
    doc.add_paragraph(f"Tổng nhu cầu vốn: {format_number(financial_info.get('total_need', 0))} đồng")
    doc.add_paragraph(f"Vốn đối ứng: {format_number(financial_info.get('equity', 0))} đồng")
    doc.add_paragraph(f"Số tiền vay: {format_number(financial_info.get('loan_amount', 0))} đồng")
    doc.add_paragraph(f"Lãi suất: {financial_info.get('interest_rate', 0)}%/năm")
    doc.add_paragraph(f"Thời hạn vay: {financial_info.get('loan_term', 0)} tháng")
    doc.add_paragraph(f"Thu nhập hàng tháng: {format_number(financial_info.get('monthly_income', 0))} đồng")
    doc.add_paragraph(f"Chi phí hàng tháng: {format_number(financial_info.get('monthly_expense', 0))} đồng")
    
    doc.add_heading('III. TÀI SẢN ĐẢM BẢO', 1)
    doc.add_paragraph(f"Loại tài sản: {collateral_info.get('type', 'N/A')}")
    doc.add_paragraph(f"Giá trị: {format_number(collateral_info.get('value', 0))} đồng")
    doc.add_paragraph(f"Địa chỉ: {collateral_info.get('address', 'N/A')}")
    if collateral_info.get('area'):
        doc.add_paragraph(f"Diện tích: {format_number(collateral_info.get('area', 0))} m²")
    
    doc.add_heading('IV. CÁC CHỈ TIÊU TÀI CHÍNH', 1)
    doc.add_paragraph(f"Trả nợ gốc hàng tháng: {format_number(metrics.get('monthly_principal', 0))} đồng")
    doc.add_paragraph(f"Trả lãi tháng đầu: {format_number(metrics.get('first_month_interest', 0))} đồng")
    doc.add_paragraph(f"Tổng trả tháng đầu: {format_number(metrics.get('first_month_payment', 0))} đồng")
    doc.add_paragraph(f"Tổng lãi phải trả: {format_number(metrics.get('total_interest', 0))} đồng")
    doc.add_paragraph(f"Thu nhập ròng: {format_number(metrics.get('net_income', 0))} đồng")
    doc.add_paragraph(f"Tỷ lệ trả nợ/thu nhập: {metrics.get('debt_service_ratio', 0):.2f}%")
    doc.add_paragraph(f"Số dư sau trả nợ: {format_number(metrics.get('surplus', 0))} đồng")
    doc.add_paragraph(f"DSCR: {metrics.get('dscr', 0):.2f}")
    
    if analysis_file:
        doc.add_heading('V. PHÂN TÍCH TỪ FILE UPLOAD', 1)
        doc.add_paragraph(analysis_file)
    
    if analysis_metrics:
        doc.add_heading('VI. PHÂN TÍCH TỪ CÁC CHỈ SỐ', 1)
        doc.add_paragraph(analysis_metrics)
    
    output = io.BytesIO()
    doc.save(output)
    output.seek(0)
    return output.getvalue()

# SIDEBAR
with st.sidebar:
    st.markdown("### 🔑 Cấu Hình API")
    api_key = st.text_input("Nhập Gemini API Key:", type="password", help="Nhập API key từ Google AI Studio")
    
    # Chọn model
    st.markdown("### 🤖 Chọn Model AI")
    model_options = {
        'Gemini 1.5 Flash (Nhanh - Khuyến nghị)': 'gemini-1.5-flash',
        'Gemini 1.5 Pro (Chất lượng cao)': 'gemini-1.5-pro',
        'Gemini 2.0 Flash (Mới nhất)': 'gemini-2.0-flash'
    }
    selected_model_display = st.selectbox(
        "Model:",
        options=list(model_options.keys()),
        help="Chọn model phù hợp với API key của bạn"
    )
    selected_model = model_options[selected_model_display]
    
    if api_key and GENAI_AVAILABLE:
        if configure_gemini(api_key):
            st.success("✅ API Key hợp lệ!")
        else:
            st.error("❌ API Key không hợp lệ!")
    elif api_key and not GENAI_AVAILABLE:
        st.warning("⚠️ Thư viện google-generativeai chưa được cài đặt!")
    
    st.markdown("---")
    st.markdown("### 📤 Upload File")
    uploaded_file = st.file_uploader("Chọn file PASDV (.docx)", type=['docx'])
    
    if uploaded_file is not None:
        if st.button("🔍 Trích Xuất Dữ Liệu", use_container_width=True):
            with st.spinner("Đang xử lý..."):
                customer_info, financial_info, collateral_info = extract_info_from_docx(uploaded_file)
                st.session_state.customer_info = customer_info
                st.session_state.financial_info = financial_info
                st.session_state.collateral_info = collateral_info
                st.session_state.data_extracted = True
                st.session_state.data_modified = False
                st.success("✅ Trích xuất thành công!")
                st.rerun()
    
    st.markdown("---")
    with st.expander("ℹ️ Hướng dẫn xử lý lỗi Rate Limit"):
        st.markdown("""
        **Nếu gặp lỗi 429:**
        1. Đợi 1-2 phút
        2. Chọn model khác
        3. Kiểm tra quota: [AI Studio](https://ai.dev/usage)
        4. Tạo API key mới nếu cần
        """)

# HEADER
st.markdown('<div class="main-header">🏦 HỆ THỐNG THẨM ĐỊNH PHƯƠNG ÁN KINH DOANH</div>', unsafe_allow_html=True)

# MAIN CONTENT
if st.session_state.data_extracted:
    tabs = st.tabs([
        "📋 Thông Tin KH",
        "💰 Thông Tin Tài Chính", 
        "🏠 Tài Sản Đảm Bảo",
        "📊 Chỉ Tiêu & Kế Hoạch",
        "📈 Biểu Đồ",
        "🤖 Phân Tích AI",
        "💬 Chatbox AI",
        "📥 Xuất Dữ Liệu"
    ])
    
    # TAB 1: Thông tin khách hàng
    with tabs[0]:
        st.subheader("📋 Thông Tin Định Danh Khách Hàng")
        
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input("Họ và tên:", value=st.session_state.customer_info.get('name', ''))
            cccd = st.text_input("CCCD:", value=st.session_state.customer_info.get('cccd', ''))
            phone = st.text_input("Số điện thoại:", value=st.session_state.customer_info.get('phone', ''))
        
        with col2:
            email = st.text_input("Email:", value=st.session_state.customer_info.get('email', ''))
            address = st.text_area("Địa chỉ:", value=st.session_state.customer_info.get('address', ''), height=100)
        
        if st.button("💾 Lưu Thay Đổi", key="save_customer"):
            st.session_state.customer_info.update({
                'name': name,
                'cccd': cccd,
                'phone': phone,
                'email': email,
                'address': address
            })
            st.session_state.data_modified = True
            st.success("✅ Đã lưu thay đổi!")
    
    # TAB 2: Thông tin tài chính
    with tabs[1]:
        st.subheader("💰 Thông Tin Tài Chính")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Thông Tin Vay Vốn")
            purpose = st.text_area("Mục đích vay:", value=st.session_state.financial_info.get('purpose', ''), height=80)
            
            total_need_input = st.text_input("Tổng nhu cầu vốn (đồng):", 
                                        value=format_number(st.session_state.financial_info.get('total_need', 0)),
                                        help="Nhập số, có thể dùng dấu chấm phân cách")
            total_need = parse_number(total_need_input)
            
            equity_input = st.text_input("Vốn đối ứng (đồng):", 
                                    value=format_number(st.session_state.financial_info.get('equity', 0)),
                                    help="Nhập số, có thể dùng dấu chấm phân cách")
            equity = parse_number(equity_input)
            
            loan_amount_input = st.text_input("Số tiền vay (đồng):", 
                                         value=format_number(st.session_state.financial_info.get('loan_amount', 0)),
                                         help="Nhập số, có thể dùng dấu chấm phân cách")
            loan_amount = parse_number(loan_amount_input)
            
            interest_rate_input = st.text_input("Lãi suất (%/năm):", 
                                           value=str(st.session_state.financial_info.get('interest_rate', 8.5)).replace('.', ','),
                                           help="Ví dụ: 8,5 hoặc 8.5")
            interest_rate = float(interest_rate_input.replace(',', '.')) if interest_rate_input else 0
            
            loan_term_input = st.text_input("Thời hạn vay (tháng):", 
                                       value=str(int(st.session_state.financial_info.get('loan_term', 60))),
                                       help="Nhập số tháng")
            loan_term = int(loan_term_input) if loan_term_input else 0
        
        with col2:
            st.markdown("#### Thu Chi Hàng Tháng")
            
            monthly_income_input = st.text_input("Thu nhập hàng tháng (đồng):", 
                                            value=format_number(st.session_state.financial_info.get('monthly_income', 0)),
                                            help="Nhập số, có thể dùng dấu chấm phân cách")
            monthly_income = parse_number(monthly_income_input)
            
            monthly_expense_input = st.text_input("Chi phí hàng tháng (đồng):", 
                                             value=format_number(st.session_state.financial_info.get('monthly_expense', 0)),
                                             help="Nhập số, có thể dùng dấu chấm phân cách")
            monthly_expense = parse_number(monthly_expense_input)
            
            project_income_input = st.text_input("Thu nhập từ dự án (đồng/tháng):", 
                                            value=format_number(st.session_state.financial_info.get('project_income', 0)),
                                            help="Nhập số, có thể dùng dấu chấm phân cách")
            project_income = parse_number(project_income_input)
            
            if total_need > 0:
                equity_ratio = (equity / total_need) * 100
                st.metric("Tỷ lệ vốn đối ứng", f"{equity_ratio:.2f}%")
        
        if st.button("💾 Lưu Thay Đổi", key="save_financial"):
            st.session_state.financial_info.update({
                'purpose': purpose,
                'total_need': total_need,
                'equity': equity,
                'loan_amount': loan_amount,
                'interest_rate': interest_rate,
                'loan_term': loan_term,
                'monthly_income': monthly_income,
                'monthly_expense': monthly_expense,
                'project_income': project_income
            })
            st.session_state.data_modified = True
            st.success("✅ Đã lưu thay đổi!")
    
    # TAB 3: Tài sản đảm bảo
    with tabs[2]:
        st.subheader("🏠 Tài Sản Đảm Bảo")
        
        col1, col2 = st.columns(2)
        
        with col1:
            collateral_type = st.text_input("Loại tài sản:", 
                                           value=st.session_state.collateral_info.get('type', ''))
            
            collateral_value_input = st.text_input("Giá trị tài sản (đồng):", 
                                              value=format_number(st.session_state.collateral_info.get('value', 0)),
                                              help="Nhập số, có thể dùng dấu chấm phân cách")
            collateral_value = parse_number(collateral_value_input)
            
            collateral_area_input = st.text_input("Diện tích (m²):", 
                                             value=str(st.session_state.collateral_info.get('area', 0)).replace('.', ','),
                                             help="Ví dụ: 120,50 hoặc 120.5")
            collateral_area = float(collateral_area_input.replace(',', '.')) if collateral_area_input else 0
        
        with col2:
            collateral_address = st.text_area("Địa chỉ tài sản:", 
                                             value=st.session_state.collateral_info.get('address', ''),
                                             height=100)
            
            if collateral_value > 0 and st.session_state.financial_info.get('loan_amount', 0) > 0:
                ltv = (st.session_state.financial_info['loan_amount'] / collateral_value) * 100
                st.metric("Tỷ lệ LTV", f"{ltv:.2f}%")
                
                if ltv > 80:
                    st.warning("⚠️ LTV cao hơn 80%")
                elif ltv > 70:
                    st.info("ℹ️ LTV trong khoảng 70-80%")
                else:
                    st.success("✅ LTV dưới 70%")
        
        if st.button("💾 Lưu Thay Đổi", key="save_collateral"):
            st.session_state.collateral_info.update({
                'type': collateral_type,
                'value': collateral_value,
                'area': collateral_area,
                'address': collateral_address
            })
            st.session_state.data_modified = True
            st.success("✅ Đã lưu thay đổi!")
    
    # TAB 4: Chỉ tiêu và kế hoạch
    with tabs[3]:
        st.subheader("📊 Các Chỉ Tiêu Tài Chính & Kế Hoạch Trả Nợ")
        
        metrics = calculate_financial_metrics(st.session_state.financial_info)
        
        if metrics:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Trả nợ gốc/tháng", 
                         f"{format_number(metrics.get('monthly_principal', 0))} đ")
            with col2:
                st.metric("Trả lãi tháng đầu", 
                         f"{format_number(metrics.get('first_month_interest', 0))} đ")
            with col3:
                st.metric("Tổng trả tháng đầu", 
                         f"{format_number(metrics.get('first_month_payment', 0))} đ")
            with col4:
                st.metric("Tổng lãi phải trả", 
                         f"{format_number(metrics.get('total_interest', 0))} đ")
            
            st.markdown("---")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Thu nhập ròng/tháng", 
                         f"{format_number(metrics.get('net_income', 0))} đ")
            with col2:
                debt_ratio = metrics.get('debt_service_ratio', 0)
                st.metric("Tỷ lệ trả nợ/Thu nhập", 
                         f"{debt_ratio:.2f}%",
                         delta="Tốt" if debt_ratio < 40 else "Cao")
            with col3:
                st.metric("Số dư sau trả nợ", 
                         f"{format_number(metrics.get('surplus', 0))} đ")
            with col4:
                dscr = metrics.get('dscr', 0)
                st.metric("DSCR", 
                         f"{dscr:.2f}",
                         delta="Tốt" if dscr >= 1.25 else "Thấp")
            
            st.markdown("---")
            st.markdown("### 📅 Kế Hoạch Trả Nợ Chi Tiết")
            
            if 'repayment_schedule' in metrics:
                df = metrics['repayment_schedule'].copy()
                
                for col in ['Dư nợ đầu kỳ', 'Trả gốc', 'Trả lãi', 'Tổng trả', 'Dư nợ cuối kỳ']:
                    df[col] = df[col].apply(lambda x: format_number(x))
                
                st.dataframe(df, use_container_width=True, height=400)
                
                st.session_state.repayment_schedule = metrics['repayment_schedule']
                st.session_state.metrics = metrics
    
    # TAB 5: Biểu đồ
    with tabs[4]:
        st.subheader("📈 Biểu Đồ Phân Tích")
        
        if not PLOTLY_AVAILABLE:
            st.warning("⚠️ Thư viện Plotly chưa được cài đặt. Biểu đồ không khả dụng.")
            st.info("Để sử dụng biểu đồ, vui lòng cài đặt: `pip install plotly`")
        elif 'metrics' in st.session_state and st.session_state.metrics:
            metrics = st.session_state.metrics
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### Cơ Cấu Thanh Toán Tháng Đầu")
                payment_data = pd.DataFrame({
                    'Loại': ['Gốc', 'Lãi'],
                    'Số tiền': [
                        metrics.get('monthly_principal', 0),
                        metrics.get('first_month_interest', 0)
                    ]
                })
                fig1 = px.pie(payment_data, values='Số tiền', names='Loại',
                             color_discrete_sequence=['#1f77b4', '#ff7f0e'])
                st.plotly_chart(fig1, use_container_width=True)
                
                st.markdown("#### Thu Chi Hàng Tháng")
                income_expense_data = pd.DataFrame({
                    'Loại': ['Thu nhập', 'Chi phí', 'Trả nợ', 'Còn lại'],
                    'Số tiền': [
                        st.session_state.financial_info.get('monthly_income', 0),
                        st.session_state.financial_info.get('monthly_expense', 0),
                        metrics.get('first_month_payment', 0),
                        metrics.get('surplus', 0)
                    ]
                })
                fig2 = px.bar(income_expense_data, x='Loại', y='Số tiền',
                             color='Loại',
                             color_discrete_sequence=['#2ca02c', '#d62728', '#ff7f0e', '#1f77b4'])
                fig2.update_layout(showlegend=False)
                st.plotly_chart(fig2, use_container_width=True)
            
            with col2:
                if 'repayment_schedule' in metrics:
                    st.markdown("#### Diễn Biến Dư Nợ")
                    schedule_df = metrics['repayment_schedule']
                    fig3 = go.Figure()
                    fig3.add_trace(go.Scatter(
                        x=schedule_df['Tháng'],
                        y=schedule_df['Dư nợ cuối kỳ'],
                        mode='lines+markers',
                        name='Dư nợ',
                        line=dict(color='#1f77b4', width=2),
                        marker=dict(size=6)
                    ))
                    fig3.update_layout(
                        xaxis_title="Tháng",
                        yaxis_title="Dư nợ (đồng)",
                        hovermode='x unified'
                    )
                    st.plotly_chart(fig3, use_container_width=True)
                    
                    st.markdown("#### Gốc & Lãi Theo Tháng")
                    fig4 = go.Figure()
                    fig4.add_trace(go.Bar(
                        x=schedule_df['Tháng'],
                        y=schedule_df['Trả gốc'],
                        name='Trả gốc',
                        marker_color='#1f77b4'
                    ))
                    fig4.add_trace(go.Bar(
                        x=schedule_df['Tháng'],
                        y=schedule_df['Trả lãi'],
                        name='Trả lãi',
                        marker_color='#ff7f0e'
                    ))
                    fig4.update_layout(
                        barmode='stack',
                        xaxis_title="Tháng",
                        yaxis_title="Số tiền (đồng)",
                        hovermode='x unified'
                    )
                    st.plotly_chart(fig4, use_container_width=True)
        else:
            st.info("Vui lòng nhập đầy đủ thông tin tài chính để xem biểu đồ")
    
    # TAB 6: Phân tích AI
    with tabs[5]:
        st.subheader("🤖 Phân Tích Bằng AI Gemini")
        
        if not api_key:
            st.warning("⚠️ Vui lòng nhập API Key ở sidebar để sử dụng tính năng này!")
        elif not GENAI_AVAILABLE:
            st.error("⚠️ Thư viện google-generativeai chưa được cài đặt!")
        else:
            st.info(f"🤖 **Model đang sử dụng:** {selected_model_display}")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### 📄 Phân Tích Từ File Upload")
                if st.button("🔍 Phân Tích File", use_container_width=True):
                    if st.session_state.uploaded_content:
                        with st.spinner("Đang phân tích..."):
                            analysis = analyze_with_gemini(api_key, "file", st.session_state.uploaded_content, selected_model)
                            st.session_state.analysis_file = analysis
                
                if 'analysis_file' in st.session_state:
                    st.markdown("#### Kết Quả Phân Tích:")
                    st.info(f"**Nguồn dữ liệu:** File Upload (.docx)")
                    st.write(st.session_state.analysis_file)
            
            with col2:
                st.markdown("### 📊 Phân Tích Từ Các Chỉ Số")
                if st.button("🔍 Phân Tích Chỉ Số", use_container_width=True):
                    if 'metrics' in st.session_state and st.session_state.metrics:
                        data_content = f"""
THÔNG TIN KHÁCH HÀNG:
- Họ và tên: {st.session_state.customer_info.get('name', 'N/A')}
- Thu nhập hàng tháng: {format_number(st.session_state.financial_info.get('monthly_income', 0))} đồng
- Chi phí hàng tháng: {format_number(st.session_state.financial_info.get('monthly_expense', 0))} đồng

THÔNG TIN VAY VỐN:
- Số tiền vay: {format_number(st.session_state.financial_info.get('loan_amount', 0))} đồng
- Lãi suất: {st.session_state.financial_info.get('interest_rate', 0)}%/năm
- Thời hạn: {st.session_state.financial_info.get('loan_term', 0)} tháng

CÁC CHỈ TIÊU TÀI CHÍNH:
- Trả nợ hàng tháng: {format_number(st.session_state.metrics.get('first_month_payment', 0))} đồng
- Thu nhập ròng: {format_number(st.session_state.metrics.get('net_income', 0))} đồng
- Tỷ lệ trả nợ/thu nhập: {st.session_state.metrics.get('debt_service_ratio', 0):.2f}%
- DSCR: {st.session_state.metrics.get('dscr', 0):.2f}
- Số dư sau trả nợ: {format_number(st.session_state.metrics.get('surplus', 0))} đồng
- Tổng lãi phải trả: {format_number(st.session_state.metrics.get('total_interest', 0))} đồng

TÀI SẢN ĐẢM BẢO:
- Loại: {st.session_state.collateral_info.get('type', 'N/A')}
- Giá trị: {format_number(st.session_state.collateral_info.get('value', 0))} đồng
- LTV: {(st.session_state.financial_info.get('loan_amount', 0) / st.session_state.collateral_info.get('value', 1) * 100):.2f}%
"""
                        with st.spinner("Đang phân tích..."):
                            analysis = analyze_with_gemini(api_key, "metrics", data_content, selected_model)
                            st.session_state.analysis_metrics = analysis
                
                if 'analysis_metrics' in st.session_state:
                    st.markdown("#### Kết Quả Phân Tích:")
                    st.info(f"**Nguồn dữ liệu:** Các chỉ số tài chính đã nhập")
                    st.write(st.session_state.analysis_metrics)
    
    # TAB 7: Chatbox AI
    with tabs[6]:
        st.subheader("💬 Chatbox AI Gemini")
        
        if not api_key:
            st.warning("⚠️ Vui lòng nhập API Key ở sidebar để sử dụng tính năng này!")
        elif not GENAI_AVAILABLE:
            st.error("⚠️ Thư viện google-generativeai chưa được cài đặt!")
        else:
            st.info(f"🤖 **Model đang sử dụng:** {selected_model_display}")
            
            chat_container = st.container()
            with chat_container:
                for i, chat in enumerate(st.session_state.chat_history):
                    if chat['role'] == 'user':
                        st.markdown(f"**👤 Bạn:** {chat['content']}")
                    else:
                        st.markdown(f"**🤖 AI:** {chat['content']}")
                    st.markdown("---")
            
            col1, col2 = st.columns([5, 1])
            with col1:
                user_input = st.text_input("Nhập câu hỏi của bạn:", key="chat_input")
            with col2:
                if st.button("Gửi", use_container_width=True):
                    if user_input:
                        st.session_state.chat_history.append({
                            'role': 'user',
                            'content': user_input
                        })
                        
                        context = f"""
Thông tin khách hàng và dự án:
- Tên: {st.session_state.customer_info.get('name', 'N/A')}
- Số tiền vay: {format_number(st.session_state.financial_info.get('loan_amount', 0))} đồng
- Lãi suất: {st.session_state.financial_info.get('interest_rate', 0)}%
- Thu nhập: {format_number(st.session_state.financial_info.get('monthly_income', 0))} đồng/tháng
"""
                        
                        with st.spinner("AI đang suy nghĩ..."):
                            try:
                                # Rate limiting
                                current_time = time.time()
                                time_since_last = current_time - st.session_state.last_request_time
                                if time_since_last < 2:
                                    time.sleep(2 - time_since_last)
                                
                                configure_gemini(api_key)
                                
                                def chat_request():
                                    model = genai.GenerativeModel(selected_model)
                                    prompt = f"{context}\n\nCâu hỏi: {user_input}"
                                    response = model.generate_content(prompt)
                                    st.session_state.last_request_time = time.time()
                                    return response.text
                                
                                ai_response = retry_with_backoff(chat_request)
                                
                                st.session_state.chat_history.append({
                                    'role': 'assistant',
                                    'content': ai_response
                                })
                            except Exception as e:
                                ai_response = f"❌ Lỗi: {str(e)}"
                                st.session_state.chat_history.append({
                                    'role': 'assistant',
                                    'content': ai_response
                                })
                        
                        st.rerun()
            
            if st.button("🗑️ Xóa Lịch Sử Chat", use_container_width=True):
                st.session_state.chat_history = []
                st.rerun()
    
    # TAB 8: Xuất dữ liệu
    with tabs[7]:
        st.subheader("📥 Xuất Dữ Liệu")
        
        export_option = st.selectbox(
            "Chọn loại dữ liệu xuất:",
            ["Bảng kế hoạch trả nợ (Excel)", "Báo cáo thẩm định (Word)"]
        )
        
        if export_option == "Bảng kế hoạch trả nợ (Excel)":
            st.markdown("### 📊 Xuất Bảng Kế Hoạch Trả Nợ")
            
            if 'repayment_schedule' in st.session_state:
                st.dataframe(st.session_state.repayment_schedule, use_container_width=True)
                
                excel_data = export_to_excel(st.session_state.repayment_schedule)
                st.download_button(
                    label="📥 Tải Xuống Excel",
                    data=excel_data,
                    file_name=f"ke_hoach_tra_no_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            else:
                st.warning("⚠️ Chưa có dữ liệu kế hoạch trả nợ!")
        
        else:
            st.markdown("### 📄 Xuất Báo Cáo Thẩm Định")
            
            if 'metrics' in st.session_state:
                analysis_file = st.session_state.get('analysis_file', '')
                analysis_metrics = st.session_state.get('analysis_metrics', '')
                
                word_data = export_appraisal_report(
                    st.session_state.customer_info,
                    st.session_state.financial_info,
                    st.session_state.collateral_info,
                    st.session_state.metrics,
                    analysis_file,
                    analysis_metrics
                )
                
                st.download_button(
                    label="📥 Tải Xuống Word",
                    data=word_data,
                    file_name=f"bao_cao_tham_dinh_{datetime.now().strftime('%Y%m%d')}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True
                )
            else:
                st.warning("⚠️ Chưa có dữ liệu để xuất báo cáo!")

else:
    st.markdown("""
    <div style='text-align: center; padding: 3rem;'>
        <h2>👋 Chào Mừng Đến Với Hệ Thống Thẩm Định</h2>
        <p style='font-size: 1.2rem; color: #666;'>
            Vui lòng upload file phương án sử dụng vốn (.docx) ở sidebar để bắt đầu!
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        ### 📤 Bước 1: Upload File
        - Click vào sidebar bên trái
        - Chọn file PASDV.docx
        - Click "Trích xuất dữ liệu"
        """)
    
    with col2:
        st.markdown("""
        ### ✏️ Bước 2: Chỉnh Sửa
        - Xem và chỉnh sửa thông tin
        - Sử dụng nút +/- để điều chỉnh
        - Lưu thay đổi khi cần
        """)
    
    with col3:
        st.markdown("""
        ### 📊 Bước 3: Phân Tích
        - Xem các chỉ tiêu tài chính
        - Phân tích bằng AI
        - Xuất báo cáo
        """)
    
    st.markdown("---")
    
    with st.expander("ℹ️ Hướng dẫn lấy Gemini API Key"):
        st.markdown("""
        1. Truy cập: https://aistudio.google.com/app/apikey
        2. Đăng nhập bằng tài khoản Google
        3. Click "Create API Key"
        4. Copy API Key và paste vào ô bên sidebar
        """)

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 1rem;'>
    <p>🏦 Hệ Thống Thẩm Định Phương Án Kinh Doanh v1.1</p>
    <p>Powered by Streamlit & Google Gemini AI | With Rate Limit Protection</p>
</div>
""", unsafe_allow_html=True)
