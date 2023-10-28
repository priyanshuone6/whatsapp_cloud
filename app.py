import json

import streamlit as st

from api import (
    generate_components,
    get_message_templates,
    send_whatsapp_message,
    upload_media,
)


# Function to get user inputs based on selected header type
def get_user_input(header_type):
    if header_type == "Image":
        return st.file_uploader("Upload Image", type=["jpg", "png", "jpeg"])


# Streamlit App
st.title("WhatsApp Bulk Message Sender")

st.markdown(
    """<style>[class="st-emotion-cache-76z9jo e116k4er2"]{display: none;}""",
    unsafe_allow_html=True,
)

# Input fields
all_templates = get_message_templates()
template_name = st.selectbox("Select Template Name", all_templates)

# Header selection
header_type = st.radio("Select Template Header Type", ["Text", "Image"])

# Get user inputs based on header selection
user_inputs = get_user_input(header_type)
country_code = st.number_input("Enter Country Code", value=91)
phone_number = st.number_input("Enter Phone Number", value=0)
language = st.selectbox("Select Language", ["Hindi", "English"])

# Variables dropdown menu
num_variables = st.selectbox("Select Number of Variables", list(range(1, 11)))

# Gather user inputs for variables
variables = [st.text_input(f"Variable {{ {i + 1} }}") for i in range(num_variables)]

# Display the selected inputs in a nice box
st.markdown("### Selected Inputs")
selected_inputs = f"""
- **Template Name:** {template_name}
- **Header Type:** {header_type}
- **Country Code:** {country_code}
- **Phone Number:** {phone_number}
- **Language:** {language}
- **Number of Variables:** {num_variables}
"""
selected_inputs += "\n".join(
    [f"- **Variable {{ {i + 1} }}:** {variables[i]}" for i in range(num_variables)]
)
st.info(selected_inputs)

# Submit button
if st.button("Send Message"):
    image_component = None
    if user_inputs is not None:
        stdout = upload_media(user_inputs.read(), user_inputs.type)
        image_id = json.loads(stdout)["id"]
        image_component = {
            "type": "header",
            "parameters": [{"type": "image", "image": {"id": image_id}}],
        }

    component = generate_components(variables)
    if image_component:
        component.insert(0, image_component)

    response = send_whatsapp_message(
        template_name=template_name,
        language=language,
        country_code=country_code,
        phone_number=phone_number,
        components=component,
    )
    data = json.loads(response["response"])
    st.write(data)
