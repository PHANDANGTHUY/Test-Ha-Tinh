import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from docx import Document
import re
import io
import google.generativeai as genai
from datetime import datetime
import openpyxl
# ==============================================================================
# PAGE CONFIGURATION AND GLOBAL VARIABLES
# ==============================================================================
st.set_page_config(
    page_title="Thẩm định Phương án Kinh doanh",
    page_icon="💼",
    layout="wide"
)
# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================
def format_currency(value):
    """Formats a number into a currency string with dot separators for thousands."""
    if isinstance(value, (int, float)):
        return f"{value:,.0f}".replace(",", ".")
    return value
def safe_float(value):
    """Safely converts a value to float, returning 0.0 on error."""
    try:
        if isinstance(value, str):
            # Remove all non-digit characters except for a potential comma decimal separator
            value = re.sub(r'[^\d,]', '', value).replace(',', '.')
        return float(value)
    except (ValueError, TypeError):
        return 0.0
def extract_data_from_docx(uploaded_file):
    """Extracts data from the uploaded .docx file, reading from both paragraphs and tables."""
    try:
        document = Document(uploaded_file)
       
        # CORRECTED LOGIC: Read text from both paragraphs and tables
        content = []
        for para in document.paragraphs:
            content.append(para.text)
        for table in document.tables:
            for row in table.rows:
                for cell in row.cells:
                    content.append(cell.text)
        full_text = "\n".join(content)
        # --- Data Extraction using Improved Regex ---
       
        # Helper function for searching with multiple patterns
        def search_patterns(patterns, text):
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    # Return the first captured group
                    return match.group(1).strip()
            return "Không tìm thấy"
        # Extract customer name (finds the first "Họ và tên")
        ho_ten = search_patterns([r"(?:\d+\.\s*)?Họ và tên:\s*([^.\n]+)"], full_text)
       
        # Extract CCCD (finds the first CCCD number)
        cccd = search_patterns([r"CCCD số:\s*(\d+)"], full_text)
           
        # Extract address
        dia_chi_raw = search_patterns([r"Nơi cư trú:\s*(.+?)(?=\s*,?\s*Số điện thoại|\n)"], full_text)
        dia_chi = dia_chi_raw.strip(' ,"\n') if dia_chi_raw != "Không tìm thấy" else "Không tìm thấy"
           
        # Extract phone number
        sdt_raw = search_patterns([r"Số điện thoại:\s*([0-9\s,]+)"], full_text)
        sdt = "Không tìm thấy"
        if sdt_raw != "Không tìm thấy":
            sdt_cleaned = sdt_raw.split(',')[0].strip()
            sdt = re.sub(r'\D', '', sdt_cleaned)
        # Extract loan purpose
        muc_dich_vay = search_patterns([
            r"Mục đích vay:\s*([^\n]+)",
            r"Lĩnh vực kinh doanh chính:\s*([^\n]+)"
        ], full_text)
       
        # Extract total cost and revenue
        tong_chi_phi = "0"
        tong_doanh_thu = "0"
        # Find all totals; the first is cost, the last is revenue.
        matches = re.findall(r"TỔNG CỘNG[,\s]*([\d.,]+)", full_text)
        if len(matches) > 0:
            tong_chi_phi = matches[0]
        if len(matches) > 1:
            tong_doanh_thu = matches[-1]
        else: # If only one total is found, it's likely the cost
            tong_doanh_thu = "0"
        # Extract working capital requirement
        nhu_cau_von = search_patterns([r"Nhu cầu vốn lưu động trên một vòng quay[^\d]*([\d.,]+)"], full_text)
           
        # Extract equity capital
        von_doi_ung = search_patterns([r"Vốn đối ứng[^\d]+([\d.,]+)"], full_text)
           
        # Extract loan amount from Agribank
        von_vay = search_patterns([r"Vốn vay Agribank[^\d]+([\d.,]+)"], full_text)
           
        # Extract interest rate
        lai_suat_raw = search_patterns([r"Lãi suất đề nghị:\s*(\d+[\.,]?\d*)\s*%"], full_text)
        lai_suat = lai_suat_raw.replace(',', '.') if lai_suat_raw != "Không tìm thấy" else "0"
           
        # Extract loan term
        thoi_gian_vay = search_patterns([r"Thời hạn cho vay:\s*(\d+)\s*tháng"], full_text)

        # Extract additional fields
        nguon_tra_no = search_patterns([r"Nguồn trả nợ:\s*- (.+)"], full_text)
        tai_san_bao_dam = search_patterns([r"Tài sản bảo đảm:\s*(.+)"], full_text)
        doanh_thu_phuong_an = search_patterns([r"Doanh thu của phương án:\s*([\d.,]+)\s*đồng"], full_text)
        chi_phi_kinh_doanh = search_patterns([r"Chi phí kinh doanh:\s*([\d.,]+)\s*đồng"], full_text)
        chenh_lech_thu_chi = search_patterns([r"Chênh lệch thu chi:\s*([\d.,]+)\s*đồng"], full_text)
           
        data = {
            'ho_ten': ho_ten,
            'cccd': cccd,
            'dia_chi': dia_chi,
            'sdt': sdt,
            'muc_dich_vay': muc_dich_vay,
            'tong_chi_phi': tong_chi_phi,
            'tong_doanh_thu': tong_doanh_thu,
            'nhu_cau_von': nhu_cau_von,
            'von_doi_ung': von_doi_ung,
            'von_vay': von_vay,
            'lai_suat': lai_suat,
            'thoi_gian_vay': thoi_gian_vay,
            'nguon_tra_no': nguon_tra_no,
            'tai_san_bao_dam': tai_san_bao_dam,
            'doanh_thu_phuong_an': doanh_thu_phuong_an,
            'chi_phi_kinh_doanh': chi_phi_kinh_doanh,
            'chenh_lech_thu_chi': chenh_lech_thu_chi,
            'full_text': full_text
        }
       
        return data
    except Exception as e:
        st.error(f"Lỗi khi đọc và phân tích file Word: {e}")
        import traceback
        st.error(traceback.format_exc())
        return None
