import streamlit as st
import pandas as pd
import docx
import re
import io
import google.generativeai as genai
from streamlit_chat import message

# =================================================================================
# Cấu hình trang (Page Configuration)
# =================================================================================
st.set_page_config(
    page_title="Hệ thống thẩm định phương án kinh doanh",
    page_icon="💼",
    layout="wide"
)

# =================================================================================
# Các hàm trợ giúp (Helper Functions)
# =================================================================================

def format_number(n):
    """Định dạng số với dấu chấm phân cách hàng nghìn."""
    if isinstance(n, (int, float)):
        return f"{n:,.0f}".replace(",", ".")
    return n

def extract_data_from_docx(uploaded_file):
    """Trích xuất thông tin từ file .docx."""
    try:
        doc = docx.Document(uploaded_file)
        full_text = "\n".join([para.text for para in doc.paragraphs])

        # Sử dụng regex để tìm kiếm thông tin
        data = {
            "ho_ten": re.search(r"(Họ và tên|Họ tên khách hàng)\s*:\s*(.*)", full_text, re.IGNORECASE),
            "cccd": re.search(r"(CCCD|CMND|Căn cước công dân)\s*:\s*(.*)", full_text, re.IGNORECASE),
            "dia_chi": re.search(r"Địa chỉ\s*:\s*(.*)", full_text, re.IGNORECASE),
            "sdt": re.search(r"(Số điện thoại|SĐT)\s*:\s*(.*)", full_text, re.IGNORECASE),
            "muc_dich": re.search(r"(Mục đích vay vốn|Mục đích)\s*:\s*(.*)", full_text, re.IGNORECASE),
            "tong_nhu_cau": re.search(r"(Tổng nhu cầu vốn|Tổng nhu cầu)\s*:\s*([\d.,]+)", full_text, re.IGNORECASE),
            "von_doi_ung": re.search(r"(Vốn đối ứng|Vốn tự có)\s*:\s*([\d.,]+)", full_text, re.IGNORECASE),
            "so_tien_vay": re.search(r"(Số tiền vay|Đề nghị vay)\s*:\s*([\d.,]+)", full_text, re.IGNORECASE),
            "lai_suat": re.search(r"Lãi suất\s*:\s*([\d.,]+)%", full_text, re.IGNORECASE),
            "thoi_gian_vay": re.search(r"(Thời gian vay|Thời hạn vay)\s*:\s*(\d+)", full_text, re.IGNORECASE),
        }

        extracted = {}
        for key, match in data.items():
            if match:
                value = match.group(2).strip() if key not in ["tong_nhu_cau", "von_doi_ung", "so_tien_vay", "lai_suat", "thoi_gian_vay"] else match.group(2).replace(".", "").replace(",", "")
                try:
                    extracted[key] = int(value) if value.isdigit() else float(value) if key == "lai_suat" else value
                except (ValueError, TypeError):
                    extracted[key] = value
            else:
                extracted[key] = None
        return extracted
    except Exception as e:
        st.error(f"Lỗi khi đọc file .docx: {e}")
        return {}


def calculate_repayment_schedule(principal, annual_rate, years):
    """Tính toán bảng kế hoạch trả nợ."""
    if not all([principal > 0, annual_rate > 0, years > 0]):
        return pd.DataFrame()

    monthly_rate = (annual_rate / 100) / 12
    num_months = years * 12
    
    # Công thức trả nợ gốc đều, lãi trên dư nợ giảm dần
    principal_payment = principal / num_months

    remaining_balance = principal
    schedule_data = []

    for month in range(1, num_months + 1):
        interest_payment = remaining_balance * monthly_rate
        total_payment = principal_payment + interest_payment
        remaining_balance -= principal_payment
        
        # Đảm bảo dư nợ cuối kỳ cuối cùng là 0
        if month == num_months:
            remaining_balance = 0

        schedule_data.append({
            "Kỳ trả nợ": month,
            "Dư nợ đầu kỳ": round(principal_payment * (num_months - month + 1) + interest_payment),
            "Gốc phải trả": round(principal_payment),
            "Lãi phải trả": round(interest_payment),
            "Tổng gốc và lãi": round(total_payment),
            "Dư nợ cuối kỳ": round(remaining_balance),
        })
    
    df = pd.DataFrame(schedule_data)
    return df

# =================================================================================
# Khởi tạo Session State (Initialize Session State)
# =================================================================================
if 'params' not in st.session_state:
    st.session_state.params = {
        "ho_ten": "", "cccd": "", "dia_chi": "", "sdt": "",
        "muc_dich": "", "tong_nhu_cau": 100000000, "von_doi_ung": 20000000,
        "so_tien_vay": 80000000, "lai_suat": 8.5, "thoi_gian_vay": 5
    }
