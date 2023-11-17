import json
import logging
import re

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


# Function to get user inputs based on selected header type
def get_header_input(header_type):
    if header_type == "Image":
        return st.file_uploader("Upload Image", type=["jpg", "png", "jpeg"])
    elif header_type == "Video":
        return st.file_uploader("Upload Video", type=["mp4", "3gp"])
    else:
        return None


def get_phone_input(message_method):
    if message_method == "Phone Number":
        phone_number = st.text_input("Enter Phone Number")
        if len(phone_number) != 10 or not phone_number.isdigit():
            st.error("Please enter a valid 10 digit phone number")
            return None
        return phone_number
    elif message_method == "Excel File":
        return st.file_uploader("Upload xlsx file", type=["xlsx"])


# Streamlit App
st.title("WhatsApp Message Sender")

# Input fields
all_templates = get_message_templates()
selected_template = st.selectbox("Select Template Name", all_templates)

# Header selection
header_type = st.radio("Select Header Type", ["Text", "Image", "Video"])
header_input = get_header_input(header_type)
country_code = st.text_input("Enter Country Code", value="91")

if not re.match("^[0-9]+$", country_code):
    st.error("Please enter a valid country code with only digits")
    country_code = None

# Message method selection
phone_method = st.radio(
    "Select Phone Number Input Method",
    ["Phone Number", "Excel File"],
    key="message_method",
)
phone_method_input = get_phone_input(phone_method)


language = st.selectbox("Select Language", ["Hindi", "English"])

# Variables dropdown menu
num_variables = st.selectbox("Select Number of Variables", list(range(1, 11)))

# Gather user inputs for variables
variables = [st.text_input(f"Variable {{ {i + 1} }}") for i in range(num_variables)]

# Display the selected inputs in a nice box
st.markdown("### Selected Inputs")
selected_inputs = f"""
- **Template Name:** {selected_template}
- **Header Type:** {header_type}
- **Country Code:** {country_code}
- **Phone Method:** {phone_method}
- **Language:** {language}
- **Number of Variables:** {num_variables}
"""
selected_inputs += "\n".join(
    [f"- **Variable {{ {i + 1} }}:** {variables[i]}" for i in range(num_variables)]
)
st.info(selected_inputs)

# Submit button
if st.button("Send Message"):
    media_component = None
    if header_input is not None:
        media_content = upload_media(header_input.read(), header_input.type)
        st.write(f"Uploaded media: {media_content}")
        media_id = json.loads(media_content)["id"]
        if header_input.type == "video/mp4" or header_input.type == "video/3gp":
            media_component = {
                "type": "header",
                "parameters": [
                    {
                        "type": "video",
                        "video": {"id": media_id},
                    }
                ],
            }
        elif header_input.type == "image/png" or header_input.type == "image/jpeg":
            media_component = {
                "type": "header",
                "parameters": [{"type": "image", "image": {"id": media_id}}],
            }

    components = generate_components(variables)
    if media_component:
        components.insert(0, media_component)

    if phone_method == "Phone Number":
        phone_numbers_dict = {"phone_number": [phone_method_input]}
    elif phone_method == "Excel File":
        phone_numbers_dict = excel_to_phone_list(phone_method_input)

    # st.write(phone_numbers_dict)
    total_messages_sent = 0
    for sheet, phone_list in phone_numbers_dict.items():
        for phone_number in phone_list:

            response = send_whatsapp_message(
                template_name=selected_template,
                language=language,
                country_code=country_code,
                phone_number=phone_number,
                components=components,
            )
            response_data = json.loads(response["response"])
            logger.info(f"{sheet}: {phone_number} --> {response_data}")

            total_messages_sent += 1
            with st.empty():
                st.write(f"Total messages sent: {total_messages_sent}")
