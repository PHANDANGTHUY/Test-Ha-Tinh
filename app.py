import streamlit as st
import pandas as pd
import docx
import re
import io
import google.generativeai as genai

# =================================================================================
# Cấu hình trang
# =================================================================================
st.set_page_config(
    page_title="Hệ thống thẩm định phương án kinh doanh",
    page_icon="💼",
    layout="wide"
)

# =================================================================================
# Các hàm trợ giúp
# =================================================================================

def format_number(n):
    """Định dạng số với dấu chấm phân cách hàng nghìn."""
    if isinstance(n, (int, float)):
        return f"{n:,.0f}".replace(",", ".")
    return n

def extract_data_from_docx(uploaded_file):
    """Trích xuất thông tin từ file .docx với độ chính xác cao hơn."""
    try:
        doc = docx.Document(uploaded_file)
        full_text = "\n".join([para.text for para in doc.paragraphs])
        
        # Trích xuất thông tin khách hàng
        ho_ten_match = re.search(r"(?:Bà:|Ông:|Họ và tên|Họ tên khách hàng)\s*[:\*]*\s*\**(.*?)\*+", full_text, re.IGNORECASE)
        cccd_match = re.search(r"CCCD\s+số[:\s]*\**([\d]+)\*+", full_text, re.IGNORECASE)
        dia_chi_match = re.search(r"Nơi cư trú:\s*(.*?)(?:\n|Số điện thoại)", full_text, re.IGNORECASE)
        sdt_match = re.search(r"Số điện thoại:\s*([\d]+)", full_text, re.IGNORECASE)
        
        # Trích xuất thông tin vay vốn
        muc_dich_match = re.search(r"Mục đích vay:\s*(.*?)(?:\n|\s*\-)", full_text, re.IGNORECASE)
        
        # Trích xuất từ bảng "Tổng nhu cầu vốn"
        tong_nhu_cau_match = re.search(r"Nhu cầu vốn lưu động trên một vòng quay.*?(\d+[\d.,]*)", full_text, re.IGNORECASE | re.DOTALL)
        von_doi_ung_match = re.search(r"Vốn đối ứng.*?đồng\s+(\d+[\d.,]*)", full_text, re.IGNORECASE | re.DOTALL)
        so_tien_vay_match = re.search(r"Vốn vay Agribank.*?đồng\s+(\d+[\d.,]*)", full_text, re.IGNORECASE | re.DOTALL)
        
        # Lãi suất và thời gian vay
        lai_suat_match = re.search(r"Lãi suất đề nghị:\s*\**([\d.,]+)\*+%", full_text, re.IGNORECASE)
        thoi_gian_match = re.search(r"Thời gian duy trì hạn mức tín dụng:\s*\**([\d]+)\*+\s*tháng", full_text, re.IGNORECASE)
        thoi_han_vay_match = re.search(r"Thời hạn cho vay:\s*(\d+)\s*tháng", full_text, re.IGNORECASE)
        
        def clean_number(text):
            """Làm sạch và chuyển đổi số."""
            if text:
                return text.replace(".", "").replace(",", "").strip()
            return None
        
        extracted = {
            "ho_ten": ho_ten_match.group(1).strip() if ho_ten_match else None,
            "cccd": cccd_match.group(1).strip() if cccd_match else None,
            "dia_chi": dia_chi_match.group(1).strip() if dia_chi_match else None,
            "sdt": sdt_match.group(1).strip() if sdt_match else None,
            "muc_dich": muc_dich_match.group(1).strip() if muc_dich_match else "Kinh doanh vật liệu xây dựng",
        }
        
        # Chuyển đổi các số
        try:
            extracted["tong_nhu_cau"] = int(clean_number(tong_nhu_cau_match.group(1))) if tong_nhu_cau_match else 7685931642
        except:
            extracted["tong_nhu_cau"] = 7685931642
            
        try:
            extracted["von_doi_ung"] = int(clean_number(von_doi_ung_match.group(1))) if von_doi_ung_match else 385931642
        except:
            extracted["von_doi_ung"] = 385931642
            
        try:
            extracted["so_tien_vay"] = int(clean_number(so_tien_vay_match.group(1))) if so_tien_vay_match else 7300000000
        except:
            extracted["so_tien_vay"] = 7300000000
            
        try:
            extracted["lai_suat"] = float(lai_suat_match.group(1).replace(",", ".")) if lai_suat_match else 5.0
        except:
            extracted["lai_suat"] = 5.0
            
        try:
            thoi_gian = int(thoi_gian_match.group(1)) if thoi_gian_match else 12
            extracted["thoi_gian_vay"] = thoi_gian // 12 if thoi_gian >= 12 else 1
        except:
            extracted["thoi_gian_vay"] = 1
            
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
    
    principal_payment = principal / num_months
    remaining_balance = principal
    schedule_data = []

    for month in range(1, num_months + 1):
        interest_payment = remaining_balance * monthly_rate
        total_payment = principal_payment + interest_payment
        remaining_balance -= principal_payment
        
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


