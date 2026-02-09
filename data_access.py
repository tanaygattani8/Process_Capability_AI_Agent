
from promptflow import tool
from azure.storage.blob import BlobServiceClient
import pandas as pd
import io

@tool
def data_access_tool(
    account_name: str,
    account_key: str,
    container_name: str,
    blob_name: str
) -> str:
    """
    Rapid prototype: Download a CSV file from Azure Blob Storage and return its contents as JSON records (string).
    Authentication: Uses storage account key.
    Input: CSV blob in Azure Storage.
    Output: JSON array of records (string) for downstream processing.
    """

    # Step 1: Build the account URL and create a BlobServiceClient using the account key
    account_url = f"https://{account_name}.blob.core.windows.net"
    blob_service_client = BlobServiceClient(account_url=account_url, credential=account_key)

    # Step 2: Get a BlobClient for the specified container and blob, then download the blob's content as bytes
    blob_client = blob_service_client.get_container_client(container_name).get_blob_client(blob_name)
    data = blob_client.download_blob().readall()

    # Step 3: Load the downloaded bytes into a pandas DataFrame
    # Using utf-8-sig encoding to handle potential BOM in CSV files
    df = pd.read_csv(io.BytesIO(data), encoding="utf-8-sig")

    # Step 4: Convert the DataFrame to a JSON string in "records" format (list of dictionaries)
    return df.to_json(orient="records")
