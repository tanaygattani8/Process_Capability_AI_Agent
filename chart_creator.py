
from promptflow import tool
from dotenv import load_dotenv

import os
import time
import re

from azure.identity import ClientSecretCredential
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    McpTool,
    ToolSet,
    ListSortOrder,
    MessageRole,
    MessageTextContent,
)

# ---------------------------------------------------------------------------
# Configuration: load environment variables from a local .env file
# Keep secrets out of source; use environment configuration wherever possible.
# ---------------------------------------------------------------------------
dotenv_path = './config.env'
load_dotenv(dotenv_path=dotenv_path)

project_endpoint = os.environ.get("PROJECT_ENDPOINT")
model_deployment = os.environ.get("MODEL_DEPLOYMENT_NAME")
api_key = os.environ.get("API_KEY")  # If you prefer key-based auth (not used below)

# Azure AD app credentials (client credentials flow)
tenant_id = os.environ.get("AZURE_TENANT_ID")
client_id = os.environ.get("AZURE_CLIENT_ID")
client_secret = os.environ.get("AZURE_CLIENT_SECRET")

# ---------------------------------------------------------------------------
# ⚠ SECURITY NOTE:
# The hardcoded values below expose secrets in source code. Remove them and rely
# on environment variables or Azure Key Vault. Committing hardcoded secrets is unsafe.
# ---------------------------------------------------------------------------
tenant_id = "2ca68321-0eda-4908-88b2-424a8cb4b0f9"
client_id = "5253f3fa-15bd-42a4-94a3-9eba4d19379e"
client_secret = "lSl8Q~5QHfpbe0UESlzotw_UkbcMzUemm3DZibth"

# Build an AAD credential used by AgentsClient
credential = ClientSecretCredential(
    tenant_id=tenant_id,
    client_id=client_id,
    client_secret=client_secret
)

# ---------------------------------------------------------------------------
# Helper: extract the first http(s) URL from freeform text
# Useful when the agent returns extra text around the URL.
# ---------------------------------------------------------------------------
def _extract_first_url(text: str) -> str | None:
    """
    Extract the first http(s) URL from text, trimming trailing punctuation.
    """
    if not text:
        return None
    m = re.search(r"(https?://\S+)", text)
    if not m:
        return None
    return m.group(1).rstrip(").,]")  # strip common trailing characters


# ---------------------------------------------------------------------------
# Prompt Flow Tool: Generate SPC chart via MCP tool and return ONLY the chart URL
# ---------------------------------------------------------------------------
@tool
def chart(I_ChartDataPoints: str) -> str:
    """
    Calls the MCP chart service through an Azure Agent and returns ONLY the URL
    of the generated statistical process control (SPC) chart.

    Input:
        I_ChartDataPoints: str -> data points to plot (e.g., comma-separated numbers or JSON)

    Output:
        str -> the chart URL, or an "ERROR: ..." message if generation fails.
    """

    # Create the Azure AI Agents client (project-scoped)
    agents_client = AgentsClient(
        endpoint=project_endpoint,
        credential=credential,
    )

    # --- MCP Tool Registration ---
    # Configure MCP server hosting chart generation; add it to the toolset for the run.
    mcp_chart_url = "https://chartmcp02.azurewebsites.net/sse"
    mcp_chart_label = "chart"

    mcp_chart_tool = McpTool(
        server_label=mcp_chart_label,
        server_url=mcp_chart_url,
    )
    mcp_chart_tool.set_approval_mode("never")  # auto-approve tool calls

    toolset = ToolSet()
    toolset.add(mcp_chart_tool)

    # --- Agent instructions ---
    # Emphasize the output contract: respond with ONLY the URL (single line).
    agent_instructions = """
    You have access to an MCP server called `chart` with a tool
    `create_process_control_chart_url`.

    Your job:
    1. Call the MCP tool to generate a statistical process control chart
       using the data points provided by the user.
    2. When the chart is successfully generated, respond with ONLY the
       chart URL, on a single line, with no additional text, markdown,
       or explanation.

    If something goes wrong, respond with:
    ERROR: <short description of the problem>

    Do not describe the chart; only return the URL.
    """

    # Use client context to ensure proper cleanup of resources
    with agents_client:
        # 1) Create an agent bound to your deployed model and the above instructions
        agent = agents_client.create_agent(
            model=model_deployment,
            name="chart-agent",
            instructions=agent_instructions,
        )

        # 2) Create a conversation thread (container for messages/runs)
        thread = agents_client.threads.create()

        # 3) Send user prompt with data points and reiterate URL-only contract
        prompt = (
            "Generate a statistical process control chart for the following data: "
            f"{I_ChartDataPoints}\n\n"
            "Return ONLY the chart URL, nothing else."
        )
        agents_client.messages.create(
            thread_id=thread.id,
            role=MessageRole.USER,
            content=prompt,
        )

        # 4) Run the agent with the MCP toolset
        run = agents_client.runs.create_and_process(
            thread_id=thread.id,
            agent_id=agent.id,
            toolset=toolset,
        )

        # 5) Poll until the run completes or fails (simple blocking loop)
        while True:
            run = agents_client.runs.get(thread_id=thread.id, run_id=run.id)
            if run.status in ["completed", "succeeded"]:  # success states
                break
            if run.status in ["failed", "cancelled"]:     # terminal failure
                raise RuntimeError(f"Chart agent run ended with status: {run.status}")
            time.sleep(1)

        # 6) Prefer the most recent assistant text message for output
        last = agents_client.messages.get_last_message_text_by_role(
            thread_id=thread.id,
            role=MessageRole.AGENT,
        )

        raw_text = ""
        if last is not None and last.text is not None:
            raw_text = last.text.value.strip()

        # 7) Fallback: scan all agent messages (ascending) and collect text if needed
        if not raw_text:
            messages = agents_client.messages.list(
                thread_id=thread.id,
                order=ListSortOrder.ASCENDING,
            )
            collected = []
            for msg in messages:
                if msg.role != MessageRole.AGENT:
                    continue
                for item in msg.content:
                    if isinstance(item, MessageTextContent) and item.text:
                        collected.append(item.text.value)
            raw_text = "\n".join(collected).strip()

        # 8) If the agent explicitly returned an error, pass it through
        if raw_text.startswith("ERROR:"):
            agents_client.delete_agent(agent.id)
            return raw_text

        # 9) Extract the URL from the agent response; enforce URL-only contract
        url = _extract_first_url(raw_text)
        if not url:
            agents_client.delete_agent(agent.id)
            # Return a concise error with a snippet to aid Prompt Flow debugging
            return (
                "ERROR: Chart agent did not return a valid URL. "
                f"Raw response was: {raw_text[:300]}"
            )

        # 10) Cleanup the agent and return the final chart URL
        agents_client.delete_agent(agent.id)
        return url