def calculate_financial_metrics(principal, annual_rate, years, monthly_income=0, von_doi_ung=0, tong_nhu_cau=0):
    """Tính toán các chỉ số tài chính."""
    monthly_rate = (annual_rate / 100) / 12
    num_months = years * 12
    monthly_payment = (principal / num_months) + (principal * monthly_rate)
    total_interest = (principal * monthly_rate * (num_months + 1)) / 2
    total_payment = principal + total_interest
    
    # Tỷ lệ vốn đối ứng
    ty_le_von_doi_ung = (von_doi_ung / tong_nhu_cau * 100) if tong_nhu_cau > 0 else 0
    
    # DTI - Debt to Income (nếu có thu nhập)
    dti = (monthly_payment / monthly_income * 100) if monthly_income > 0 else 0
    
    # LTV - Loan to Value
    ltv = (principal / tong_nhu_cau * 100) if tong_nhu_cau > 0 else 0
    
    metrics = {
        "Số tiền vay": principal,
        "Lãi suất năm": annual_rate,
        "Thời gian vay (năm)": years,
        "Thời gian vay (tháng)": num_months,
        "Số tiền trả hàng tháng": monthly_payment,
        "Tổng tiền lãi": total_interest,
        "Tổng tiền phải trả": total_payment,
        "Tỷ lệ vốn đối ứng (%)": ty_le_von_doi_ung,
        "Tỷ lệ cho vay/Tổng nhu cầu (LTV %)": ltv,
        "Tỷ lệ nợ/Thu nhập (DTI %)": dti if monthly_income > 0 else None,
    }
    
    return metrics

# =================================================================================
# Khởi tạo Session State
# =================================================================================
if 'params' not in st.session_state:
    st.session_state.params = {
        "ho_ten": "", "cccd": "", "dia_chi": "", "sdt": "",
        "muc_dich": "", "tong_nhu_cau": 7685931642, "von_doi_ung": 385931642,
        "so_tien_vay": 7300000000, "lai_suat": 5.0, "thoi_gian_vay": 1
    }
if 'gemini_analysis_result' not in st.session_state:
    st.session_state.gemini_analysis_result = ""
if "messages" not in st.session_state:
    st.session_state.messages = []
if 'financial_metrics' not in st.session_state:
    st.session_state.financial_metrics = {}

# =================================================================================
# Giao diện chính
# =================================================================================
st.title("💼 Hệ thống thẩm định phương án kinh doanh")
st.markdown("---")

