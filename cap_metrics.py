
from promptflow.core import tool

import os
from dotenv import load_dotenv

# Azure identity for AAD auth; AgentsClient for model/agent orchestration
from azure.identity import ClientSecretCredential
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import McpTool, ToolSet, ListSortOrder


@tool
def capmetrics(I_DataPoints: str) -> str:
    """
    Prompt Flow tool: Generate process capability metrics via an MCP-enabled Azure AI Agent.
    Input:
      - I_DataPoints: raw datapoints (string) to analyze (e.g., CSV-like text or a prompt describing data).
    Output:
      - Aggregated agent response as a single string.
    """

    # --- Configuration & Secrets ---
    # Load environment variables from a local file so we avoid hardcoding secrets
    dotenv_path = './config.env'
    load_dotenv(dotenv_path=dotenv_path)

    # Core project settings & model deployment
    project_endpoint = os.environ.get("PROJECT_ENDPOINT")
    model_deployment = os.environ.get("MODEL_DEPLOYMENT_NAME")
    api_key = os.environ.get("API_KEY")  # Present if using key-based auth (not used below)

    # AAD application credentials for Azure identity (client credentials flow)
    tenant_id = os.environ.get("AZURE_TENANT_ID")
    client_id = os.environ.get("AZURE_CLIENT_ID")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET")

    # Build an AAD credential that the AgentsClient will use to authenticate
    credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )

    # --- Agents Client ---
    # Create the Azure AI Agents client bound to your project endpoint
    agents_client = AgentsClient(
        endpoint=project_endpoint,
        credential=credential
    )

    # --- MCP Tool Setup ---
    # Configure the MCP server (Process Capability MCP)
    mcp_cpk_url = "https://cpkmcp05.azurewebsites.net/mcp"
    mcp_cpk_label = "cpk"

    # Register the MCP tool so the agent can call MCP server functions
    mcp_cpk_tool = McpTool(
        server_label=mcp_cpk_label,
        server_url=mcp_cpk_url,
    )

    # Approval mode controls whether tool calls require user approval; "never" = auto-approve
    mcp_cpk_tool.set_approval_mode("never")

    # Group tools into a ToolSet so they can be provided to the run
    toolset = ToolSet()
    toolset.add(mcp_cpk_tool)

    response = ""

    # --- Agent Lifecycle & Run ---
    # Use the client as a context manager to ensure proper resource cleanup
    with agents_client:

        # 1) Create an agent configured to use your deployed model
        agent = agents_client.create_agent(
            model=model_deployment,
            name="cap-metric-agent",
            instructions=(
                "You have access to an MCP server called `process-capability-mcp` which "
                "can compute process capability indices. Use the available MCP tools to "
                "answer questions and perform tasks."
            ),
        )

        # 2) Create a conversation thread the agent will use to exchange messages
        thread = agents_client.threads.create()

        # 3) Seed the thread with a user message requesting capability computation
        prompt = "generate process capability for " + I_DataPoints
        message = agents_client.messages.create(
            thread_id=thread.id,
            role="user",
            content=prompt,
        )

        # (Optional) Reaffirm approval mode before running, ensuring tool calls auto-execute
        mcp_cpk_tool.set_approval_mode("never")

        # 4) Start and process the run, providing the toolset (MCP tools) to the agent
        run = agents_client.runs.create_and_process(
            thread_id=thread.id,
            agent_id=agent.id,
            toolset=toolset
        )

        response = ""

        # 5) Poll the run status until it completes or fails
        # NOTE: This code calls time.sleep(1) but does not import time at the top.
        # Add `import time` to your imports to avoid a NameError.
        while True:
            run = agents_client.runs.get(thread_id=thread.id, run_id=run.id)
            if run.status in ["completed", "succeeded"]:  # success states
                break
            elif run.status in ["failed", "cancelled"]:   # terminal error states
                raise RuntimeError(f"Run ended with status: {run.status}")
            time.sleep(1)

        # 6) Retrieve all messages on the thread in ascending order (oldest → newest)
        messages = agents_client.messages.list(
            thread_id=thread.id,
            order=ListSortOrder.ASCENDING
        )

        # 7) Collect textual content from the messages and aggregate into a single response string
        response = ""
        for msg in messages:
            if msg.text_messages:
                last_text = msg.text_messages[-1]
                response += last_text.text.value

        # 8) Clean up: delete the agent after the run finishes to free resources
        agents_client.delete_agent(agent.id)

    # Return the aggregated response from the agent
    return response
