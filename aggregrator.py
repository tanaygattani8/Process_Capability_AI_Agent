
from promptflow import tool

import os
import time
from dotenv import load_dotenv

from azure.identity import ClientSecretCredential
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    ListSortOrder,
    MessageRole,
    MessageTextContent,
)

# ---------------------------------------------------------------------------
# Environment configuration
# Load secrets and settings from a local config file (do not hardcode in source).
# ---------------------------------------------------------------------------
dotenv_path = './config.env'
load_dotenv(dotenv_path=dotenv_path)

def _strip_not_assessed(text: str) -> str:
    """
    Helper: remove boilerplate such as 'Not assessed in this run...' from text.
    This prevents the aggregator from treating boilerplate as substantive content.
    """
    if not text:
        return ""

    marker = "Not assessed in this run"
    return "" if marker in text else text


# ---------------------------------------------------------------------------
# Prompt Flow Tool: Aggregates behavior analysis + capability metrics
# into a single management-ready summary
# ---------------------------------------------------------------------------
@tool
def aggregator(o_processbehavior: str, o_capmetrics: str, o_chart_url) -> str:
    # -----------------------------------------------------------------------
    # Load required environment variables (fail fast if critical settings unset)
    # -----------------------------------------------------------------------
    project_endpoint = os.environ.get("PROJECT_ENDPOINT")
    model_deployment = os.environ.get("MODEL_DEPLOYMENT_NAME")  # Not used directly; kept for consistency
    process_capability_aggregator_agent = os.environ.get("PROCESS_CAPABILITY_AGGREGATOR_AGENT")

    if not project_endpoint:
        raise RuntimeError("PROJECT_ENDPOINT must be set in config.env or environment.")
    if not process_capability_aggregator_agent:
        raise RuntimeError("PROCESS_CAPABILITY_AGGREGATOR_AGENT must be set.")
    
    tenant_id = os.environ.get("AZURE_TENANT_ID")
    client_id = os.environ.get("AZURE_CLIENT_ID")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET")

    # Build a client credentials token for Azure AI Agents auth
    credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )

    # -----------------------------------------------------------------------
    # (Informational) What we aggregate and the expected output
    # NOTE: This triple-quoted block is not a function docstring (it appears
    # later than the first statement). It serves as a comment/documentation.
    # -----------------------------------------------------------------------
    """
    Aggregates:
      - Process behavior analysis text from a process behavior agent
      - Process capability analysis / metrics from a capability agent

    Returns a unified, management-ready summary.
    """

    # -----------------------------------------------------------------------
    # Safety checks: ensure we have at least some content to aggregate
    # -----------------------------------------------------------------------
    if not o_processbehavior and not o_capmetrics:
        return "No process behavior or capability information was provided to the aggregator."

    # Optional cleanup of boilerplate to improve synthesis quality
    pb_clean = _strip_not_assessed(o_processbehavior or "")
    cap_clean = _strip_not_assessed(o_capmetrics or "")

    # -----------------------------------------------------------------------
    # Construct a structured user message for the aggregator agent
    # - Provide both raw and cleaned versions (with explicit fallbacks)
    # - Include chart URL for embedding/linking in the final output
    # -----------------------------------------------------------------------
    user_message = f"""
You are the Process Capability Aggregator Agent.

You receive:
{o_processbehavior}
{pb_clean if pb_clean else "(No process behavior analysis was provided or it was not assessed in this run.)"}

{o_capmetrics}
{cap_clean if cap_clean else "(No capability metrics analysis was provided or it was not assessed in this run.)"}

{o_chart_url}

Your tasks:

1. First, provide a clear overview of common process capability indices
   (Cp, Cpk, Pp, Ppk, and any others you consider critical) and when each
   is most appropriate to use (e.g., short-term vs long-term, centered vs uncentered).

2. Then, synthesize the two analyses into a single, coherent engineering narrative:
   - Identify whether the process appears stable or unstable.
   - Interpret capability (is the process capable against the given specs?).
   - Explain how the behavior/stability and capability results fit together.
   - Call out any conflicts between the behavior analysis and capability metrics.

3. Finally, provide 3–5 concise recommendations for management, e.g.:
   - Is the process ready for capability reporting?
   - Should they focus on reducing special causes first?
   - Specific next steps (data collection, investigation, or adjustment).

4. Include o_chart_url as an embedded link as part of the output

Constraints:
- Do NOT fabricate numbers that are not provided in the analyses.
- If one of the sections above is missing or not assessed, clearly state that it
  was not available and focus on the information you do have.
- Use headings and short paragraphs or bullet points to keep this readable
  for engineers and managers.
"""

    # -----------------------------------------------------------------------
    # Create the Agents client (project-scoped) and run the aggregation
    # -----------------------------------------------------------------------
    agents_client = AgentsClient(
        endpoint=project_endpoint,
        credential=credential,
    )

    with agents_client:
        # Create an isolated thread for this aggregation request
        thread = agents_client.threads.create()

        # Send the composed user message (plain text) to the aggregator agent
        agents_client.messages.create(
            thread_id=thread.id,
            role=MessageRole.USER,
            content=user_message,
        )

        # Kick off the run on an existing aggregator agent (by ID from env)
        run = agents_client.runs.create_and_process(
            thread_id=thread.id,
            agent_id=process_capability_aggregator_agent,
        )

        # -------------------------------------------------------------------
        # Poll the run until completion or failure (simple timeout loop)
        # -------------------------------------------------------------------
        max_wait_seconds = 30
        waited = 0
        poll_interval = 1

        while True:
            run = agents_client.runs.get(thread_id=thread.id, run_id=run.id)

            if run.status in ["completed", "succeeded"]:  # success states
                break
            if run.status in ["failed", "cancelled"]:     # terminal failure states
                raise RuntimeError(f"Aggregator run ended with status: {run.status}")

            time.sleep(poll_interval)
            waited += poll_interval
            if waited > max_wait_seconds:
                raise TimeoutError(
                    f"Aggregator run did not complete within {max_wait_seconds} seconds. "
                    f"Last status: {run.status}"
                )

        # -------------------------------------------------------------------
        # Retrieve the assistant's final text (preferred shortcut)
        # -------------------------------------------------------------------
        last = agents_client.messages.get_last_message_text_by_role(
            thread_id=thread.id,
            role=MessageRole.AGENT,
        )

        if last is not None and last.text is not None:
            return last.text.value

        # -------------------------------------------------------------------
        # Fallback: scan all thread messages and collect agent text blocks
        # -------------------------------------------------------------------
        messages = agents_client.messages.list(
            thread_id=thread.id,
            order=ListSortOrder.ASCENDING,  # oldest -> newest
        )

        collected = []
        for msg in messages:
            if msg.role != MessageRole.AGENT:
                continue
            if not msg.content:
                continue
            for item in msg.content:
                if isinstance(item, MessageTextContent) and item.text:
                    collected.append(item.text.value)

        if collected:
            return "\n\n".join(collected)

        # If nothing was returned at all, surface a friendly default
        return "The aggregator agent did not return any text response."