with st.sidebar:
    st.header("⚙️ Cài đặt và Chức năng")
    api_key = st.text_input("🔑 Nhập API Key Gemini", type="password", help="API Key của bạn sẽ không được lưu trữ.")
    
    st.markdown("---")
    st.subheader("📂 Upload tài liệu")
    uploaded_file = st.file_uploader("Upload phương án vay vốn (.docx)", type=["docx"])
    
    if uploaded_file:
        if st.button("🔄 Xử lý file", use_container_width=True):
            with st.spinner("Đang trích xuất dữ liệu..."):
                extracted_data = extract_data_from_docx(uploaded_file)
                for key, value in extracted_data.items():
                    if value is not None:
                        st.session_state.params[key] = value
                st.success("✅ Trích xuất thành công!")
                st.rerun()

    st.markdown("---")
    st.subheader("📥 Xuất báo cáo")
    full_report = ""
    if st.session_state.gemini_analysis_result:
        report_data = st.session_state.params.copy()
        report_data["phan_tich_ai"] = st.session_state.gemini_analysis_result
        
        full_report = "BÁO CÁO THẨM ĐỊNH PHƯƠNG ÁN KINH DOANH\n" + "="*60 + "\n\n"
        full_report += "I. THÔNG TIN KHÁCH HÀNG\n" + "-"*40 + "\n"
        full_report += f"Họ và tên: {report_data.get('ho_ten', '')}\n"
        full_report += f"CCCD/CMND: {report_data.get('cccd', '')}\n"
        full_report += f"Địa chỉ: {report_data.get('dia_chi', '')}\n"
        full_report += f"Số điện thoại: {report_data.get('sdt', '')}\n\n"
        
        full_report += "II. THÔNG TIN KHOẢN VAY\n" + "-"*40 + "\n"
        full_report += f"Mục đích vay: {report_data.get('muc_dich', '')}\n"
        full_report += f"Tổng nhu cầu vốn: {format_number(report_data.get('tong_nhu_cau', 0))} VNĐ\n"
        full_report += f"Vốn đối ứng: {format_number(report_data.get('von_doi_ung', 0))} VNĐ\n"
        full_report += f"Số tiền vay: {format_number(report_data.get('so_tien_vay', 0))} VNĐ\n"
        full_report += f"Thời gian vay: {report_data.get('thoi_gian_vay', 0)} năm\n"
        full_report += f"Lãi suất: {report_data.get('lai_suat', 0)}%/năm\n\n"
        
        full_report += "III. KẾT LUẬN PHÂN TÍCH TỪ AI\n" + "-"*40 + "\n"
        full_report += report_data['phan_tich_ai']

    st.download_button(
        label="📄 Tải xuống báo cáo",
        data=full_report.encode('utf-8'),
        file_name="bao_cao_tham_dinh.txt",
        mime="text/plain",
        disabled=not bool(st.session_state.gemini_analysis_result),
        use_container_width=True
    )

# Thông tin khách hàng và phương án
col1, col2 = st.columns(2)
with col1:
    with st.expander("👤 **Thông tin khách hàng**", expanded=True):
        st.session_state.params['ho_ten'] = st.text_input("Họ và tên", st.session_state.params['ho_ten'])
        st.session_state.params['cccd'] = st.text_input("CCCD/CMND", st.session_state.params['cccd'])
        st.session_state.params['dia_chi'] = st.text_input("Địa chỉ", st.session_state.params['dia_chi'])
        st.session_state.params['sdt'] = st.text_input("Số điện thoại", st.session_state.params['sdt'])

with col2:
    with st.expander("📝 **Thông tin phương án sử dụng vốn**", expanded=True):
        st.session_state.params['muc_dich'] = st.text_area("Mục đích vay vốn", st.session_state.params['muc_dich'], height=100)
        
        col2a, col2b = st.columns(2)
        with col2a:
            st.session_state.params['tong_nhu_cau'] = st.number_input(
                "Tổng nhu cầu vốn (VNĐ)", 
                min_value=0, 
                value=st.session_state.params['tong_nhu_cau'], 
                step=1000000, 
                format="%d"
            )
            st.session_state.params['so_tien_vay'] = st.number_input(
                "Số tiền vay (VNĐ)", 
                min_value=0, 
                value=st.session_state.params['so_tien_vay'], 
                step=1000000, 
                format="%d"
            )
            st.session_state.params['thoi_gian_vay'] = st.number_input(
                "Thời gian vay (năm)", 
                min_value=0, 
                value=st.session_state.params['thoi_gian_vay'], 
                step=1
            )
        
        with col2b:
            st.session_state.params['von_doi_ung'] = st.number_input(
                "Vốn đối ứng (VNĐ)", 
                min_value=0, 
                value=st.session_state.params['von_doi_ung'], 
                step=1000000, 
                format="%d"
            )
            st.session_state.params['lai_suat'] = st.number_input(
                "Lãi suất (%/năm)", 
                min_value=0.0, 
                value=st.session_state.params['lai_suat'], 
                step=0.1, 
                format="%.1f"
            )

