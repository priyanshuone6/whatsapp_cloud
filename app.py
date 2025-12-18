import concurrent.futures
import json
import logging
import os
import re

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from dotenv import load_dotenv
from yaml.loader import SafeLoader

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

load_dotenv()

BUSINESS_CONFIG = {
    "arena": {
        "WHATSAPP_ACCESS_TOKEN": os.getenv("ARENA_WHATSAPP_ACCESS_TOKEN"),
        "WHATSAPP_PHONE_NUMBER_ID": os.getenv("ARENA_WHATSAPP_PHONE_NUMBER_ID"),
        "WHATSAPP_BUSINESS_ACCOUNT_ID": os.getenv("ARENA_WHATSAPP_BUSINESS_ACCOUNT_ID"),
        "WHATSAPP_APP_ID": os.getenv("ARENA_WHATSAPP_APP_ID"),
    },
    "nexa": {
        "WHATSAPP_ACCESS_TOKEN": os.getenv("NEXA_WHATSAPP_ACCESS_TOKEN"),
        "WHATSAPP_PHONE_NUMBER_ID": os.getenv("NEXA_WHATSAPP_PHONE_NUMBER_ID"),
        "WHATSAPP_BUSINESS_ACCOUNT_ID": os.getenv("NEXA_WHATSAPP_BUSINESS_ACCOUNT_ID"),
        "WHATSAPP_APP_ID": os.getenv("NEXA_WHATSAPP_APP_ID"),
    },
    "rasto": {
        "WHATSAPP_ACCESS_TOKEN": os.getenv("RASTO_WHATSAPP_ACCESS_TOKEN"),
        "WHATSAPP_PHONE_NUMBER_ID": os.getenv("RASTO_WHATSAPP_PHONE_NUMBER_ID"),
        "WHATSAPP_BUSINESS_ACCOUNT_ID": os.getenv("RASTO_WHATSAPP_BUSINESS_ACCOUNT_ID"),
        "WHATSAPP_APP_ID": os.getenv("RASTO_WHATSAPP_APP_ID"),
    },
}


