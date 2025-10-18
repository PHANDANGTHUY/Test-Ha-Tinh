import streamlit as st
import docx
import re
import pandas as pd
import matplotlib.pyplot as plt
import io
from google.generativeai import configure, GenerativeModel, ChatSession
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import base64
from fpdf import FPDF
from datetime import datetime, timedelta
import requests
import os

# Function to download fonts
def download_fonts():
    if not os.path.exists('DejaVuSans.ttf'):
        try:
            r = requests.get('https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf', timeout=10)
            r.raise_for_status()
            with open('DejaVuSans.ttf', 'wb') as f:
                f.write(r.content)
        except Exception as e:
            st.error(f"Lỗi tải font DejaVuSans: {e}")
            return False

    if not os.path.exists('DejaVuSans-Bold.ttf'):
        try:
            r = requests.get('https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans-Bold.ttf', timeout=10)
            r.raise_for_status()
            with open('DejaVuSans-Bold.ttf', 'wb') as f:
                f.write(r.content)
        except Exception as e:
            st.error(f"Lỗi tải font DejaVuSans-Bold: {e}")
            return False
    
    return True

# Function to extract data from docx
def extract_data_from_docx(file):
    doc = docx.Document(file)
    full_text = "\n".join([para.text for para in doc.paragraphs])
    
    data = {}
    
    # Extract using regex patterns
    data['muc_dich_vay'] = re.search(r'Mục đích vay: ?(.*)', full_text).group(1) if re.search(r'Mục đích vay: ?(.*)', full_text) else "Kinh doanh vật liệu xây dựng"
    data['thoi_gian_vong_quay'] = int(re.search(r'Số ngày 1 vòng quay = ?(\d+) ngày', full_text).group(1)) if re.search(r'Số ngày 1 vòng quay = ?(\d+) ngày', full_text) else 90
    data['so_vong_quay'] = int(re.search(r'Số vòng quay vốn lưu động kế hoạch = ?(\d+) vòng', full_text).group(1)) if re.search(r'Số vòng quay vốn lưu động kế hoạch = ?(\d+) vòng', full_text) else 4
    data['doanh_thu'] = int(re.search(r'Doanh thu của phương án: ?([\d.]+) đồng', full_text).group(1).replace('.', '')) if re.search(r'Doanh thu của phương án: ?([\d.]+) đồng', full_text) else 8050108000
    data['chi_phi'] = int(re.search(r'Chi phí kinh doanh: ?([\d.]+) đồng', full_text).group(1).replace('.', '')) if re.search(r'Chi phí kinh doanh: ?([\d.]+) đồng', full_text) else 7827181642
    data['chenh_lech'] = int(re.search(r'Chênh lệch thu chi: ?([\d.]+) đồng', full_text).group(1).replace('.', '')) if re.search(r'Chênh lệch thu chi: ?([\d.]+) đồng', full_text) else 222926358
    data['thoi_han_vay'] = int(re.search(r'Thời hạn cho vay: ?(\d+) tháng', full_text).group(1)) if re.search(r'Thời hạn cho vay: ?(\d+) tháng', full_text) else 3
    data['lai_suat'] = float(re.search(r'Lãi suất đề nghị: ?([\d.]+)%/năm', full_text).group(1)) if re.search(r'Lãi suất đề nghị: ?([\d.]+)%/năm', full_text) else 5.0
    
    # Extract loan amount
    so_tien_vay_match = re.search(r'Vốn vay Agribank.*?: ?([\d.]+) đồng', full_text)
    if so_tien_vay_match:
        data['so_tien_vay'] = int(so_tien_vay_match.group(1).replace('.', ''))
    else:
        data['so_tien_vay'] = data['chi_phi'] - data['chenh_lech']
    
    return data

# Function to format number with dots
def format_number(num):
    return "{:,.0f}".format(num).replace(",", ".")

# Function to calculate financial metrics
def calculate_metrics(data):
    ty_suat_loi_nhuan = (data['chenh_lech'] / data['doanh_thu']) * 100 if data['doanh_thu'] > 0 else 0
    roi = (data['chenh_lech'] / data['so_tien_vay']) * 100 if data['so_tien_vay'] > 0 else 0
    return {
        'Tỷ suất lợi nhuận (%)': ty_suat_loi_nhuan,
        'Vòng quay vốn (vòng/năm)': data['so_vong_quay'],
        'ROI (%)': roi
    }

