import json
import logging
import re
import concurrent.futures

import streamlit as st

from api import (
    excel_to_phone_list,
    generate_components,
    get_message_templates,
    send_whatsapp_message,
    upload_media,
)

# Set up logging
logging.basicConfig(
    filename="logs.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_header_input(header_type: str):
    """Return file uploader for image/video based on header_type."""
    types = {
        "Image": ["jpg", "png", "jpeg"],
        "Video": ["mp4", "3gp"],
    }
    if header_type in types:
        return st.file_uploader(f"Upload {header_type}", type=types[header_type])
    return None


def get_phone_input(message_method: str):
    """Return phone input based on method selection."""
    if message_method == "Phone Number":
        phone = st.text_input("Enter Phone Number")
        if phone and (len(phone) != 10 or not phone.isdigit()):
            st.error("Enter a valid 10-digit phone number")
            return None
        return phone
    elif message_method == "Excel File":
        return st.file_uploader("Upload xlsx file", type=["xlsx"])
    return None


def prepare_media_component(header_input):
    """Upload media and prepare media component for WhatsApp API."""
    if not header_input:
        return None

    media_bytes = header_input.read()
    media_response = upload_media(media_bytes, header_input.type)
    st.write(f"Uploaded media: {media_response}")
    media_id = json.loads(media_response).get("id")

    if header_input.type in ["video/mp4", "video/3gp"]:
        return {
            "type": "header",
            "parameters": [{"type": "video", "video": {"id": media_id}}],
        }
    elif header_input.type in ["image/png", "image/jpeg"]:
        return {
            "type": "header",
            "parameters": [{"type": "image", "image": {"id": media_id}}],
        }
    return None


def send_message(selected_template, language, country_code, phone_number, components, sheet):
    """Send WhatsApp message and return message details."""
    response = send_whatsapp_message(
        template_name=selected_template,
        language=language,
        country_code=country_code,
        phone_number=phone_number,
        components=components,
    )
    return sheet, phone_number, response


def main():
    st.title("WhatsApp Message Sender")

    # Template and header input
    templates = get_message_templates()
    selected_template = st.selectbox("Select Template Name", templates)
    header_type = st.radio("Select Header Type", ["Text", "Image", "Video"])
    header_input = get_header_input(header_type)
    country_code = st.text_input("Enter Country Code", value="91")

    if country_code and not re.fullmatch(r"\d+", country_code):
        st.error("Please enter a valid country code with only digits")
        country_code = None

    # Phone input method
    message_method = st.radio("Select Phone Number Input Method", ["Phone Number", "Excel File"], key="message_method")
    phone_input = get_phone_input(message_method)

    language = st.selectbox("Select Language", ["Hindi", "English_US", "English"])
    num_variables = st.selectbox("Select Number of Variables", list(range(1, 11)))
    variables = [st.text_input(f"Variable {{ {i + 1} }}") for i in range(num_variables)]

    # Show selected inputs
    selected_inputs_md = f"""
    - **Template Name:** {selected_template}
    - **Header Type:** {header_type}
    - **Country Code:** {country_code}
    - **Phone Input Method:** {message_method}
    - **Language:** {language}
    - **Number of Variables:** {num_variables}
    """
    selected_inputs_md += "\n".join(
        [f"- **Variable {{ {i + 1} }}:** {var or ''}" for i, var in enumerate(variables)]
    )
    st.info(selected_inputs_md)

    if st.button("Send Message"):
        # Prepare media component and components list
        media_component = prepare_media_component(header_input)
        components = generate_components(variables)
        if media_component:
            components.insert(0, media_component)

        # Process phone number(s)
        phone_numbers_dict = {}
        if message_method == "Phone Number" and phone_input:
            phone_numbers_dict = {"Single": [phone_input]}
        elif message_method == "Excel File" and phone_input:
            phone_numbers_dict = excel_to_phone_list(phone_input)

        # Flatten dict into list of (sheet, phone_number)
        tasks = [(sheet, phone) for sheet, numbers in phone_numbers_dict.items() for phone in numbers]
        total_tasks = len(tasks)
        total_messages_sent = 0
        progress_placeholder = st.empty()

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
            futures = {
                executor.submit(send_message, selected_template, language, country_code, phone, components, sheet): (sheet, phone)
                for sheet, phone in tasks
            }
            for future in concurrent.futures.as_completed(futures):
                sheet, phone = futures[future]
                try:
                    sheet_ret, phone_ret, response = future.result()
                    response_data = json.loads(response.get("response", "{}"))
                    logger.info(f"{sheet_ret}: {phone_ret} --> {response_data}")
                except Exception as exc:
                    logger.error(f"{sheet}: {phone} generated an exception: {exc}")
                total_messages_sent += 1
                progress_placeholder.write(f"Total messages sent: {total_messages_sent} out of {total_tasks}")


if __name__ == "__main__":
    main()