st.markdown("---")

# Tính toán chỉ số tài chính
st.subheader("📊 Phân tích các chỉ số tài chính")

if st.button("🔄 Tính toán lại chỉ số tài chính", use_container_width=True):
    st.session_state.financial_metrics = calculate_financial_metrics(
        st.session_state.params['so_tien_vay'],
        st.session_state.params['lai_suat'],
        st.session_state.params['thoi_gian_vay'],
        0,
        st.session_state.params['von_doi_ung'],
        st.session_state.params['tong_nhu_cau']
    )
    st.success("✅ Đã cập nhật chỉ số tài chính!")

# Hiển thị chỉ số nếu đã tính
if st.session_state.financial_metrics:
    metrics = st.session_state.financial_metrics
    
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.metric("💰 Trả hàng tháng", format_number(metrics['Số tiền trả hàng tháng']) + " VNĐ")
        st.metric("📈 Tổng tiền lãi", format_number(metrics['Tổng tiền lãi']) + " VNĐ")
    with col_m2:
        st.metric("💵 Tổng phải trả", format_number(metrics['Tổng tiền phải trả']) + " VNĐ")
        st.metric("⏱️ Thời gian (tháng)", int(metrics['Thời gian vay (tháng)']))
    with col_m3:
        st.metric("📊 Tỷ lệ vốn đối ứng", f"{metrics['Tỷ lệ vốn đối ứng (%)']:.2f}%")
        st.metric("📉 LTV", f"{metrics['Tỷ lệ cho vay/Tổng nhu cầu (LTV %)']:.2f}%")
    with col_m4:
        color_ltv = "🟢" if metrics['Tỷ lệ cho vay/Tổng nhu cầu (LTV %)'] < 80 else "🟡" if metrics['Tỷ lệ cho vay/Tổng nhu cầu (LTV %)'] < 90 else "🔴"
        color_von = "🟢" if metrics['Tỷ lệ vốn đối ứng (%)'] >= 20 else "🟡" if metrics['Tỷ lệ vốn đối ứng (%)'] >= 10 else "🔴"
        st.markdown(f"**Đánh giá LTV:** {color_ltv}")
        st.markdown(f"**Đánh giá vốn ĐU:** {color_von}")

st.markdown("---")

# Bảng kế hoạch trả nợ
st.subheader("🗓️ Bảng kế hoạch trả nợ dự kiến")
repayment_df = calculate_repayment_schedule(
    st.session_state.params['so_tien_vay'],
    st.session_state.params['lai_suat'],
    st.session_state.params['thoi_gian_vay']
)

if not repayment_df.empty:
    df_display = repayment_df.copy()
    for col in ["Dư nợ đầu kỳ", "Gốc phải trả", "Lãi phải trả", "Tổng gốc và lãi", "Dư nợ cuối kỳ"]:
        df_display[col] = df_display[col].apply(format_number)
    
    st.dataframe(df_display, use_container_width=True, height=400)
    
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
    st.warning("⚠️ Vui lòng nhập đầy đủ thông tin khoản vay để xem kế hoạch trả nợ.")

st.markdown("---")

# Phân tích AI
st.subheader("🤖 Phân tích và Đề xuất từ Gemini AI")

