import os
import re
import subprocess
import tempfile

import openpyxl
import requests


def generate_components(texts_list):
    """
    Generates the components for the WhatsApp message.
    Ref: https://developers.facebook.com/docs/whatsapp/api/messages/message-templates/media-message-templates/
    """
    if all(text == "" for text in texts_list):
        return []

    parameters = [{"type": "text", "text": text} for text in texts_list]
    return [{"type": "body", "parameters": parameters}]


def send_whatsapp_message(
    WHATSAPP_PHONE_NUMBER_ID,
    WHATSAPP_ACCESS_TOKEN,
    template_name,
    language_code,
    country_code,
    phone_number,
    components,
):

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
            "language": {"code": language_code},
            "components": components,
        },
    }

    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    return {"status_code": response.status_code, "response": response.text}


def get_message_templates(WHATSAPP_BUSINESS_ACCOUNT_ID, WHATSAPP_ACCESS_TOKEN):
    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_BUSINESS_ACCOUNT_ID}/message_templates"
    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    response_data = response.json()
    response_data = response_data.get("data", [])
    if not response_data:
        return {}
    response_data = {template["name"]: template for template in response_data}
    return response_data


def upload_media(
    WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN, file_bytes, file_type
):
    """
    Uploads a media file to WhatsApp Business API.
    Parameters:
        file_bytes (bytes): The bytes of the file to upload.
        file_type (str): The MIME type of the file.

    Returns:
        str: The ID of the uploaded file.

    Docs: https://developers.facebook.com/docs/whatsapp/cloud-api/reference/media
    """

    # Determine the file extension from the file_type
    if file_type == "image/jpeg" or file_type == "image/jpg":
        file_extension = ".jpeg"
    elif file_type == "image/png":
        file_extension = ".png"
    elif file_type == "video/mp4":
        file_extension = ".mp4"
    elif file_type == "video/3gpp":
        file_extension = ".3gp"
    else:
        raise ValueError("Unsupported file_type")

    # Create a temporary file with the file_bytes
    with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as temp_file:
        temp_file.write(file_bytes)
        file_path = temp_file.name

    # Construct the command
    command = [
        "curl",
        "-X",
        "POST",
        f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_NUMBER_ID}/media",
        "-H",
        f"Authorization: Bearer {WHATSAPP_ACCESS_TOKEN}",
        "-F",
        f'file=@"{file_path}"',
        "-F",
        f'type="{file_type}"',
        "-F",
        'messaging_product="whatsapp"',
    ]

    try:
        # Run the command and capture the output
        completed_process = subprocess.run(command, stdout=subprocess.PIPE, text=True)
    finally:
        # Ensure the temporary file is deleted after the work is done
        os.remove(file_path)

    return completed_process.stdout


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
