from promptflow import tool
from azure.storage.blob import BlobServiceClient, ContentSettings
import os
import uuid

# The inputs section will change based on the arguments of the tool function, after you save the code
# Adding type to arguments and return value will help the system show the types properly
# Please update the function name/signature per need
@tool
def reportwriter(account_name: str,
    account_key: str,
    container_name: str,
    blob_name: str, 
    html_content: str) -> str:

    container_name = container_name + "-output"

    # Ensure blob name has .html extension and add unique GUID
    base_name = blob_name.replace('.html', '') if blob_name.endswith('.html') else blob_name
    blob_name = f"{base_name}-{uuid.uuid4()}.html"
    
    # Create account URL
    account_url = f"https://{account_name}.blob.core.windows.net"
    
    # Create BlobServiceClient using account key
    blob_service_client = BlobServiceClient(
        account_url=account_url,
        credential=account_key
    )
    
    # Get container client and create if it doesn't exist
    container_client = blob_service_client.get_container_client(container_name)
    if not container_client.exists():
        container_client.create_container(public_access="blob")
        print(f"Created container: {container_name}")
    
    # Get blob client
    blob_client = blob_service_client.get_blob_client(
        container=container_name,
        blob=blob_name
    )
    

    # Set content settings for HTML
    content_settings = ContentSettings(content_type="text/html")
    
    # Upload the HTML content
    blob_client.upload_blob(
        html_content,
        overwrite=True,
        content_settings=content_settings
    )
    
    return blob_client.url