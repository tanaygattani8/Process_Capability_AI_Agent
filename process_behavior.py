
from promptflow import tool
import os
import time
from dotenv import load_dotenv

from azure.identity import ClientSecretCredential
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    ListSortOrder,
    MessageTextContent,
    MessageInputTextBlock,
    MessageInputImageUrlBlock,
    MessageImageUrlParam,
    MessageRole,
)

# ---------------------------------------------------------------------------
# Load environment variables
# (Values are loaded inside the tool to keep invocation-local configuration.)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Agent instructions (defined at module scope so they're not rebuilt per call)
# Provide task scope, style, and constraints here.
# ---------------------------------------------------------------------------
AGENT_INSTRUCTIONS = """
You are a Process Behavior & Statistical Process Control (SPC) expert.

When provided:
- A process behavior chart (image)
- Capability metrics (Cp, Cpk, Pp, Ppk, etc.)

Your task is to produce a clear, structured, professional analysis including:

1. Chart Type Identification
   - Identify the type of chart (I-MR, Xbar-R, p-chart, u-chart, etc.).
   - Note visible features (individual points, moving range, subgroups).

2. Control Limits & Key Components
   - Identify the Center Line (CL), Upper Control Limit (UCL), Lower Control Limit (LCL).
   - Identify specification limits if shown.
   - Describe relative position of data to limits.

3. Process Stability Assessment
   Evaluate standard SPC rules:
   - Points beyond control limits
   - 8+ point runs on one side of the mean
   - 8+ point trends (continuous increase or decrease)
   - Cyclical, sawtooth, or repeating patterns
   - Sudden shifts or jumps
   - 2 of 3 beyond 2-sigma on same side
   Clearly state whether the process is stable or unstable.

4. Variation Evaluation
   - Compare local vs global variation.
   - Identify signs of tool wear, operator differences, batch shifts, warm-up effects, etc.
   - Discuss short-term vs long-term variation patterns.

5. Capability Assessment (using provided metrics)
   Use the provided capability metrics to interpret:
   - Is the process centered relative to spec limits?
   - Is variation acceptable?
   - Cp vs Cpk (centering)
   - Pp vs Ppk (long-term vs short-term variation)
   - Provide a qualitative summary of capability.

6. Actionable Recommendations
   Based on the observed patterns, recommend:
   - Investigations for assignable causes.
   - Potential process adjustments.
   - Monitoring guidance.
   - When a process can be considered capable or stable enough for capability reporting.

Constraints:
- Do NOT fabricate numerical values that are not visible on the chart or in the provided metrics.
- If the chart quality is poor or something is unclear, say so explicitly.
- Use clear headings and concise, actionable engineering insights.

"""