def generate_repayment_schedule(principal, annual_rate, term_months):
    """Creates a detailed loan repayment schedule."""
    if term_months <= 0 or principal <= 0 or annual_rate < 0:
        return pd.DataFrame()
   
    monthly_rate = (annual_rate / 100) / 12
    principal_payment = principal / term_months
   
    schedule = []
    remaining_balance = principal
   
    for i in range(1, term_months + 1):
        interest_payment = remaining_balance * monthly_rate
        total_payment = principal_payment + interest_payment
        remaining_balance -= principal_payment
       
        # Ensure remaining balance doesn't go below zero due to float precision
        if remaining_balance < 1:
            remaining_balance = 0
           
        schedule.append({
            'Kỳ': i,
            'Dư nợ đầu kỳ': remaining_balance + principal_payment,
            'Gốc trả': principal_payment,
            'Lãi trả': interest_payment,
            'Tổng trả': total_payment,
            'Dư nợ cuối kỳ': remaining_balance
        })
       
    df = pd.DataFrame(schedule)
    return df
def generate_report_text():
    """Generates the text content for the report export."""
    report_data = st.session_state.report_data
    schedule_df = st.session_state.schedule_df
   
    total_cost = report_data.get('tong_chi_phi', 0)
    total_revenue = report_data.get('tong_doanh_thu', 0)
    profit = total_revenue - total_cost
    profit_margin = (profit / total_revenue) * 100 if total_revenue > 0 else 0
   
    text = f"""
BÁO CÁO PHÂN TÍCH PHƯƠNG ÁN KINH DOANH
Ngày tạo: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
=================================================
I. THÔNG TIN KHÁCH HÀNG
-------------------------
- Họ và tên: {report_data.get('ho_ten', '')}
- CCCD: {report_data.get('cccd', '')}
- Địa chỉ: {report_data.get('dia_chi', '')}
- Số điện thoại: {report_data.get('sdt', '')}
II. THÔNG TIN KHOẢN VAY
-------------------------
- Mục đích vay: {report_data.get('muc_dich_vay', '')}
- Số tiền vay: {format_currency(report_data.get('von_vay', 0))} VND
- Lãi suất: {report_data.get('lai_suat', 0)}%/năm
- Thời gian vay: {report_data.get('thoi_gian_vay', 0)} tháng
III. PHÂN TÍCH TÀI CHÍNH (1 VÒNG QUAY)
----------------------------------------
- Tổng chi phí: {format_currency(total_cost)} VND
- Tổng doanh thu: {format_currency(total_revenue)} VND
- Lợi nhuận: {format_currency(profit)} VND
- Tỷ suất lợi nhuận: {profit_margin:.2f}%
- Tổng nhu cầu vốn: {format_currency(report_data.get('nhu_cau_von', 0))} VND
- Vốn đối ứng: {format_currency(report_data.get('von_doi_ung', 0))} VND
IV. KẾ HOẠCH TRẢ NỢ
--------------------
{schedule_df.to_string(index=False) if not schedule_df.empty else "Chưa có kế hoạch trả nợ."}
V. PHÂN TÍCH TỪ AI (NẾU CÓ)
-----------------------------
{st.session_state.get('ai_analysis', 'Chưa có phân tích từ AI.')}
=================================================
"""
    return text