if 'gemini_analysis_result' not in st.session_state:
    st.session_state.gemini_analysis_result = ""
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []


# =================================================================================
# Giao diện chính (Main Interface)
# =================================================================================
st.title("💼 Hệ thống thẩm định phương án kinh doanh")
st.markdown("---")

# --- Thanh bên (Sidebar) ---
with st.sidebar:
    st.header("Cài đặt và Chức năng")
    
    # 1. Nhập API Key
    api_key = st.text_input("🔑 Nhập API Key Gemini của bạn", type="password", help="API Key của bạn sẽ không được lưu trữ.")
    
    # 2. Upload file
    uploaded_file = st.file_uploader("📂 Upload phương án vay vốn (.docx)", type=["docx"])
    
    if uploaded_file:
        if st.button("Xử lý file"):
            with st.spinner("Đang trích xuất dữ liệu..."):
                extracted_data = extract_data_from_docx(uploaded_file)
                # Cập nhật state với dữ liệu mới, chỉ ghi đè những trường có giá trị
                for key, value in extracted_data.items():
                    if value is not None:
                        st.session_state.params[key] = value
                st.success("Trích xuất thành công! Vui lòng kiểm tra và chỉnh sửa nếu cần.")

    # 6. Nút xuất phân tích
    st.markdown("---")
    st.subheader("Xuất báo cáo")
    full_report = ""
    if st.session_state.gemini_analysis_result:
        report_data = st.session_state.params.copy()
        report_data["phan_tich_ai"] = st.session_state.gemini_analysis_result
        
        full_report = "BÁO CÁO THẨM ĐỊNH PHƯƠNG ÁN KINH DOANH\n"
        full_report += "="*50 + "\n"
        full_report += f"Họ và tên: {report_data.get('ho_ten', '')}\n"
        full_report += f"CCCD: {report_data.get('cccd', '')}\n"
        full_report += f"Địa chỉ: {report_data.get('dia_chi', '')}\n"
        full_report += "-"*20 + "\n"
        full_report += f"Số tiền vay: {format_number(report_data.get('so_tien_vay', 0))} VNĐ\n"
        full_report += f"Thời gian vay: {report_data.get('thoi_gian_vay', 0)} năm\n"
        full_report += f"Lãi suất: {report_data.get('lai_suat', 0)} %/năm\n"
        full_report += "-"*20 + "\n"
        full_report += "KẾT LUẬN TỪ AI:\n"
        full_report += report_data['phan_tich_ai']

    st.download_button(
        label="📥 Tải xuống báo cáo thẩm định",
        data=full_report.encode('utf-8'),
        file_name="bao_cao_tham_dinh.txt",
        mime="text/plain",
        disabled=not bool(st.session_state.gemini_analysis_result)
    )


# --- Khu vực chính (Main Area) ---
col1, col2 = st.columns(2)

with col1:
    with st.expander("👤 **Thông tin khách hàng**", expanded=True):
        st.session_state.params['ho_ten'] = st.text_input("Họ và tên", st.session_state.params['ho_ten'])
        st.session_state.params['cccd'] = st.text_input("CCCD/CMND", st.session_state.params['cccd'])
        st.session_state.params['dia_chi'] = st.text_input("Địa chỉ", st.session_state.params['dia_chi'])
        st.session_state.params['sdt'] = st.text_input("Số điện thoại", st.session_state.params['sdt'])

with col2:
    with st.expander("📝 **Thông tin phương án sử dụng vốn**", expanded=True):
        st.session_state.params['muc_dich'] = st.text_area("Mục đích vay vốn", st.session_state.params['muc_dich'])
        st.session_state.params['tong_nhu_cau'] = st.number_input("Tổng nhu cầu vốn (VNĐ)", min_value=0, value=st.session_state.params['tong_nhu_cau'], step=1000000, format="%d")
        st.session_state.params['von_doi_ung'] = st.number_input("Vốn đối ứng (VNĐ)", min_value=0, value=st.session_state.params['von_doi_ung'], step=1000000, format="%d")
        st.session_state.params['so_tien_vay'] = st.number_input("Số tiền vay (VNĐ)", min_value=0, value=st.session_state.params['so_tien_vay'], step=1000000, format="%d")
        st.session_state.params['lai_suat'] = st.number_input("Lãi suất (%/năm)", min_value=0.0, value=st.session_state.params['lai_suat'], step=0.1, format="%.1f")
        st.session_state.params['thoi_gian_vay'] = st.number_input("Thời gian vay (năm)", min_value=0, value=st.session_state.params['thoi_gian_vay'], step=1)

# --- Bảng kế hoạch trả nợ (Repayment Schedule) ---
st.markdown("---")
st.subheader("🗓️ Bảng kế hoạch trả nợ dự kiến")

