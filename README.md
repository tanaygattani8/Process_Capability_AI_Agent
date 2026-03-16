# Process Capability AI Agent

A multi-step AI agent built on Azure Prompt Flow that takes raw process measurement data and returns a full capability analysis — metrics, control charts, behavior classification, and a written report — without you touching a spreadsheet.

## What it does

Process capability analysis is one of those things that's conceptually simple but tedious in practice. You collect measurements, compute Cp and Cpk, check whether the process is stable, build a control chart, and write up what it all means. This agent handles all of that in sequence.

Feed it sample data. It runs through five stages:

1. **Data access** — loads and validates the measurement input
2. **Capability metrics** — computes Cp, Cpk, and related indices
3. **Process behavior** — classifies whether the process is stable, drifting, or showing special-cause variation
4. **Chart creation** — generates control charts for visual inspection
5. **Report writing** — produces a narrative summary of findings

The DAG in `flow.dag.yaml` wires these stages together. Each step is a separate Python module, so you can swap out the metrics logic or the report template without touching anything else.

## Tech stack

- Python 3.x
- Azure Prompt Flow (DAG-based orchestration)
- Jinja2 (report templating)
- See `requirements.txt` for the full list

## Project structure

```
├── flow.dag.yaml              # Prompt Flow DAG definition
├── flow.meta.yaml             # Flow metadata
├── data_access.py             # Loads and validates input data
├── cap_metrics.py             # Cp, Cpk, and capability index calculations
├── process_behavior.py        # Stability and variation analysis
├── chart_creator.py           # Control chart generation
├── aggregrator.py             # Combines outputs across steps
├── report_generator.py        # Orchestrates the final report
├── report_writer.py           # Writes the narrative report output
├── process_data_formatter.jinja2  # Report template
├── samples.json               # Sample input data to test with
├── config.env                 # Environment variables
└── requirements.txt
```

## Getting started

**Prerequisites**

- Python 3.8+
- Azure Prompt Flow installed (`pip install promptflow`)
- Azure OpenAI or compatible LLM endpoint configured

**Setup**

```bash
git clone https://github.com/tanaygattani8/Process_Capability_AI_Agent
cd Process_Capability_AI_Agent
pip install -r requirements.txt
```

Copy `config.env` and fill in your credentials:

```bash
cp config.env .env
# Add your Azure endpoint and API key
```

**Run**

```bash
pf flow run --flow . --data samples.json
```

The agent runs through the DAG stages and outputs a capability report. `samples.json` has test data to get you started.

## Why Prompt Flow

The DAG approach means each stage is independently testable and the dependencies between steps are explicit. If the chart creator breaks, the rest of the pipeline is still intact. It also makes it easy to add a new step (say, an anomaly detection pass) without restructuring everything else.

## Contributing

Open to issues and pull requests. If you're testing on a specific type of process data (manufacturing, lab measurements, etc.) and something breaks, file an issue with the data shape and I'll take a look.