# ==============================================================================
# SESSION STATE INITIALIZATION
# ==============================================================================
if 'data_extracted' not in st.session_state:
    st.session_state.data_extracted = False
    st.session_state.report_data = {}
    st.session_state.schedule_df = pd.DataFrame()
    st.session_state.ai_analysis = ""
    st.session_state.full_text = ""
if "messages" not in st.session_state:
    st.session_state.messages = []
# ==============================================================================
# UI - SIDEBAR
# ==============================================================================
with st.sidebar:
    st.header("Thiết lập")
    api_key = st.text_input("🔑 Nhập Gemini API Key", type="password", help="API Key của bạn sẽ không được lưu trữ.")
   
    uploaded_file = st.file_uploader(
        "Tải lên Phương án Kinh doanh (.docx)",
        type=['docx'],
        accept_multiple_files=False
    )
   
    if uploaded_file:
        if st.button("Xử lý File"):
            with st.spinner('Đang trích xuất và phân tích dữ liệu...'):
                extracted_data = extract_data_from_docx(uploaded_file)
                if extracted_data:
                    st.session_state.report_data = {
                        'ho_ten': extracted_data.get('ho_ten', ''),
                        'cccd': extracted_data.get('cccd', ''),
                        'dia_chi': extracted_data.get('dia_chi', ''),
                        'sdt': extracted_data.get('sdt', ''),
                        'muc_dich_vay': extracted_data.get('muc_dich_vay', ''),
                        'tong_chi_phi': safe_float(extracted_data.get('tong_chi_phi', 0)),
                        'tong_doanh_thu': safe_float(extracted_data.get('tong_doanh_thu', 0)),
                        'nhu_cau_von': safe_float(extracted_data.get('nhu_cau_von', 0)),
                        'von_doi_ung': safe_float(extracted_data.get('von_doi_ung', 0)),
                        'von_vay': safe_float(extracted_data.get('von_vay', 0)),
                        'lai_suat': safe_float(extracted_data.get('lai_suat', 0)),
                        'thoi_gian_vay': int(safe_float(extracted_data.get('thoi_gian_vay', 0))),
                        'nguon_tra_no': extracted_data.get('nguon_tra_no', ''),
                        'tai_san_bao_dam': extracted_data.get('tai_san_bao_dam', ''),
                        'doanh_thu_phuong_an': safe_float(extracted_data.get('doanh_thu_phuong_an', 0)),
                        'chi_phi_kinh_doanh': safe_float(extracted_data.get('chi_phi_kinh_doanh', 0)),
                        'chenh_lech_thu_chi': safe_float(extracted_data.get('chenh_lech_thu_chi', 0)),
                    }
                    st.session_state.full_text = extracted_data.get('full_text', '')
                    st.session_state.data_extracted = True
                    st.success("Trích xuất dữ liệu thành công!")
                    st.rerun()
    if st.session_state.data_extracted:
        st.download_button(
            label="📄 Tải xuống Báo cáo (.txt)",
            data=generate_report_text(),
            file_name=f"Bao_cao_tham_dinh_{st.session_state.report_data.get('ho_ten', 'KH').replace(' ', '_')}.txt",
            mime='text/plain',
        )
       
    if st.button("🗑️ Xóa dữ liệu & Trò chuyện"):
        st.session_state.data_extracted = False
        st.session_state.report_data = {}
        st.session_state.schedule_df = pd.DataFrame()
        st.session_state.ai_analysis = ""
        st.session_state.full_text = ""
        st.session_state.messages = []
        st.rerun()
# ==============================================================================
# UI - MAIN PAGE
# ==============================================================================
st.title("📊 Thẩm định Phương án Kinh doanh của Khách hàng")
st.markdown("---")
if not st.session_state.data_extracted:
    st.info("Vui lòng tải lên file phương án kinh doanh (.docx), sau đó nhấn 'Xử lý File' ở thanh bên trái để bắt đầu.")