# Function to generate repayment schedule
def generate_repayment_schedule(so_tien_vay, lai_suat, thoi_han_vay):
    start_date = datetime.now()
    monthly_interest_rate = lai_suat / 12 / 100
    df = pd.DataFrame(columns=['Kỳ', 'Ngày', 'Gốc phải trả', 'Lãi phải trả', 'Tổng phải trả', 'Dư nợ'])
    du_no = so_tien_vay
    for i in range(1, thoi_han_vay + 1):
        ngay = start_date + timedelta(days=30 * i)
        lai = du_no * monthly_interest_rate
        goc = 0 if i < thoi_han_vay else du_no
        tong = goc + lai
        du_no -= goc
        df.loc[i-1] = [i, ngay.strftime('%Y-%m-%d'), goc, lai, tong, du_no]
    return df

# Function to create charts
def create_charts(data, metrics):
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(['Doanh thu', 'Chi phí', 'Chênh lệch'], [data['doanh_thu'], data['chi_phi'], data['chenh_lech']])
    ax.set_ylabel('Đồng')
    ax.set_title('Biểu đồ Doanh thu vs Chi phí')
    plt.xticks(rotation=0)
    return fig

# PDF export function
class PDF(FPDF):
    def __init__(self):
        super().__init__()
        if os.path.exists('DejaVuSans.ttf') and os.path.exists('DejaVuSans-Bold.ttf'):
            try:
                self.add_font('DejaVuSans', '', 'DejaVuSans.ttf', uni=True)
                self.add_font('DejaVuSans', 'B', 'DejaVuSans-Bold.ttf', uni=True)
            except Exception as e:
                st.error(f"Lỗi thêm font: {e}")

    def header(self):
        self.set_font('DejaVuSans', 'B', 12)
        self.cell(0, 10, 'Báo cáo Thẩm định Phương án Kinh doanh', 0, 1, 'C')

def export_report(data, metrics, df_repayment, analysis):
    try:
        # Ensure fonts are downloaded
        if not download_fonts():
            return None
            
        pdf = PDF()
        pdf.add_page()
        pdf.set_font('DejaVuSans', '', 12)
        
        # Add data section
        pdf.cell(0, 10, 'THÔNG TIN PHƯƠNG ÁN', 0, 1)
        pdf.ln(5)
        for key, value in data.items():
            text = f"{key}: {format_number(value) if isinstance(value, (int, float)) else value}"
            pdf.multi_cell(0, 10, text)
        
        # Add metrics section
        pdf.ln(5)
        pdf.set_font('DejaVuSans', 'B', 12)
        pdf.cell(0, 10, 'CHỈ TIÊU TÀI CHÍNH', 0, 1)
        pdf.set_font('DejaVuSans', '', 12)
        pdf.ln(5)
        for key, value in metrics.items():
            text = f"{key}: {value:.2f}" if isinstance(value, float) else f"{key}: {value}"
            pdf.multi_cell(0, 10, text)
        
        # Add repayment schedule
        pdf.ln(5)
        pdf.set_font('DejaVuSans', 'B', 12)
        pdf.cell(0, 10, 'KẾ HOẠCH TRẢ NỢ', 0, 1)
        pdf.set_font('DejaVuSans', '', 10)
        pdf.ln(5)
        for _, row in df_repayment.head(10).iterrows():  # Limit to 10 rows for PDF
            text = f"Kỳ {int(row['Kỳ'])}: {row['Ngày']} - Gốc: {format_number(row['Gốc phải trả'])} - Lãi: {format_number(row['Lãi phải trả'])}"
            pdf.multi_cell(0, 8, text)
        
        # Add AI analysis
        if analysis:
            pdf.ln(5)
            pdf.set_font('DejaVuSans', 'B', 12)
            pdf.cell(0, 10, 'PHÂN TÍCH AI', 0, 1)
            pdf.set_font('DejaVuSans', '', 11)
            pdf.ln(5)
            pdf.multi_cell(0, 10, analysis)
        
        output = io.BytesIO()
        pdf.output(output)
        output.seek(0)
        return output
    except Exception as e:
        st.error(f"Lỗi tạo PDF: {e}")
        return None

# Streamlit app
st.set_page_config(page_title="Thẩm định phương án kinh doanh", layout="wide")

st.title("🏦 Hệ thống Thẩm định Phương án Kinh doanh")

# Sidebar
with st.sidebar:
    st.header("⚙️ Cấu hình")
    api_key = st.text_input("Nhập API Key Gemini", type="password")
    if api_key:
        configure(api_key=api_key)
    
    st.divider()
    
    # Only show export button when data is ready
    if st.session_state.get('data') and st.session_state.get('metrics') and not st.session_state.get('df_repayment', pd.DataFrame()).empty:
        if st.button("📄 Xuất báo cáo PDF", use_container_width=True):
            with st.spinner("Đang tạo báo cáo..."):
                report_data = export_report(
                    st.session_state.data, 
                    st.session_state.metrics, 
                    st.session_state.df_repayment, 
                    st.session_state.get('analysis', '')
                )
                if report_data:
                    st.download_button(
                        "⬇️ Tải báo cáo", 
                        report_data, 
                        file_name=f"bao_cao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf", 
                        mime="application/pdf",
                        use_container_width=True
                    )
                else:
                    st.error("Không thể tạo báo cáo PDF")