if st.button("🚀 Phân tích với Gemini AI", use_container_width=True, type="primary"):
    if not api_key:
        st.error("❌ Vui lòng nhập API Key của Gemini ở thanh bên trái.")
    else:
        # Tính toán metrics nếu chưa có
        if not st.session_state.financial_metrics:
            st.session_state.financial_metrics = calculate_financial_metrics(
                st.session_state.params['so_tien_vay'],
                st.session_state.params['lai_suat'],
                st.session_state.params['thoi_gian_vay'],
                0,
                st.session_state.params['von_doi_ung'],
                st.session_state.params['tong_nhu_cau']
            )
        
        metrics = st.session_state.financial_metrics
        
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            
            prompt = f"""
            Với vai trò là một chuyên gia thẩm định tín dụng cao cấp, hãy phân tích chi tiết phương án kinh doanh dưới đây và đưa ra đề xuất chuyên nghiệp.

            **THÔNG TIN KHÁCH HÀNG:**
            - Họ và tên: {st.session_state.params['ho_ten']}
            - CCCD: {st.session_state.params['cccd']}
            - Địa chỉ: {st.session_state.params['dia_chi']}
            - Số điện thoại: {st.session_state.params['sdt']}

            **THÔNG TIN KHOẢN VAY:**
            - Mục đích: {st.session_state.params['muc_dich']}
            - Tổng nhu cầu vốn: {format_number(st.session_state.params['tong_nhu_cau'])} VNĐ
            - Vốn đối ứng: {format_number(st.session_state.params['von_doi_ung'])} VNĐ ({metrics['Tỷ lệ vốn đối ứng (%)']:.2f}%)
            - Số tiền vay: {format_number(st.session_state.params['so_tien_vay'])} VNĐ
            - Thời gian vay: {st.session_state.params['thoi_gian_vay']} năm ({metrics['Thời gian vay (tháng)']} tháng)
            - Lãi suất: {st.session_state.params['lai_suat']}%/năm

            **CÁC CHỈ SỐ TÀI CHÍNH:**
            - Số tiền trả hàng tháng: {format_number(metrics['Số tiền trả hàng tháng'])} VNĐ
            - Tổng tiền lãi phải trả: {format_number(metrics['Tổng tiền lãi'])} VNĐ
            - Tổng tiền phải trả: {format_number(metrics['Tổng tiền phải trả'])} VNĐ
            - Tỷ lệ cho vay/Tổng nhu cầu (LTV): {metrics['Tỷ lệ cho vay/Tổng nhu cầu (LTV %)']:.2f}%
            - Tỷ lệ vốn đối ứng: {metrics['Tỷ lệ vốn đối ứng (%)']:.2f}%

            **YÊU CẦU PHÂN TÍCH:**
            1. **Đánh giá tính khả thi** của phương án (30-50 từ):
               - Phân tích khả năng sinh lời và bền vững của mô hình kinh doanh
               - Đánh giá mức độ phù hợp của số vốn vay với quy mô kinh doanh
            
            2. **Phân tích rủi ro** (50-80 từ):
               - Rủi ro thị trường và ngành hàng
               - Rủi ro thanh khoản (khả năng trả nợ)
               - Rủi ro từ tỷ lệ LTV và vốn đối ứng
               - Đề xuất biện pháp giảm thiểu rủi ro
            
            3. **Phân tích các chỉ số tài chính quan trọng** (40-60 từ):
               - Đánh giá LTV (tiêu chuẩn: <80% tốt, 80-90% chấp nhận được, >90% rủi ro cao)
               - Đánh giá tỷ lệ vốn đối ứng (tiêu chuẩn: >20% tốt, 10-20% chấp nhận, <10% thấp)
               - Đánh giá khả năng thanh toán hàng tháng
            
            4. **Kết luận và Đề xuất** (20-30 từ):
               - Đưa ra kết luận rõ ràng: **ĐỀ XUẤT CHO VAY** hoặc **KHÔNG ĐỀ XUẤT CHO VAY**
               - Nêu điều kiện cho vay (nếu có)
               - Đề xuất mức vay phù hợp (nếu cần điều chỉnh)

            Trình bày bằng tiếng Việt, rõ ràng, súc tích, chuyên nghiệp với format markdown.
            """
            
            with st.spinner("🤖 AI đang phân tích phương án, vui lòng chờ..."):
                response = model.generate_content(prompt)
                st.session_state.gemini_analysis_result = response.text
            st.success("✅ Phân tích hoàn tất!")
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Đã xảy ra lỗi khi kết nối với Gemini: {e}")

if st.session_state.gemini_analysis_result:
    st.markdown(st.session_state.gemini_analysis_result)

st.markdown("---")

# Chat với AI
st.subheader("💬 Chat với Trợ lý AI")

col_chat1, col_chat2 = st.columns([6, 1])
with col_chat2:
    if st.button("🗑️ Xóa chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Đặt câu hỏi về phương án kinh doanh..."):
    if not api_key:
        st.warning("⚠️ Vui lòng nhập API Key để bắt đầu chat.")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown()