else:
    col1, col2 = st.columns(2)
    with col1:
        with st.expander("👤 **Thông tin khách hàng**", expanded=True):
            st.session_state.report_data['ho_ten'] = st.text_input("Họ và tên", value=st.session_state.report_data.get('ho_ten'))
            st.session_state.report_data['cccd'] = st.text_input("CCCD", value=st.session_state.report_data.get('cccd'))
            st.session_state.report_data['dia_chi'] = st.text_input("Địa chỉ", value=st.session_state.report_data.get('dia_chi'))
            st.session_state.report_data['sdt'] = st.text_input("Số điện thoại", value=st.session_state.report_data.get('sdt'))
   
    with col2:
        with st.expander("💰 **Thông tin khoản vay**", expanded=True):
            st.session_state.report_data['muc_dich_vay'] = st.text_input("Mục đích vay", value=st.session_state.report_data.get('muc_dich_vay'))
            st.session_state.report_data['von_vay'] = st.number_input("Số tiền vay (VND)", min_value=0, value=int(st.session_state.report_data.get('von_vay', 0)), step=1000000, format="%d")
            st.session_state.report_data['lai_suat'] = st.number_input("Lãi suất (%/năm)", min_value=0.0, value=st.session_state.report_data.get('lai_suat', 0.0), step=0.1, format="%.1f")
            st.session_state.report_data['thoi_gian_vay'] = st.number_input("Thời gian vay (tháng)", min_value=1, value=int(st.session_state.report_data.get('thoi_gian_vay', 1)), step=1, format="%d")
            st.session_state.report_data['nguon_tra_no'] = st.text_input("Nguồn trả nợ", value=st.session_state.report_data.get('nguon_tra_no', ''))
            st.session_state.report_data['tai_san_bao_dam'] = st.text_area("Tổng tài sản đảm bảo", value=st.session_state.report_data.get('tai_san_bao_dam', ''))
            st.session_state.report_data['doanh_thu_phuong_an'] = st.number_input("Doanh thu của phương án (VND)", min_value=0, value=int(st.session_state.report_data.get('doanh_thu_phuong_an', 0)), step=1000000, format="%d")
            st.session_state.report_data['chi_phi_kinh_doanh'] = st.number_input("Chi phí kinh doanh (VND)", min_value=0, value=int(st.session_state.report_data.get('chi_phi_kinh_doanh', 0)), step=1000000, format="%d")
            st.session_state.report_data['chenh_lech_thu_chi'] = st.number_input("Chênh lệch thu chi (VND)", min_value=0, value=int(st.session_state.report_data.get('chenh_lech_thu_chi', 0)), step=1000000, format="%d")
    st.markdown("---")
    st.subheader("📈 Phân tích tài chính và Trực quan hóa")
   
    total_cost = st.session_state.report_data.get('tong_chi_phi', 0)
    total_revenue = st.session_state.report_data.get('tong_doanh_thu', 0)
    loan_amount = st.session_state.report_data.get('von_vay', 0)
    equity = st.session_state.report_data.get('von_doi_ung', 0)
   
    profit = total_revenue - total_cost
    profit_margin = (profit / total_revenue) * 100 if total_revenue > 0 else 0
   
    metric_col1, metric_col2, metric_col3 = st.columns(3)
    metric_col1.metric("Lợi nhuận (1 vòng quay)", f"{format_currency(profit)} VND", delta=f"{format_currency(profit)} VND" if profit != 0 else None)
    metric_col2.metric("Tỷ suất lợi nhuận", f"{profit_margin:.2f}%")
    metric_col3.metric("Tổng chi phí (1 vòng quay)", f"{format_currency(total_cost)} VND")
    viz_col1, viz_col2 = st.columns(2)
    with viz_col1:
        st.markdown("##### Cơ cấu Doanh thu")
        if total_revenue > 0 and profit >= 0:
            fig_pie = go.Figure(data=[go.Pie(
                labels=['Tổng chi phí', 'Lợi nhuận'],
                values=[total_cost, profit],
                hole=.3,
                marker_colors=['#ff9999', '#66b3ff']
            )])
            fig_pie.update_layout(showlegend=True, margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.warning("Không đủ dữ liệu doanh thu và lợi nhuận để vẽ biểu đồ.")
    with viz_col2:
        st.markdown("##### Cơ cấu Nguồn vốn")
        if (loan_amount + equity) > 0:
            fig_bar = go.Figure(data=[go.Bar(
                x=['Vốn đối ứng', 'Vốn vay'],
                y=[equity, loan_amount],
                marker_color=['#4CAF50', '#F44336']
            )])
            fig_bar.update_layout(yaxis_title='Số tiền (VND)', margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.warning("Không có dữ liệu vốn để vẽ biểu đồ.")
    st.markdown("---")
    st.subheader("🗓️ Kế hoạch trả nợ dự kiến")
   
    schedule_df = generate_repayment_schedule(
        st.session_state.report_data['von_vay'],
        st.session_state.report_data['lai_suat'],
        st.session_state.report_data['thoi_gian_vay']
    )
    st.session_state.schedule_df = schedule_df
   
    if not schedule_df.empty:
        display_df = schedule_df.copy()
        for col in ['Dư nợ đầu kỳ', 'Gốc trả', 'Lãi trả', 'Tổng trả', 'Dư nợ cuối kỳ']:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(format_currency)
        st.dataframe(display_df, use_container_width=True)
       
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            schedule_df.to_excel(writer, index=False, sheet_name='KeHoachTraNo')
        excel_data = output.getvalue()
       
        st.download_button(
            label="📥 Tải xuống Kế hoạch trả nợ (.xlsx)",
            data=excel_data,
            file_name=f"Ke_hoach_tra_no_{st.session_state.report_data.get('ho_ten', 'KH').replace(' ', '_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("Vui lòng nhập đầy đủ thông tin khoản vay để tạo kế hoạch trả nợ.")
       
    st.markdown("---")
    st.subheader("🤖 Phân tích từ Trợ lý AI")
   
    if not api_key:
        st.warning("Vui lòng nhập Gemini API Key ở thanh bên trái để sử dụng các tính năng AI.")
    else:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.5-flash')
        except Exception as e:
            st.error(f"Lỗi khi cấu hình Gemini: {e}")
            model = None
           
        if model:
            if st.button("🚀 AI Phân tích Nhanh", help="Gửi toàn bộ thông tin dự án đến AI để nhận phân tích tổng quan."):
                with st.spinner("AI đang phân tích, vui lòng chờ..."):
                    prompt = f"""
                    Bạn là một chuyên gia thẩm định tín dụng giàu kinh nghiệm. Dưới đây là toàn bộ phương án kinh doanh của khách hàng.
                    {st.session_state.full_text}
                    ---
                    DỰA VÀO DỮ LIỆU TRÊN, HÃY CUNG CẤP MỘT BÁO CÁO NGẮN GỌN:
                    1. **Điểm mạnh:** 2-3 gạch đầu dòng về các ưu điểm của phương án (ví dụ: tỷ suất lợi nhuận, vốn đối ứng).
                    2. **Điểm yếu:** 2-3 gạch đầu dòng về các nhược điểm hoặc điểm cần làm rõ (ví dụ: chi phí bất thường, vòng quay vốn).
                    3. **Rủi ro:** 2-3 gạch đầu dòng về các rủi ro tiềm ẩn (ví dụ: biến động giá nguyên vật liệu, khả năng thu hồi công nợ).
                    4. **Đề xuất cuối cùng:** In đậm và chỉ ghi một trong hai cụm từ: "NÊN CHO VAY" hoặc "CẦN XEM XÉT THÊM".
                    """
                    try:
                        response = model.generate_content(prompt)
                        st.session_state.ai_analysis = response.text
                        st.markdown(st.session_state.ai_analysis)
                    except Exception as e:
                        st.error(f"Đã xảy ra lỗi khi gọi API của Gemini: {e}")
            st.markdown("##### Trò chuyện với Trợ lý AI")
           
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
                   
            if prompt := st.chat_input("Đặt câu hỏi về phương án kinh doanh này..."):
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)
                with st.chat_message("assistant"):
                    with st.spinner("AI đang suy nghĩ..."):
                        context_prompt = f"""
                        Bối cảnh: Bạn là trợ lý phân tích tín dụng. Hãy dựa vào nội dung phương án kinh doanh dưới đây để trả lời câu hỏi của người dùng.
                       
                        Nội dung phương án kinh doanh:
                        {st.session_state.full_text}
                        ---
                        Câu hỏi của người dùng: {prompt}
                        """
                        try:
                            response = model.generate_content(context_prompt)
                            response_text = response.text
                            st.markdown(response_text)
                            st.session_state.messages.append({"role": "assistant", "content": response_text})
                        except Exception as e:
                            error_message = f"Xin lỗi, đã có lỗi xảy ra: {e}"
                            st.markdown(error_message)
                            st.session_state.messages.append({"role": "assistant", "content": error_message})
