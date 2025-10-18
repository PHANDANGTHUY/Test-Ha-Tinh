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
        "Chênh lệch thu chi": profit,
        # Add more as needed
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

# Streamlit App
st.title("Chương trình Thẩm định Phương án Kinh doanh")

# API Key input
api_key = st.text_input("Nhập API Key cho Gemini:", type="password")
if api_key:
    genai.configure(api_key=api_key)

# Upload file
uploaded_file = st.file_uploader("Upload file phương án vay vốn (.docx)", type="docx")

if uploaded_file:
    info, full_text = extract_info_from_docx(uploaded_file)
    
    # Display extracted info
    st.subheader("Thông tin trích xuất")
    for key, value in info.items():
        if isinstance(value, dict):
            st.write(f"{key}:")
            for subkey, subvalue in value.items():
                st.write(f"  - {subkey}: {subvalue}")
        else:
            st.write(f"{key}: {value}")
    
    # Manual adjustment
    st.subheader("Điều chỉnh thủ công (nếu cần)")
    info["Họ và tên"] = st.text_input("Họ và tên", info["Họ và tên"])
    info["CCCD"] = st.text_input("CCCD", info["CCCD"])
    info["Địa chỉ"] = st.text_input("Địa chỉ", info["Địa chỉ"])
    info["Số điện thoại"] = st.text_input("Số điện thoại", info["Số điện thoại"])
    info["Mục đích vay"] = st.text_input("Mục đích vay", info["Mục đích vay"])
    info["Tổng nhu cầu vốn"] = st.number_input("Tổng nhu cầu vốn", value=info["Tổng nhu cầu vốn"])
    info["Vốn đối ứng"] = st.number_input("Vốn đối ứng", value=info["Vốn đối ứng"])
    info["Số tiền vay"] = st.number_input("Số tiền vay", value=info["Số tiền vay"])
    info["Lãi suất"] = st.number_input("Lãi suất (%)", value=info["Lãi suất"])
    info["Thời gian vay (tháng)"] = st.number_input("Thời gian vay (tháng)", value=info["Thời gian vay (tháng)"])
    
    # Repayment schedule
    st.subheader("Kế hoạch trả nợ")
    df_schedule = generate_repayment_schedule(info["Số tiền vay"], info["Lãi suất"]/100, info["Thời gian vay (tháng)"])
    st.dataframe(df_schedule)
    
    # Download Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_schedule.to_excel(writer, index=False)
    st.download_button("Tải xuống bảng kế hoạch trả nợ (Excel)", output.getvalue(), file_name="ke_hoach_tra_no.xlsx")
    
    # Gemini Analysis
    if api_key:
        st.subheader("Phân tích bằng Gemini")
        model = GenerativeModel('gemini-1.5-flash')
        prompt = f"Phân tích phương án sử dụng vốn sau và đề xuất cho vay hay không: {full_text}"
        response = model.generate_content(prompt)
        st.write(response.text)
        
        # Recommendation
        rec_prompt = f"Dựa trên phân tích, đề xuất cho vay hay không cho vay? Lý do: {response.text}"
        rec_response = model.generate_content(rec_prompt)
        st.write(rec_response.text)
    
    # Chatbox with Gemini
    st.subheader("Chat với Gemini về phương án")
    if "chat_session" not in st.session_state and api_key:
        model = GenerativeModel('gemini-1.5-flash')
        st.session_state.chat_session = model.start_chat(history=[])
    
    if "chat_session" in st.session_state:
        user_input = st.chat_input("Hỏi về phương án:")
        if user_input:
            response = st.session_state.chat_session.send_message(user_input)
            st.chat_message("user").write(user_input)
            st.chat_message("assistant").write(response.text)
    
    # Export info
    st.subheader("Xuất thông tin dự án và kết quả phân tích")
    export_data = pd.DataFrame(list(info.items()), columns=["Thông tin", "Giá trị"])
    output_export = io.BytesIO()
    with pd.ExcelWriter(output_export, engine='openpyxl') as writer:
        export_data.to_excel(writer, index=False)
    st.download_button("Tải xuống thông tin dự án (Excel)", output_export.getvalue(), file_name="thong_tin_du_an.xlsx")