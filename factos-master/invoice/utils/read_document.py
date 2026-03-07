import requests
import json
from django.conf import settings
from google import genai


def get_token():
    url = settings.CONFIG_GENAI['AUTH_URL']

    payload = json.dumps({
      "username": settings.CONFIG_GENAI['AUTH_USERNAME'],
      "password": settings.CONFIG_GENAI['AUTH_PASSWORD']
    })
    headers = {
      'Content-Type': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, data=payload)

    if response.status_code == 200:
        data = response.json()
        return data['access']
    else:
        print(f"Error: {response.status_code} - {response.text}")
        return None
    
  
def obtain_best_api_key(access_token, model_name="gemini-2.5-flash-lite"):
    url = f"{settings.CONFIG_GENAI['API_KEY_URL']}?model_name={model_name}"

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data['key'], data['id']
    else:
        print(f"Error: {response.status_code} - {response.text}")
        # Fallback to default API key if service fails
        default_key = settings.CONFIG_GENAI.get('DEFAULT_API_KEY')
        if default_key:
            print("Using default API key as fallback")
            return default_key, 'default'
        return None, None
    

def register_token_usage(access_token, api_key_id, total_token_count):
    url = settings.CONFIG_GENAI['TOKEN_USAGE_URL'].format(api_key_id=api_key_id)

    payload = json.dumps({
        "token_count": total_token_count,
        "used_for": "document_processing"
    })
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(url, headers=headers, data=payload)

        if response.status_code == 201:
            print("Token usage registered successfully.")
        else:
            print(f"Error: {response.status_code} - {response.text}")
    except requests.RequestException as e:
        print(f"Request failed: {e}")


def read_document(pdf_path, prompt, model_name="gemini-2.5-flash-lite"):
    """
    This function retrieves document data by uploading a PDF file to the Google GenAI API
    and processing the response to extract structured JSON data.

    DOC: https://github.com/googleapis/python-genai

    Args:
        pdf_path (str): The path to the PDF file to be processed.
        prompt (str): The prompt to guide the AI in processing the document.

    Returns:
        dict: A dictionary containing the structured data extracted from the document.

    """
    # Get access token always to ensure we have the latest one
    access_token = get_token()
    
    # Obtain the best API key for the given access token
    if access_token:
        api_key, api_key_id = obtain_best_api_key(access_token, model_name=model_name)
    else:
        print("Failed to obtain access token. Using default API key.")
        api_key = settings.CONFIG_GENAI.get('DEFAULT_API_KEY')
        api_key_id = 'default'
    
    if not api_key:
        print("No API key available. Cannot proceed.")
        return None
    
    client = genai.Client(
        api_key=api_key
    )
    print(f"Using API Key ID: {api_key_id}")
    # Example PDF path
    # pdf_path = "/path/9cc76f14bd13e5f4f892eed37522242208d98a90fde884018fee013e031a3d9c8b5616d42a716e2d53539106763b047f.pdf"
    
    file1 = client.files.upload(file=pdf_path)
    
    response = client.models.generate_content(
        model='gemini-2.5-flash-lite',
        contents=[
            prompt,
            file1
        ]
    )

    # JSON is in marked code block with ```json and ``` delimiters
    text_response = response.text

    try:
        json_part = text_response.split('```json')[1].split('```')[0].strip()
        json_data = json.loads(json_part)

        # NOTE: Register the total_token_count
        response_json = json.loads(response.json())
        total_token_count = response_json.get('usage_metadata', {}).get('total_token_count', 0)

        # Only register usage if we have a valid access token and non-default key
        if access_token and api_key_id != 'default':
            register_token_usage(access_token, api_key_id, total_token_count)
        else:
            print(f"Skipping token usage registration (using default key or no access token). Tokens used: {total_token_count}")

    except (IndexError, json.JSONDecodeError) as e:
        print("Error parsing JSON response:", e)
        print("Full response text:", text_response)
        json_data = None
    
    # Clean up the file after processing
    # Note: This is optional, you can keep the file if needed
    client.files.delete(name=file1.name)
            
    return json_data
    

def get_invoice_data(pdf_path):
    """
    This function retrieves invoice data by uploading a PDF file to the Google GenAI API
    and processing the response to extract structured JSON data.

    """
    prompt = """
    Get the next general information of invoice: 
    - Datos del Documento
    The attributes that I want to obtain of the document are:
        - "Código Único de Factura - CUFE"
        - Número de Factura
        - Fecha de Emisión
        - Fecha de Vencimiento
        - Orden de pedido
        
    - Datos del Emisor / Vendedor
    - Datos del Adquiriente / Comprador


    And get the lines of the products with the next attributes:

    The attributes that I want to obtain of the products are:
    - Código
    - Descripción
    - U/M
    - Cantidad
    - Precio unitario
    - Descuento detalle
    - Recargo detalle
    - IVA
    - %_iva
    - INC
    - %_inc
    - Precio unitario de venta


    Give me the response in JSON format with the next structure:
    {
        "general_info": {
            "cufe": "12345678901234567890123456789012345678901234567890",
            "invoice_number": "123456789",
            "issue_date": "2023-10-01",
            "due_date": "2023-10-15",
            "order_number": "PO123456",
        },
        "issuer_info": {
            "name": "Empresa S.A.S.",
            "nit": "123456789",
            "address": "Calle Falsa 123",
            "phone": "+57 123 4567890"
        },
        "buyer_info": {
            "name": "Cliente S.A.S.",
            "nit": "987654321",
            "address": "Avenida Siempre Viva 456",
            "phone": "+57 098 7654321"
        },
        "products": [
            {
                "line": 1,
                "Código": "670753",
                "Descripción": "MOSQUETON-YOKE-N248 G 50KN.",
                "U/M": "94",
                "Cantidad": "3,00",
                "Precio unitario": "44.370,00",
                "Descuento detalle": "0,00",
                "Recargo detalle": "0,00",
                "IVA": "25.291,00",
                "%_iva": "19.00",
                "INC": null,
                "%_inc": null,
                "Precio unitario de venta": "133.110,00"
            },
            {
                "line": 2,
                "Código": "698071",
                "Descripción": "CASCO-ZUBIOLA-TIPO II DIELEC 6 APOY/BARB 4AP O+RACHBLANC(10)",
                "U/M": "94",
                "Cantidad": "3,00",
                "Precio unitario": "49.000,00",
                "Descuento detalle": "0,00",
                "Recargo detalle": "0,00",
                "IVA": "27.930,00",
                "%_iva": "19.00",
                "INC": null,
                "%_inc": null,
                "Precio unitario de venta": "147.000,00"
            }
        ]
    }
    """

    json_data = read_document(
        pdf_path,
        prompt=prompt
    )

    return json_data