def get_header_input(header_type: str):
    """Return file uploader for image/video based on header_type."""
    types = {
        "IMAGE": ["jpg", "png", "jpeg"],
        "VIDEO": ["mp4", "3gp"],
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


def prepare_media_component(business_name, header_input):
    """Upload media and prepare media component for WhatsApp API."""
    if not header_input:
        return None

    media_bytes = header_input.read()
    media_response = upload_media(
        BUSINESS_CONFIG[business_name]["WHATSAPP_PHONE_NUMBER_ID"],
        BUSINESS_CONFIG[business_name]["WHATSAPP_ACCESS_TOKEN"],
        media_bytes,
        header_input.type,
    )
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


def main():
    with open("config.yaml") as file:
        config = yaml.load(file, Loader=SafeLoader)

    authenticator = stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
    )

    try:
        authenticator.login()
    except Exception as e:
        st.error(e)

    if st.session_state["authentication_status"]:
        business_name = st.session_state["name"]

        authenticator.logout()

        st.title("WhatsApp Message Sender - " + business_name.upper())
        # Template and header input
        try:
            templates = get_message_templates(
                BUSINESS_CONFIG[business_name]["WHATSAPP_BUSINESS_ACCOUNT_ID"],
                BUSINESS_CONFIG[business_name]["WHATSAPP_ACCESS_TOKEN"],
            )
            template_names = list(templates.keys())
        except Exception as e:
            st.error(f"⚠️ Failed to load templates: {str(e)}")
            st.info(
                "Please verify:\n- Access token is valid and not expired\n- Token has required permissions\n- Business Account ID is correct"
            )
            return
        selected_template = st.selectbox("Select Template Name", template_names)

        if selected_template:
            header_type = None
            for component in templates[selected_template]["components"]:
                if component["type"] == "HEADER":
                    header_type = component["format"]
                    break

            st.write("Header Type: ", header_type)

            header_input = get_header_input(header_type)
            country_code = st.text_input("Enter Country Code", value="91")

            if country_code and not re.fullmatch(r"\d+", country_code):
                st.error("Please enter a valid country code with only digits")
                country_code = None

            # Phone input method
            message_method = st.radio(
                "Select Phone Number Input Method",
                ["Phone Number", "Excel File"],
                key="message_method",
            )
            phone_input = get_phone_input(message_method)

            language = templates[selected_template]["language"]
            st.write("Language: ", language)

            num_variables = 0
            for component in templates[selected_template]["components"]:
                if component["type"] == "BODY":
                    num_variables = len(
                        component.get("example", {}).get("body_text", [[]])[0]
                    )
                    break
            st.write("Number of Variables: ", num_variables)

            # Create text inputs for variables
            variables = [
                st.text_input(f"Variable {{ {i + 1} }}") for i in range(num_variables)
            ]

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
                [
                    f"- **Variable {{ {i + 1} }}:** {var or ''}"
                    for i, var in enumerate(variables)
                ]
            )
            st.info(selected_inputs_md)

            if st.button("Send Message"):
                # If header_type is not TEXT and no media is uploaded, show an error and do not proceed.
                if header_type and header_type.upper() != "TEXT" and not header_input:
                    st.error(
                        "Please upload the required media for the header (image/video) before sending the message."
                    )
                else:
                    # Prepare media component and components list
                    media_component = prepare_media_component(
                        business_name, header_input
                    )
                    components = generate_components(variables)
                    if media_component:
                        components.insert(0, media_component)

                    # Process phone number(s)
                    phone_numbers_dict = {}
                    if message_method == "Phone Number" and phone_input:
                        phone_numbers_dict = {"Single": [phone_input]}
                    elif message_method == "Excel File" and phone_input:
                        phone_numbers_dict = excel_to_phone_list(phone_input)

                    total_messages_sent = 0
                    total_messages_failed = 0
                    total_tasks = sum(
                        len(phones) for phones in phone_numbers_dict.values()
                    )
                    progress_placeholder = st.empty()
                    failed_numbers = []

                    def send_message_task(phone_number):
                        try:
                            response = send_whatsapp_message(
                                BUSINESS_CONFIG[business_name][
                                    "WHATSAPP_PHONE_NUMBER_ID"
                                ],
                                BUSINESS_CONFIG[business_name]["WHATSAPP_ACCESS_TOKEN"],
                                template_name=selected_template,
                                language_code=language,
                                country_code=country_code,
                                phone_number=phone_number,
                                components=components,
                            )
                            response_data = json.loads(response["response"])
                            logger.info(f"Message sent successfully to {phone_number}")
                            return {"success": True, "phone": phone_number}
                        except Exception as e:
                            error_msg = f"Failed to send to {phone_number}: {str(e)}"
                            logger.error(error_msg)
                            return {
                                "success": False,
                                "phone": phone_number,
                                "error": str(e),
                            }

                    with concurrent.futures.ThreadPoolExecutor(
                        max_workers=50
                    ) as executor:
                        futures = []
                        for sheet, phone_list in phone_numbers_dict.items():
                            for phone_number in phone_list:
                                futures.append(
                                    executor.submit(send_message_task, phone_number)
                                )
                        for future in concurrent.futures.as_completed(futures):
                            result = future.result()
                            if result["success"]:
                                total_messages_sent += 1
                            else:
                                total_messages_failed += 1
                                failed_numbers.append(
                                    {"phone": result["phone"], "error": result["error"]}
                                )

                            progress_placeholder.write(
                                f"✅ Sent: {total_messages_sent} | ❌ Failed: {total_messages_failed} | Total: {total_tasks}"
                            )

                    # Display final summary
                    st.success(
                        f"**Completed!** ✅ Sent: {total_messages_sent} | ❌ Failed: {total_messages_failed}"
                    )

                    # Show failed numbers in expandable section
                    if failed_numbers:
                        with st.expander(
                            f"❌ View {len(failed_numbers)} Failed Numbers",
                            expanded=False,
                        ):
                            # Create table with two columns
                            import pandas as pd

                            df = pd.DataFrame(
                                failed_numbers, columns=["phone", "error"]
                            )
                            df.columns = ["Phone Number", "Error Message"]
                            df.index = range(1, len(df) + 1)
                            st.dataframe(df, use_container_width=True)

                            # Create downloadable list
                            failed_list = "\n".join(
                                [
                                    f"{i}. {f['phone']} - {f['error']}"
                                    for i, f in enumerate(failed_numbers, 1)
                                ]
                            )
                            st.download_button(
                                label="📥 Download Failed Numbers",
                                data=failed_list,
                                file_name=f"failed_numbers_{selected_template}.txt",
                                mime="text/plain",
                            )
    elif st.session_state["authentication_status"] is False:
        st.error("Username/password is incorrect")
    elif st.session_state["authentication_status"] is None:
        st.warning("Please enter your username and password")


if __name__ == "__main__":
    main()