# ---------------------------------------------------------------------------
# Prompt Flow Tool: Process Behavior Analysis
# ---------------------------------------------------------------------------
@tool
def processbehavior(o_capmetrics: str, o_chart_url: str) -> str:
    """
    Analyzes a process behavior (control) chart using Azure Agents with vision capabilities.

    Inputs:
        o_capmetrics : str  -> JSON or text description of capability metrics (Cp, Cpk, Pp, Ppk, etc.)
        o_chart_url  : str  -> URL of the process behavior chart image

    Returns:
        str -> Detailed SPC analysis including stability, anomalies, capability insights, and recommendations.
    """

    # --- Configuration & Secrets ---
    # Load environment variables (avoid hardcoding secrets)
    dotenv_path = './config.env'
    load_dotenv(dotenv_path=dotenv_path)

    # Project and model configuration
    project_endpoint = os.environ.get("PROJECT_ENDPOINT")
    model_deployment = os.environ.get("MODEL_DEPLOYMENT_NAME")
    api_key = os.environ.get("API_KEY")  # If using key-based auth (not used below)

    # AAD (client credentials) for AgentsClient authentication
    tenant_id = os.environ.get("AZURE_TENANT_ID")
    client_id = os.environ.get("AZURE_CLIENT_ID")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET")

    # NOTE: Do NOT commit hardcoded credentials. Keep secrets in environment only.
    # tenant_id="..."
    # client_id="..."
    # client_secret="..."

    # Build credential used by the AgentsClient
    credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )

    # --- Agent Client ---
    # Create the Azure AI Agents client bound to your project endpoint
    agents_client = AgentsClient(
        endpoint=project_endpoint,
        credential=credential,
    )

    # --- Prompt Construction ---
    # User prompt combines SPC request with capability metrics for context
    prompt_text = (
        "Analyze the following process behavior chart and provide a detailed SPC interpretation. "
        "Use the supplied capability metrics when forming conclusions.\n\n"
        f"Capability Metrics:\n{o_capmetrics}"
    )

    # Use the client as a context manager for lifecycle management
    with agents_client:
        # 1) Create an agent configured to use the deployed model and instructions
        agent = agents_client.create_agent(
            model=model_deployment,
            name="process-behavior-agent",
            instructions=AGENT_INSTRUCTIONS,
        )

        # 2) Create a conversation thread to hold messages and runs
        thread = agents_client.threads.create()

        # -------------------------------
        # Build multimodal message input
        # (text + image URL with high detail for vision analysis)
        # -------------------------------
        content_blocks = [
            MessageInputTextBlock(text=prompt_text),
            MessageInputImageUrlBlock(
                image_url=MessageImageUrlParam(url=o_chart_url, detail="high")
            ),
        ]

        # 3) Send the user message to the thread
        agents_client.messages.create(
            thread_id=thread.id,
            role=MessageRole.USER,
            content=content_blocks,
        )

        # 4) Execute the agent run (blocking until initial processing finishes)
        run = agents_client.runs.create_and_process(
            thread_id=thread.id,
            agent_id=agent.id,
        )

        # --- Poll for completion with timeout ---
        max_wait_seconds = 60
        waited = 0
        poll_interval = 1

        while True:
            run = agents_client.runs.get(thread_id=thread.id, run_id=run.id)
            # Success states vary by SDK; include both common success markers
            if run.status in ["completed", "succeeded"]:
                break
            # Terminal failure states
            if run.status in ["failed", "cancelled"]:
                raise RuntimeError(f"Run ended with status: {run.status}")
            # Continue polling until timeout
            time.sleep(poll_interval)
            waited += poll_interval
            if waited > max_wait_seconds:
                raise TimeoutError(
                    f"Run did not complete within {max_wait_seconds} seconds. Last status: {run.status}"
                )

        # -------------------------------------------
        # Extract assistant text only (preferred path)
        # get_last_message_text_by_role returns most recent assistant text block, if any.
        # -------------------------------------------
        last_assistant_text = agents_client.messages.get_last_message_text_by_role(
            thread_id=thread.id, role=MessageRole.AGENT
        )

        final_response: str | None = None
        if last_assistant_text is not None and last_assistant_text.text is not None:
            # MessageTextContent.text is a details object; actual string is `.value`
            final_response = last_assistant_text.text.value

        # -------------------------------------------
        # Fallback: scan all messages for text content by the agent
        # Useful if the shortcut above returns nothing.
        # -------------------------------------------
        if not final_response:
            messages = agents_client.messages.list(
                thread_id=thread.id,
                order=ListSortOrder.ASCENDING,  # oldest -> newest
            )
            collected = []
            for msg in messages:
                if msg.role != MessageRole.AGENT:
                    continue
                for item in msg.content:
                    if isinstance(item, MessageTextContent) and item.text:
                        collected.append(item.text.value)
            final_response = "\n\n".join(collected) if collected else ""

        # Optional cleanup: delete the agent to free resources
        agents_client.delete_agent(agent.id)

    # Return analysis or a friendly default if none was produced
    return final_response or "No analysis was produced by the agent."
