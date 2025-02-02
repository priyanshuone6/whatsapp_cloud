import json
import os
import re
import tempfile

import dotenv
import openpyxl
import requests

dotenv.load_dotenv()
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")

LANGUAGE_CODES = {
    "English_US": "en_US",
    "Hindi": "hi",
    "English": "en",
}


def generate_components(texts_list):
    """
    Generates the components for the WhatsApp message.
    Ref: https://developers.facebook.com/docs/whatsapp/api/messages/message-templates/media-message-templates/
    """
    if all(text == "" for text in texts_list):
        return []

    parameters = [{"type": "text", "text": text} for text in texts_list]
    return [{"type": "body", "parameters": parameters}]


def send_whatsapp_message(template_name, language, country_code, phone_number, components):
    code = LANGUAGE_CODES.get(language)
    if not code:
        raise ValueError(f"Unsupported language: {language}")

    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": f"{country_code}{phone_number}",
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": code},
            "components": components,
        },
    }

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    return {"status_code": response.status_code, "response": response.text}


def get_message_templates():
    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_BUSINESS_ACCOUNT_ID}/message_templates"
    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    response_data = response.json()
    names = [item["name"] for item in response_data.get("data", [])]
    return names


def upload_media(file_bytes, file_type):
    """
    Uploads a media file to WhatsApp Business API.
    Parameters:
        file_bytes (bytes): The bytes of the file to upload.
        file_type (str): The MIME type of the file.
    Returns:
        str: The response text from the API.
    Docs: https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media
    """
    EXTENSIONS = {
        "image/jpeg": ".jpeg",
        "image/jpg": ".jpeg",
        "image/png": ".png",
        "video/mp4": ".mp4",
        "video/3gpp": ".3gp",
    }
    file_extension = EXTENSIONS.get(file_type)
    if not file_extension:
        raise ValueError("Unsupported file_type")

    url = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_NUMBER_ID}/media"
    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
    data = {"messaging_product": "whatsapp", "type": file_type}

    # Use a temporary file to name the file correctly
    with tempfile.NamedTemporaryFile(suffix=file_extension) as temp_file:
        temp_file.write(file_bytes)
        temp_file.flush()  # Ensure data is written
        with open(temp_file.name, "rb") as f:
            files = {"file": (os.path.basename(temp_file.name), f, file_type)}
            response = requests.post(url, headers=headers, files=files, data=data)
            response.raise_for_status()
            return response.text


def excel_to_phone_list(file_path):
    """
    Extracts mobile numbers from all sheets in an Excel file.
    Returns: {sheet_name: [mobile_numbers]}
    """
    result = {}
    mobile_number_pattern = re.compile(r"(mobile|phone|cell|tel|contact)", re.I)
    valid_number_pattern = re.compile(r"^\d{10}$")  # exactly 10 digits

    wb = openpyxl.load_workbook(file_path)
    for sheet in wb.worksheets:
        for column in sheet.iter_cols(min_row=1, max_row=sheet.max_row):
            header = column[0].value
            if header and mobile_number_pattern.search(str(header)):
                mobile_numbers = [
                    str(cell.value).strip()
                    for cell in column[1:]
                    if cell.value and valid_number_pattern.match(str(cell.value))
                ]
                result[sheet.title] = mobile_numbers
    return result