# Tabs
tab1, tab2, tab3, tab4 = st.tabs(["📤 Upload & Trích xuất", "📊 Chỉ tiêu tài chính & Biểu đồ", "💰 Kế hoạch trả nợ", "🤖 Phân tích AI & Chatbox"])

# Initialize session state
if 'data' not in st.session_state:
    st.session_state.data = {}
if 'metrics' not in st.session_state:
    st.session_state.metrics = {}
if 'df_repayment' not in st.session_state:
    st.session_state.df_repayment = pd.DataFrame()
if 'chat_session' not in st.session_state:
    st.session_state.chat_session = None
if 'analysis' not in st.session_state:
    st.session_state.analysis = ""

with tab1:
    st.header("Upload và Trích xuất dữ liệu")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        uploaded_file = st.file_uploader("Upload file .docx", type="docx")
        if uploaded_file:
            try:
                with st.spinner("Đang trích xuất dữ liệu..."):
                    st.session_state.data = extract_data_from_docx(uploaded_file)
                st.success("✅ Trích xuất thành công!")
            except Exception as e:
                st.error(f"❌ Lỗi trích xuất: {e}")
    
    with col2:
        if st.session_state.data:
            st.info("Dữ liệu đã được trích xuất. Vui lòng kiểm tra và chỉnh sửa nếu cần.")
    
    # Display and edit data
    if st.session_state.data or st.button("Nhập dữ liệu thủ công"):
        with st.expander("📝 Thông tin phương án", expanded=True):
            col1, col2 = st.columns(2)
            
            with col1:
                st.session_state.data['muc_dich_vay'] = st.text_input("Mục đích vay", st.session_state.data.get('muc_dich_vay', ""))
                st.session_state.data['thoi_gian_vong_quay'] = st.number_input("Thời gian vòng quay (ngày)", value=st.session_state.data.get('thoi_gian_vong_quay', 90), min_value=1)
                st.session_state.data['so_vong_quay'] = st.number_input("Số vòng quay/năm", value=st.session_state.data.get('so_vong_quay', 4), min_value=1)
                st.session_state.data['doanh_thu'] = st.number_input("Doanh thu (đồng)", value=st.session_state.data.get('doanh_thu', 0), format="%i", min_value=0)
                st.session_state.data['chi_phi'] = st.number_input("Chi phí (đồng)", value=st.session_state.data.get('chi_phi', 0), format="%i", min_value=0)
            
            with col2:
                st.session_state.data['chenh_lech'] = st.number_input("Chênh lệch (đồng)", value=st.session_state.data.get('chenh_lech', 0), format="%i")
                st.session_state.data['so_tien_vay'] = st.number_input("Số tiền vay (đồng)", value=st.session_state.data.get('so_tien_vay', 0), format="%i", min_value=0)
                st.session_state.data['thoi_han_vay'] = st.number_input("Thời hạn vay (tháng)", value=st.session_state.data.get('thoi_han_vay', 3), min_value=1, max_value=360)
                st.session_state.data['lai_suat'] = st.number_input("Lãi suất (%/năm)", value=st.session_state.data.get('lai_suat', 5.0), min_value=0.0, max_value=100.0, step=0.1)

with tab2:
    st.header("Chỉ tiêu tài chính")
    
    if st.session_state.data:
        st.session_state.metrics = calculate_metrics(st.session_state.data)
        
        # Display metrics in cards
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Tỷ suất lợi nhuận", f"{st.session_state.metrics['Tỷ suất lợi nhuận (%)']:.2f}%")
        
        with col2:
            st.metric("Vòng quay vốn", f"{st.session_state.metrics['Vòng quay vốn (vòng/năm)']} vòng/năm")
        
        with col3:
            st.metric("ROI", f"{st.session_state.metrics['ROI (%)']:.2f}%")
        
        st.divider()
        
        # Conclusion
        if st.session_state.metrics['Tỷ suất lợi nhuận (%)'] > 0:
            st.success("✅ **Kết luận:** Phương án có lợi nhuận dương, khả năng sinh lời tốt.")
        else:
            st.error("❌ **Kết luận:** Phương án lỗ, cần xem xét lại.")
        
        st.divider()
        
        # Chart
        st.subheader("📊 Biểu đồ phân tích")
        fig = create_charts(st.session_state.data, st.session_state.metrics)
        st.pyplot(fig)
    else:
        st.warning("⚠️ Vui lòng upload file hoặc nhập dữ liệu ở tab 'Upload & Trích xuất'")

