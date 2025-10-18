```python
import streamlit as st
import docx
import re
import pandas as pd
import io
from google.generativeai import GenerativeModel, ChatSession
import google.generativeai as genai

# Function to extract information from .docx file
def extract_info_from_docx(file):
    doc = docx.Document(file)
    full_text = "\n".join([para.text for para in doc.paragraphs])
    
    # Extract customer info (assuming patterns; adjust as needed)
    name_pattern = r"(\w+\s+\w+\s+\w+)"  # Placeholder, based on filename or content
    cccd_pattern = r"CCCD:\s*(\d+)"
    address_pattern = r"Địa chỉ:\s*(.+)"
    phone_pattern = r"Số điện thoại:\s*(\d+)"
    
    name = re.search(name_pattern, full_text) or re.search(name_pattern, file.name)  # Fallback to filename
    name = name.group(1) if name else "Không tìm thấy"
    cccd = re.search(cccd_pattern, full_text)
    cccd = cccd.group(1) if cccd else "Không tìm thấy"
    address = re.search(address_pattern, full_text)
    address = address.group(1) if address else "Không tìm thấy"
    phone = re.search(phone_pattern, full_text)
    phone = phone.group(1) if phone else "Không tìm thấy"
    
    # Extract loan info
    purpose = re.search(r"Mục đích vay:\s*(.+)", full_text)
    purpose = purpose.group(1) if purpose else "Không tìm thấy"
    
    total_capital_need = re.search(r"Tổng nhu cầu vốn:\s*(\d+\.?\d*)", full_text)
    total_capital_need = float(total_capital_need.group(1).replace(".", "").replace(",", ".")) if total_capital_need else 0.0
    
    own_capital = re.search(r"Vốn đối ứng:\s*(\d+\.?\d*)", full_text)  # Assuming it's present; else manual
    own_capital = float(own_capital.group(1).replace(".", "").replace(",", ".")) if own_capital else 0.0
    
    loan_amount = re.search(r"Số tiền vay:\s*(\d+\.?\d*)", full_text) or re.search(r"Doanh thu của phương án:\s*(\d+\.?\d*)", full_text)  # Fallback
    loan_amount = float(loan_amount.group(1).replace(".", "").replace(",", ".")) if loan_amount else 0.0
    
    interest_rate = re.search(r"Lãi suất đề nghị:\s*(\d+\.?\d*)%", full_text)
    interest_rate = float(interest_rate.group(1)) / 100 if interest_rate else 0.05  # Default 5%
    
    loan_term_months = re.search(r"Thời hạn cho vay:\s*(\d+)\s*tháng", full_text)
    loan_term_months = int(loan_term_months.group(1)) if loan_term_months else 3
    
    revenue = re.search(r"Doanh thu của phương án:\s*(\d+\.?\d*)", full_text)
    revenue = float(revenue.group(1).replace(".", "").replace(",", ".")) if revenue else 0.0
    
    costs = re.search(r"Chi phí kinh doanh:\s*(\d+\.?\d*)", full_text)
    costs = float(costs.group(1).replace(".", "").replace(",", ".")) if costs else 0.0
    
    profit = revenue - costs
    
    # Calculate financial indicators
    days_per_cycle = re.search(r"Số ngày 1 vòng quay =\s*(\d+)\s*ngày", full_text)
    days_per_cycle = int(days_per_cycle.group(1)) if days_per_cycle else 90
    
    cycles_per_year = 360 / days_per_cycle if days_per_cycle else 4
    
    indicators = {
        "Vòng quay vốn": cycles_per_year,
        "Chênh lệch thu chi": profit
    }
    
    info = {
        "Họ và tên": name,
        "CCCD": cccd,
        "Địa chỉ": address,
        "Số điện thoại": phone,
        "Mục đích vay": purpose,
        "Tổng nhu cầu vốn": total_capital_need,
        "Vốn đối ứng": own_capital,
        "Số tiền vay": loan_amount,
        "Lãi suất": interest_rate * 100,
        "Thời gian vay (tháng)": loan_term_months,
        "Doanh thu": revenue,
        "Chi phí": costs,
        "Lợi nhuận": profit,
        "Chỉ tiêu tài chính": indicators
    }
    
    return info, full_text

# Function to generate repayment schedule
def generate_repayment_schedule(loan_amount, interest_rate, loan_term_months):
    monthly_interest = interest_rate / 12
    monthly_payment = loan_amount * (monthly_interest * (1 + monthly_interest)**loan_term_months) / ((1 + monthly_interest)**loan_term_months - 1)
    
    schedule = []
    balance = loan_amount
    for month in range(1, loan_term_months + 1):
        interest = balance * monthly_interest
        principal = monthly_payment - interest
        balance -= principal
        schedule.append({
            "Tháng": month,
            "Gốc phải trả": principal,
            "Lãi phải trả": interest,
            "Tổng phải trả": monthly_payment,
            "Dư nợ còn lại": balance
        })
    
    df = pd.DataFrame(schedule)
    return df

# Streamlit App with improved UI
st.set_page_config(page_title="Thẩm định Phương án Kinh doanh", layout="wide")
st.markdown(
    """
    <style>
    .main {background-color: #f0f2f6;}
    .stButton>button {background-color: #4CAF50; color: white; border-radius: 5px;}
    .stTextInput, .stNumberInput {border: 1px solid #ddd; border-radius: 5px;}
    .sidebar .sidebar-content {background-color: #ffffff; border-right: 1px solid #ddd;}
    .block-container {padding: 2rem;}
    .stExpander {border: 1px solid #ddd; border-radius: 5px; margin-bottom: 1rem;}
    </style>
    """, unsafe_allow_html=True
)

# Sidebar for API Key and File Upload
with st.sidebar:
    st.header("Cấu hình & Tải file")
    api_key = st.text_input("Nhập API Key cho Gemini:", type="password")
    if api_key:
        genai.configure(api_key=api_key)
    
    uploaded_file = st.file_uploader("Tải file phương án vay vốn (.docx)", type="docx")

# Main content
st.title("📊 Chương trình Thẩm định Phương án Kinh doanh")
st.markdown("---")

if uploaded_file:
    with st.container():
        st.header("📋 Thông tin trích xuất từ hồ sơ")
        info, full_text = extract_info_from_docx(uploaded_file)
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Thông tin khách hàng")
            st.info(f"**Họ và tên**: {info['Họ và tên']}")
            st.info(f"**CCCD**: {info['CCCD']}")
            st.info(f"**Địa chỉ**: {info['Địa chỉ']}")
            st.info(f"**Số điện thoại**: {info['Số điện thoại']}")
        
        with col2:
            st.subheader("Thông tin khoản vay")
            st.info(f"**Mục đích vay**: {info['Mục đích vay']}")
            st.info(f"**Tổng nhu cầu vốn**: {info['Tổng nhu cầu vốn']:,} đồng")
            st.info(f"**Vốn đối ứng**: {info['Vốn đối ứng']:,} đồng")
            st.info(f"**Số tiền vay**: {info['Số tiền vay']:,} đồng")
            st.info(f"**Lãi suất**: {info['Lãi suất']}%/năm")
            st.info(f"**Thời gian vay**: {info['Thời gian vay (tháng)']} tháng")
        
        with st.expander("Chỉ tiêu tài chính"):
            st.write(f"**Doanh thu**: {info['Doanh thu']:,} đồng")
            st.write(f"**Chi phí**: {info['Chi phí']:,} đồng")
            st.write(f"**Lợi nhuận**: {info['Lợi nhuận']:,} đồng")
            st.write(f"**Vòng quay vốn**: {info['Chỉ tiêu tài chính']['Vòng quay vốn']:.2f} vòng/năm")
            st.write(f"**Chênh lệch thu chi**: {info['Chỉ tiêu tài chính']['Chênh lệch thu chi']:,} đồng")
    
    # Manual adjustment section
    with st.container():
        st.header("✏️ Điều chỉnh thông tin (nếu cần)")
        with st.form("manual_adjustment"):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Họ và tên", info["Họ và tên"])
                cccd = st.text_input("CCCD", info["CCCD"])
                address = st.text_input("Địa chỉ", info["Địa chỉ"])
                phone = st.text_input("Số điện thoại", info["Số điện thoại"])
                purpose = st.text_input("Mục đích vay", info["Mục đích vay"])
            
            with col2:
                total_capital = st.number_input("Tổng nhu cầu vốn", value=info["Tổng nhu cầu vốn"])
                own_capital = st.number_input("Vốn đối ứng", value=info["Vốn đối ứng"])
                loan_amount = st.number_input("Số tiền vay", value=info["Số tiền vay"])
                interest_rate = st.number_input("Lãi suất (%)", value=info["Lãi suất"])
                loan_term = st.number_input("Thời gian vay (tháng)", value=info["Thời gian vay (tháng)"])
            
            submit = st.form_submit_button("Cập nhật thông tin")
            if submit:
                info.update({
                    "Họ và tên": name,
                    "CCCD": cccd,
                    "Địa chỉ": address,
                    "Số điện thoại": phone,
                    "Mục đích vay": purpose,
                    "Tổng nhu cầu vốn": total_capital,
                    "Vốn đối ứng": own_capital,
                    "Số tiền vay": loan_amount,
                    "Lãi suất": interest_rate,
                    "Thời gian vay (tháng)": loan_term
                })
                st.success("Thông tin đã được cập nhật!")

    # Repayment schedule
    with st.container():
        st.header("📅 Kế hoạch trả nợ")
        df_schedule = generate_repayment_schedule(info["Số tiền vay"], info["Lãi suất"]/100, info["Thời gian vay (tháng)"])
        st.dataframe(df_schedule.style.format({
            "Gốc phải trả": "{:,.0f}",
            "Lãi phải trả": "{:,.0f}",
            "Tổng phải trả": "{:,.0f}",
            "Dư nợ còn lại": "{:,.0f}"
        }))
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_schedule.to_excel(writer, index=False)
        st.download_button(
            label="📥 Tải xuống bảng kế hoạch trả nợ (Excel)",
            data=output.getvalue(),
            file_name="ke_hoach_tra_no.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    # Gemini Analysis
    if api_key:
        with st.container():
            st.header("🤖 Phân tích bằng Gemini 2.0 Flash")
            with st.expander("Xem phân tích chi tiết"):
                model = GenerativeModel('gemini-2.0-flash')
                prompt = f"Phân tích phương án sử dụng vốn sau và đề xuất cho vay hay không: {full_text}"
                response = model.generate_content(prompt)
                st.markdown(response.text)
                
                rec_prompt = f"Dựa trên phân tích, đề xuất cho vay hay không cho vay? Lý do: {response.text}"
                rec_response = model.generate_content(rec_prompt)
                st.markdown("**Đề xuất**: " + rec_response.text)
    
    # Chatbox with Gemini
    if api_key:
        with st.container():
            st.header("💬 Chat với Gemini 2.0 Flash về phương án")
            if "chat_session" not in st.session_state:
                model = GenerativeModel('gemini-2.0-flash')
                st.session_state.chat_session = model.start_chat(history=[])
            
            with st.expander("Cuộc trò chuyện"):
                for message in st.session_state.chat_session.history:
                    role = "Người dùng" if message.role == "user" else "Gemini"
                    st.write(f"**{role}**: {message.parts[0].text}")
                
                user_input = st.text_input("Hỏi về phương án:", key="chat_input")
                if user_input:
                    response = st.session_state.chat_session.send_message(user_input)
                    st.write(f"**Người dùng**: {user_input}")
                    st.write(f"**Gemini**: {response.text}")
    
    # Export project info
    with st.container():
        st.header("📑 Xuất thông tin dự án")
        export_data = pd.DataFrame(list(info.items()), columns=["Thông tin", "Giá trị"])
        output_export = io.BytesIO()
        with pd.ExcelWriter(output_export, engine='openpyxl') as writer:
            export_data.to_excel(writer, index=False)
        st.download_button(
            label="📥 Tải xuống thông tin dự án (Excel)",
            data=output_export.getvalue(),
            file_name="thong_tin_du_an.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    st.info("Vui lòng tải lên file .docx để bắt đầu thẩm định.")
```