repayment_df = calculate_repayment_schedule(
    st.session_state.params['so_tien_vay'],
    st.session_state.params['lai_suat'],
    st.session_state.params['thoi_gian_vay']
)

if not repayment_df.empty:
    # Định dạng lại các cột số
    df_display = repayment_df.copy()
    for col in ["Dư nợ đầu kỳ", "Gốc phải trả", "Lãi phải trả", "Tổng gốc và lãi", "Dư nợ cuối kỳ"]:
        df_display[col] = df_display[col].apply(format_number)
    
    st.dataframe(df_display, use_container_width=True)

    # 3. Chức năng tải xuống Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        repayment_df.to_excel(writer, index=False, sheet_name='KeHoachTraNo')
    excel_data = output.getvalue()

    st.download_button(
        label="📄 Tải xuống kế hoạch trả nợ (Excel)",
        data=excel_data,
        file_name="ke_hoach_tra_no.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
else:
    st.warning("Vui lòng nhập đầy đủ thông tin khoản vay để xem kế hoạch trả nợ.")

# --- Phân tích của Gemini AI (Gemini AI Analysis) ---
st.markdown("---")
st.subheader("🤖 Phân tích và Đề xuất từ Gemini AI")

# 4. Nút phân tích
if st.button("Bắt đầu phân tích với Gemini"):
    if not api_key:
        st.error("Vui lòng nhập API Key của Gemini ở thanh bên trái.")
    else:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
            
            prompt = f"""
            Với vai trò là một chuyên gia thẩm định tín dụng, hãy phân tích phương án kinh doanh dưới đây và đưa ra đề xuất.
            
            **Thông tin khách hàng:**
            - Họ và tên: {st.session_state.params['ho_ten']}
            - CCCD: {st.session_state.params['cccd']}
            
            **Thông tin khoản vay:**
            - Mục đích: {st.session_state.params['muc_dich']}
            - Tổng nhu cầu vốn: {format_number(st.session_state.params['tong_nhu_cau'])} VNĐ
            - Vốn đối ứng: {format_number(st.session_state.params['von_doi_ung'])} VNĐ ({ (st.session_state.params['von_doi_ung'] / st.session_state.params['tong_nhu_cau'] * 100) if st.session_state.params['tong_nhu_cau'] > 0 else 0 :.2f}%)
            - Số tiền vay: {format_number(st.session_state.params['so_tien_vay'])} VNĐ
            - Thời gian vay: {st.session_state.params['thoi_gian_vay']} năm
            - Lãi suất: {st.session_state.params['lai_suat']}%/năm
            
            **Yêu cầu:**
            1. Phân tích ngắn gọn tính khả thi của phương án.
            2. Đánh giá rủi ro (nếu có).
            3. Đưa ra kết luận cuối cùng: **ĐỀ XUẤT CHO VAY** hoặc **KHÔNG ĐỀ XUẤT CHO VAY**. Trình bày rõ ràng, súc tích, chuyên nghiệp.
            """

            with st.spinner("AI đang phân tích, vui lòng chờ..."):
                response = model.generate_content(prompt)
                st.session_state.gemini_analysis_result = response.text
            st.success("Phân tích hoàn tất!")

        except Exception as e:
            st.error(f"Đã xảy ra lỗi khi kết nối với Gemini: {e}")

if st.session_state.gemini_analysis_result:
    st.markdown(st.session_state.gemini_analysis_result)

# 5. Chatbot với Gemini
st.markdown("---")
st.subheader("💬 Chat với Trợ lý AI")

if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

def get_gemini_response(question, chat_history):
    if not api_key:
        st.warning("Vui lòng nhập API Key để bắt đầu chat.")
        return None
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
        
        # Tạo context từ lịch sử chat
        history_context = []
        for entry in chat_history:
            role = "user" if entry["is_user"] else "model"
            history_context.append({"role": role, "parts": [{"text": entry["content"]}]})
        
        # Thêm câu hỏi mới
        history_context.append({"role": "user", "parts": [{"text": question}]})

        response = model.generate_content(history_context)
        return response.text
    except Exception as e:
        st.error(f"Lỗi: {e}")
        return None

# Nút xóa đoạn chat
if st.button("Xóa lịch sử Chat"):
    st.session_state.chat_history = []
    st.rerun()

# Hiển thị lịch sử chat
for i, chat in enumerate(st.session_state.chat_history):
    message(chat["content"], is_user=chat["is_user"], key=f"chat_{i}")

user_input = st.chat_input("Bạn có câu hỏi gì về phương án này không?")

if user_input:
    st.session_state.chat_history.append({"content": user_input, "is_user": True})
    with st.spinner("AI đang suy nghĩ..."):
        ai_response = get_gemini_response(user_input, st.session_state.chat_history)
    if ai_response:
        st.session_state.chat_history.append({"content": ai_response, "is_user": False})
    st.rerun()