with tab3:
    st.header("Kế hoạch trả nợ")
    
    if st.session_state.data:
        st.session_state.df_repayment = generate_repayment_schedule(
            st.session_state.data['so_tien_vay'],
            st.session_state.data['lai_suat'],
            st.session_state.data['thoi_han_vay']
        )
        
        # Format numbers for display
        df_display = st.session_state.df_repayment.copy()
        for col in ['Gốc phải trả', 'Lãi phải trả', 'Tổng phải trả', 'Dư nợ']:
            df_display[col] = df_display[col].apply(lambda x: format_number(x))
        
        st.dataframe(df_display, use_container_width=True)
        
        st.divider()
        
        # Download Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            st.session_state.df_repayment.to_excel(writer, index=False, sheet_name='Kế hoạch trả nợ')
        output.seek(0)
        
        st.download_button(
            "📥 Tải Excel kế hoạch trả nợ", 
            output, 
            file_name=f"ke_hoach_tra_no_{datetime.now().strftime('%Y%m%d')}.xlsx", 
            mime="application/vnd.ms-excel"
        )
    else:
        st.warning("⚠️ Vui lòng nhập dữ liệu ở tab 'Upload & Trích xuất'")

with tab4:
    st.header("Phân tích AI & Chatbox")
    
    if api_key:
        model = GenerativeModel('gemini-1.5-flash', safety_settings={
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE
        })
        
        # Analysis section
        st.subheader("🤖 Phân tích tự động")
        if st.button("Phân tích bằng Gemini", type="primary"):
            if st.session_state.data:
                with st.spinner("Đang phân tích..."):
                    prompt = f"""Phân tích phương án kinh doanh sau và đưa ra đề xuất cho vay:
                    
Thông tin phương án:
- Mục đích vay: {st.session_state.data.get('muc_dich_vay')}
- Số tiền vay: {format_number(st.session_state.data.get('so_tien_vay', 0))} đồng
- Thời hạn vay: {st.session_state.data.get('thoi_han_vay')} tháng
- Lãi suất: {st.session_state.data.get('lai_suat')}%/năm
- Doanh thu dự kiến: {format_number(st.session_state.data.get('doanh_thu', 0))} đồng
- Chi phí dự kiến: {format_number(st.session_state.data.get('chi_phi', 0))} đồng
- Chênh lệch thu chi: {format_number(st.session_state.data.get('chenh_lech', 0))} đồng
- Tỷ suất lợi nhuận: {st.session_state.metrics.get('Tỷ suất lợi nhuận (%)', 0):.2f}%
- ROI: {st.session_state.metrics.get('ROI (%)', 0):.2f}%

Hãy phân tích:
1. Tính khả thi của phương án
2. Rủi ro tiềm ẩn
3. Đề xuất cho vay hay không và lý do
4. Các điều kiện cần lưu ý

Trả lời bằng tiếng Việt, dưới 300 từ."""
                    
                    response = model.generate_content(prompt)
                    st.session_state.analysis = response.text
                    st.write(st.session_state.analysis)
            else:
                st.warning("⚠️ Vui lòng nhập dữ liệu phương án trước")
        
        if st.session_state.analysis:
            st.info(st.session_state.analysis)
        
        st.divider()
        
        # Chatbox section
        st.subheader("💬 Chatbox tư vấn")
        
        if st.session_state.chat_session is None:
            st.session_state.chat_session = model.start_chat()
        
        # Display chat history
        for message in st.session_state.chat_session.history:
            with st.chat_message("user" if message.role == 'user' else "assistant"):
                st.markdown(message.parts[0].text)
        
        # Chat input
        user_input = st.chat_input("Hỏi về phương án...")
        if user_input:
            # Add context about the business plan
            context = f"""Thông tin phương án hiện tại:
- Số tiền vay: {format_number(st.session_state.data.get('so_tien_vay', 0))} đồng
- Doanh thu: {format_number(st.session_state.data.get('doanh_thu', 0))} đồng
- Chi phí: {format_number(st.session_state.data.get('chi_phi', 0))} đồng
- Lợi nhuận: {format_number(st.session_state.data.get('chenh_lech', 0))} đồng

Câu hỏi: {user_input}"""
            
            response = st.session_state.chat_session.send_message(context)
            
            with st.chat_message("user"):
                st.markdown(user_input)
            with st.chat_message("assistant"):
                st.markdown(response.text)
        
        if st.button("🗑️ Xóa lịch sử chat"):
            st.session_state.chat_session = model.start_chat()
            st.rerun()
    else:
        st.error("⚠️ Vui lòng nhập API key Gemini ở sidebar để sử dụng tính năng này.")
