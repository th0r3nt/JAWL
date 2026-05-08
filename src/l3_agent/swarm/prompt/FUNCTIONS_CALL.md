## FUNCTION CALL (TOOL USAGE)
Interaction strictly via `execute_skill` native tool invocation.
Do NOT output raw JSON blocks in your text response. Instead, pass the JSON payload directly into the tool arguments.

### Structure (`execute_skill` arguments)
1. `thoughts` (string): Logic and decision-making. Plain text only. NEVER write JSON here.
2. `actions` (list): Array of tool objects. Batch parallel execution is recommended for efficiency.

### Termination
- Standard Exit: `"actions":[]`.
- Constraint: Prohibited until a final report skill is successfully executed. Early exit without reporting triggers a system error.

### Arguments Example for `execute_skill` tool:
```json
{
  "thoughts": "I need to read the log file to extract data.",
  "actions":[
    {
      "tool_name": "HostOSReader.read_file",
      "parameters": {
        "filepath": "sandbox/logs.txt",
        "read_from": "head"
      }
    }
  ]
}
```