import concurrent.futures
import json
import logging
import os
import re
import time
from threading import Lock

import pandas as pd
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from dotenv import load_dotenv
from pywa.types.templates import HeaderImage, HeaderVideo
from yaml.loader import SafeLoader

from api import (
    excel_to_phone_list,
    generate_components,
    get_message_templates,
    send_whatsapp_message,
    upload_media,
)

# Page config
st.set_page_config(
    page_title="WhatsApp Sender",
    page_icon="💬",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Custom CSS
st.markdown(
    """
<style>
    /* Main container */
    .stApp {
        background: #ffffff;
    }
    
    /* Headers */
    h1 {
        color: #25D366;
        font-weight: 600 !important;
        margin-bottom: 0.5rem !important;
    }
    
    h4 {
        color: #075E54;
        font-weight: 500 !important;
        margin-top: 1.5rem !important;
        margin-bottom: 0.8rem !important;
    }
    
    /* Input fields */
    .stTextInput input, .stSelectbox select {
        border-radius: 8px !important;
    }
    
    /* Radio buttons */
    .stRadio > label {
        font-weight: 500;
        color: #075E54;
    }
    
    /* File uploader */
    [data-testid="stFileUploader"] {
        border: 2px dashed #25D366;
        border-radius: 8px;
        padding: 1rem;
        background-color: #f0fdf4;
    }
    
    /* Dataframe */
    [data-testid="stDataFrame"] {
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    
    /* Divider */
    hr {
        margin: 1.5rem 0;
        border-color: #E0E0E0;
    }
    
    /* Progress bar */
    .stProgress > div > div {
        background: linear-gradient(90deg, #25D366 0%, #128C7E 100%);
    }
    
    /* Success/Error messages */
    .stSuccess {
        background-color: #d1fae5;
        border-left: 4px solid #25D366;
        border-radius: 6px;
    }
    
    .stError {
        border-left: 4px solid #dc2626;
        border-radius: 6px;
    }
    
    /* Captions */
    .stCaptionContainer {
        color: #6b7280;
    }
    
    /* Cards effect for sections */
    [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] {
        background-color: white;
        border-radius: 12px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
</style>
""",
    unsafe_allow_html=True,
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
    size_limits = {
        "IMAGE": 5,  # MB
        "VIDEO": 16,  # MB
    }
    if header_type in types:
        uploaded_file = st.file_uploader(
            f"Upload {header_type}",
            type=types[header_type],
            help=f"⚠️ WhatsApp limit: Maximum {size_limits[header_type]}MB (Streamlit allows larger files but WhatsApp will reject them)",
        )
        if uploaded_file:
            file_size_mb = uploaded_file.size / (1024 * 1024)
            if file_size_mb > size_limits[header_type]:
                st.error(
                    f"❌ File too large! {file_size_mb:.2f}MB exceeds WhatsApp's {size_limits[header_type]}MB limit. Please compress or use a smaller file."
                )
                return None
            st.success(
                f"✓ File size: {file_size_mb:.2f}MB (Within WhatsApp's {size_limits[header_type]}MB limit)"
            )
        return uploaded_file
    return None


def get_phone_input(message_method: str):
    """Return phone input based on method selection."""
    if message_method == "Phone Number":
        col1, col2 = st.columns([1, 2])
        with col1:
            phone = st.text_input(
                "Phone Number",
                help="Digits only (no spaces, dashes, or special characters)",
            )
            if phone:
                # Check if input contains only digits
                if not phone.isdigit():
                    st.error("❌ Only digits allowed (0-9)")
                    return None
        return phone
    elif message_method == "Excel/CSV File":
        return st.file_uploader("Upload xlsx or csv file", type=["xlsx", "csv"])
    return None


def prepare_media_component(business_name, header_input):
    """Upload media and prepare pywa header params for WhatsApp API."""
    if not header_input:
        return None

    try:
        media_bytes = header_input.read()
        media_response = upload_media(
            BUSINESS_CONFIG[business_name]["WHATSAPP_PHONE_NUMBER_ID"],
            BUSINESS_CONFIG[business_name]["WHATSAPP_ACCESS_TOKEN"],
            media_bytes,
            header_input.type,
        )
        media_id = json.loads(media_response).get("id")
        st.success(f"✅ Media uploaded successfully! ID: `{media_id}`")
    except Exception as e:
        error_msg = str(e)
        if "413" in error_msg or "Payload Too Large" in error_msg:
            st.error(
                "❌ Media upload failed: File is too large. Please use a smaller file (Images: max 5MB, Videos: max 16MB)"
            )
        else:
            st.error(f"❌ Media upload failed: {error_msg}")
        raise

    # Use pywa's native header types
    if header_input.type in ["video/mp4", "video/3gp"]:
        return HeaderVideo.params(video=media_id)
    elif header_input.type in ["image/png", "image/jpeg"]:
        return HeaderImage.params(image=media_id)
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

        # Header with logout
        col1, col2 = st.columns([5, 1])
        with col1:
            st.title(f"💬 WhatsApp Sender - {business_name.upper()}")
        with col2:
            authenticator.logout()

        st.markdown("---")

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

        # Template Selection
        with st.container():
            st.markdown("#### 📋 Select Template")
            selected_template = st.selectbox(
                "Template", template_names, label_visibility="collapsed"
            )

        if selected_template:
            header_type = None
            for component in templates[selected_template]["components"]:
                if component["type"] == "HEADER":
                    header_type = component["format"]
                    break

            language = templates[selected_template]["language"]

            # Media upload if needed
            if header_type and header_type.upper() != "TEXT":
                with st.container():
                    st.markdown("#### 🖼️ Upload Media")
                    header_input = get_header_input(header_type)
                    st.write("")
            else:
                header_input = None

            # Recipients
            with st.container():
                st.markdown("#### 👥 Configure Recipients")
                message_method = st.radio(
                    "Input Method",
                    ["Phone Number", "Excel/CSV File"],
                    key="message_method",
                    horizontal=True,
                )

                # For Excel/CSV, ask if numbers include country code
                excel_has_country_code = False
                if "Excel/CSV" in message_method or "Excel" in message_method:
                    has_cc = st.radio(
                        "Do phone numbers in file include country code?",
                        ["No (10 digits only)", "Yes (country code included)"],
                        key="excel_country_code",
                        horizontal=True,
                    )
                    excel_has_country_code = "Yes" in has_cc

                # Show country code input if needed
                if not excel_has_country_code:
                    col1, col2 = st.columns([1, 3])
                    with col1:
                        country_code = st.text_input(
                            "Country Code",
                            value="91",
                            placeholder="91",
                            help="Digits only",
                        )
                        if country_code:
                            # Check if input contains only digits
                            if not country_code.isdigit():
                                st.error("❌ Only digits allowed (0-9)")
                                country_code = None
                else:
                    country_code = ""

                # Phone input (text box or file uploader)
                clean_method = (
                    "Phone Number" if "Phone" in message_method else "Excel/CSV File"
                )
                phone_input = get_phone_input(clean_method)

            # Variables
            with st.container():
                st.markdown("#### ✏️ Template Variables")
                num_variables = 0
                for component in templates[selected_template]["components"]:
                    if component["type"] == "BODY":
                        num_variables = len(
                            component.get("example", {}).get("body_text", [[]])[0]
                        )
                        break

                variables = []
                if num_variables > 0:
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        for i in range(num_variables):
                            var = st.text_input(f"Variable {i + 1}", key=f"var_{i}")
                            variables.append(var)
                else:
                    st.info("ℹ️ No variables required for this template")

            # Summary table
            with st.container():
                st.markdown("#### 📄 Message Summary")
                summary_rows = [
                    {"Field": "Template", "Value": selected_template},
                    {"Field": "Header", "Value": header_type or "None"},
                    {"Field": "Language", "Value": language},
                    {"Field": "Variables", "Value": str(num_variables)},
                ]
                for i, var in enumerate(variables):
                    summary_rows.append(
                        {"Field": f"Variable {i + 1}", "Value": var or "-"}
                    )

                st.dataframe(
                    pd.DataFrame(summary_rows), hide_index=True, width="stretch"
                )

            st.markdown("---")

            # Send button
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                send_button = st.button(
                    "🚀 Send Messages", type="primary", width="stretch"
                )

            if send_button:
                # If header_type is not TEXT and no media is uploaded, show an error and do not proceed.
                if header_type and header_type.upper() != "TEXT" and not header_input:
                    st.error(
                        "Please upload the required media for the header (image/video) before sending the message."
                    )
                else:
                    # Prepare media header and body params (pywa format)
                    media_component = prepare_media_component(
                        business_name, header_input
                    )
                    body_component = generate_components(variables)

                    # Build params list for pywa
                    components = []
                    if media_component:
                        components.append(media_component)
                    if body_component:
                        components.append(body_component)

                    # Pass None if empty, otherwise pass the list
                    components = components if components else None

                    # Process phone number(s)
                    phone_numbers_dict = {}
                    if "Phone" in message_method and phone_input:
                        phone_numbers_dict = {"Single": [phone_input]}
                    elif (
                        "Excel" in message_method or "CSV" in message_method
                    ) and phone_input:
                        phone_numbers_dict = excel_to_phone_list(phone_input)

                    total_messages_sent = 0
                    total_messages_failed = 0
                    total_tasks = sum(
                        len(phones) for phones in phone_numbers_dict.values()
                    )

                    if total_tasks == 0:
                        st.warning("⚠️ No phone numbers to send messages to.")
                        return

                    # Progress UI
                    progress_bar = st.progress(0)
                    progress_text = st.empty()
                    failed_numbers = []

                    def send_message_task(phone_number, max_retries=2):
                        """Send message with retry logic for transient errors."""
                        import time

                        for attempt in range(max_retries + 1):
                            try:
                                response = send_whatsapp_message(
                                    BUSINESS_CONFIG[business_name][
                                        "WHATSAPP_PHONE_NUMBER_ID"
                                    ],
                                    BUSINESS_CONFIG[business_name][
                                        "WHATSAPP_ACCESS_TOKEN"
                                    ],
                                    template_name=selected_template,
                                    language_code=language,
                                    country_code=country_code,
                                    phone_number=phone_number,
                                    components=components,
                                )
                                response_data = json.loads(response["response"])

                                # Check if response contains an error
                                if "error" in response_data:
                                    error_details = response_data["error"]
                                    error_code = error_details.get("code", 0)
                                    error_message = error_details.get(
                                        "message", "Unknown error"
                                    )

                                    # Retry on rate limit (code 4 or 80007) or server errors (code >= 500)
                                    if attempt < max_retries and (
                                        error_code in [4, 80007] or error_code >= 500
                                    ):
                                        wait_time = (
                                            2**attempt
                                        ) * 0.5  # Exponential backoff: 0.5s, 1s
                                        time.sleep(wait_time)
                                        continue

                                    logger.error(
                                        f"API error for {phone_number}: {error_message} (Code: {error_code})"
                                    )
                                    return {
                                        "success": False,
                                        "phone": phone_number,
                                        "error": f"{error_message} (Code: {error_code})",
                                    }

                                logger.info(f"Message sent to {phone_number}")
                                return {"success": True, "phone": phone_number}

                            except Exception as e:
                                # Retry on network/connection errors
                                if attempt < max_retries:
                                    wait_time = (2**attempt) * 0.5
                                    time.sleep(wait_time)
                                    continue

                                error_msg = (
                                    f"Failed to send to {phone_number}: {str(e)}"
                                )
                                logger.error(error_msg)
                                return {
                                    "success": False,
                                    "phone": phone_number,
                                    "error": str(e),
                                }

                        return {
                            "success": False,
                            "phone": phone_number,
                            "error": "Max retries exceeded",
                        }

                    # Meta WhatsApp Cloud API rate limits:
                    # - 80 messages per second
                    # - 1000 messages per hour per phone number
                    # Using 80 workers to maximize throughput while respecting rate limits
                    rate_limiter = {"last_batch_time": time.time(), "count": 0}
                    rate_lock = Lock()

                    def rate_limited_send(phone_number):
                        """Send message with rate limiting (80 msg/sec)."""
                        with rate_lock:
                            rate_limiter["count"] += 1
                            # Every 80 messages, ensure at least 1 second has passed
                            if rate_limiter["count"] >= 80:
                                elapsed = time.time() - rate_limiter["last_batch_time"]
                                if elapsed < 1.0:
                                    time.sleep(1.0 - elapsed)
                                rate_limiter["last_batch_time"] = time.time()
                                rate_limiter["count"] = 0

                        return send_message_task(phone_number)

                    with concurrent.futures.ThreadPoolExecutor(
                        max_workers=80  # Match Meta's 80 msg/sec limit
                    ) as executor:
                        futures = []
                        for sheet, phone_list in phone_numbers_dict.items():
                            for phone_number in phone_list:
                                futures.append(
                                    executor.submit(rate_limited_send, phone_number)
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

                            # Update progress with counter
                            completed = total_messages_sent + total_messages_failed
                            progress = completed / total_tasks
                            progress_bar.progress(progress)
                            progress_text.markdown(
                                f"**Progress:** {completed}/{total_tasks} | ✅ Sent: {total_messages_sent} | ❌ Failed: {total_messages_failed}"
                            )

                    # Final results
                    progress_bar.progress(1.0)

                    if total_messages_failed == 0:
                        st.success(f"✅ All {total_messages_sent} messages sent!")
                    elif total_messages_sent == 0:
                        st.error(f"❌ All {total_tasks} messages failed.")
                    else:
                        st.warning(
                            f"✅ Sent: {total_messages_sent} | ❌ Failed: {total_messages_failed}"
                        )

                    # Show failed numbers in table
                    if failed_numbers:
                        st.markdown("---")
                        st.markdown(f"### ❌ Failed Numbers ({len(failed_numbers)})")

                        df = pd.DataFrame(failed_numbers, columns=["phone", "error"])
                        df.columns = ["Phone Number", "Error Message"]
                        df.index = range(1, len(df) + 1)
                        st.dataframe(df, width="stretch")

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
                            width="stretch",
                        )
    elif st.session_state["authentication_status"] is False:
        st.error("❌ Username/password is incorrect")
    elif st.session_state["authentication_status"] is None:
        st.markdown("### 🔐 Login")
        st.info("Please enter your username and password to continue.")


if __name__ == "__main__":
    main()
