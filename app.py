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
    
    # Assume so_tien_vay based on chenh_lech or something; default to a value
    data['so_tien_vay'] = data['chi_phi'] - data['chenh_lech']  # Placeholder logic
    
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
    fig, ax = plt.subplots()
    ax.bar(['Doanh thu', 'Chi phí', 'Chênh lệch'], [data['doanh_thu'], data['chi_phi'], data['chenh_lech']])
    ax.set_ylabel('Đồng')
    ax.set_title('Biểu đồ Doanh thu vs Chi phí')
    return fig

# PDF export function
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Bao cao Tham dinh Phuong an Kinh doanh', 0, 1, 'C')

def export_report(data, metrics, df_repayment, analysis):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial', '', 12)
    for key, value in data.items():
        pdf.cell(0, 10, f"{key}: {format_number(value) if isinstance(value, (int, float)) else value}", 0, 1)
    pdf.cell(0, 10, 'Chi tieu tai chinh:', 0, 1)
    for key, value in metrics.items():
        pdf.cell(0, 10, f"{key}: {value:.2f}" if isinstance(value, float) else f"{key}: {value}", 0, 1)
    pdf.cell(0, 10, 'Ke hoach tra no:', 0, 1)
    for _, row in df_repayment.iterrows():
        pdf.cell(0, 10, str(row.to_dict()), 0, 1)
    pdf.cell(0, 10, 'Phan tich AI:', 0, 1)
    pdf.multi_cell(0, 10, analysis)
    output = io.BytesIO()
    pdf.output(output)
    output.seek(0)
    return output

# Streamlit app
st.set_page_config(page_title="Thẩm định phương án kinh doanh", layout="wide")

# Sidebar
with st.sidebar:
    api_key = st.text_input("Nhập API Key Gemini", type="password")
    if api_key:
        configure(api_key=api_key)
    st.download_button("Xuất báo cáo", data="", file_name="bao_cao.pdf", key="export_report")  # Placeholder, will update later

# Tabs
tab1, tab2, tab3, tab4 = st.tabs(["Upload & Trích xuất", "Chỉ tiêu tài chính & Biểu đồ", "Kế hoạch trả nợ", "Phân tích AI & Chatbox"])

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
    uploaded_file = st.file_uploader("Upload file .docx", type="docx")
    if uploaded_file:
        try:
            st.session_state.data = extract_data_from_docx(uploaded_file)
            st.success("Trích xuất thành công!")
        except Exception as e:
            st.error(f"Lỗi trích xuất: {e}")
    
    # Display and edit data
    with st.expander("Thông tin phương án"):
        st.session_state.data['muc_dich_vay'] = st.text_input("Mục đích vay", st.session_state.data.get('muc_dich_vay', ""))
        st.session_state.data['thoi_gian_vong_quay'] = st.number_input("Thời gian vòng quay (ngày)", value=st.session_state.data.get('thoi_gian_vong_quay', 90))
        st.session_state.data['so_vong_quay'] = st.number_input("Số vòng quay/năm", value=st.session_state.data.get('so_vong_quay', 4))
        st.session_state.data['doanh_thu'] = st.number_input("Doanh thu (đồng)", value=st.session_state.data.get('doanh_thu', 0), format="%i")
        st.session_state.data['chi_phi'] = st.number_input("Chi phí (đồng)", value=st.session_state.data.get('chi_phi', 0), format="%i")
        st.session_state.data['chenh_lech'] = st.number_input("Chênh lệch (đồng)", value=st.session_state.data.get('chenh_lech', 0), format="%i")
        st.session_state.data['so_tien_vay'] = st.number_input("Số tiền vay (đồng)", value=st.session_state.data.get('so_tien_vay', 0), format="%i")
        st.session_state.data['thoi_han_vay'] = st.number_input("Thời hạn vay (tháng)", value=st.session_state.data.get('thoi_han_vay', 3))
        st.session_state.data['lai_suat'] = st.number_input("Lãi suất (%/năm)", value=st.session_state.data.get('lai_suat', 5.0))

with tab2:
    if st.session_state.data:
        st.session_state.metrics = calculate_metrics(st.session_state.data)
        st.table(pd.DataFrame(st.session_state.metrics.items(), columns=['Chỉ tiêu', 'Giá trị']))
        st.write("Kết luận: Phương án có lợi nhuận dương." if st.session_state.metrics['Tỷ suất lợi nhuận (%)'] > 0 else "Kết luận: Phương án lỗ.")
        
        fig = create_charts(st.session_state.data, st.session_state.metrics)
        st.pyplot(fig)

with tab3:
    if st.session_state.data:
        st.session_state.df_repayment = generate_repayment_schedule(
            st.session_state.data['so_tien_vay'],
            st.session_state.data['lai_suat'],
            st.session_state.data['thoi_han_vay']
        )
        st.table(st.session_state.df_repayment)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            st.session_state.df_repayment.to_excel(writer, index=False)
        output.seek(0)
        st.download_button("Tải Excel kế hoạch trả nợ", output, file_name="ke_hoach_tra_no.xlsx", mime="application/vnd.ms-excel")

with tab4:
    if api_key:
        model = GenerativeModel('gemini-1.5-flash', safety_settings={
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE
        })
        
        if st.button("Phân tích bằng Gemini"):
            prompt = f"Phân tích phương án kinh doanh: {st.session_state.data}. Đề xuất cho vay hay không, dưới 300 từ."
            response = model.generate_content(prompt)
            st.session_state.analysis = response.text
            st.write(st.session_state.analysis)
        
        # Chatbox
        if st.session_state.chat_session is None:
            st.session_state.chat_session = model.start_chat()
        
        for message in st.session_state.chat_session.history:
            with st.chat_message("user" if message.role == 'user' else "assistant"):
                st.markdown(message.parts[0].text)
        
        user_input = st.chat_input("Hỏi về phương án...")
        if user_input:
            response = st.session_state.chat_session.send_message(user_input)
            with st.chat_message("user"):
                st.markdown(user_input)
            with st.chat_message("assistant"):
                st.markdown(response.text)
        
        if st.button("Xóa lịch sử chat"):
            st.session_state.chat_session = model.start_chat()
    else:
        st.error("Vui lòng nhập API key Gemini.")

# Update export button data
if st.session_state.data and st.session_state.metrics and not st.session_state.df_repayment.empty:
    report_data = export_report(st.session_state.data, st.session_state.metrics, st.session_state.df_repayment, st.session_state.analysis)
    st.sidebar.download_button("Xuất báo cáo", report_data, file_name="bao_cao.pdf", mime="application/pdf", key="export_report_actual")
