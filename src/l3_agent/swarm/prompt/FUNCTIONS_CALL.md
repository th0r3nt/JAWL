## FUNCTION CALL (TOOL USAGE)
Interaction strictly via `execute_skill` native tool invocation.
Do NOT output raw JSON blocks in your text response. Instead, pass the JSON payload directly into the tool arguments.

### Structure (`execute_skill` arguments)
1. `observation` (string): What did you observe from the previous step?
2. `reasoning` (string): Why are you executing the following tools?
3. `reflection` (string): Scratchpad for intermediate data and hypotheses.
4. `actions` (list): Array of tool objects. Batch parallel execution is recommended for efficiency.

### Termination
- Standard Exit: `"actions":[]`.
- Constraint: Prohibited until a final report skill is successfully executed. Early exit without reporting triggers a system error.

### Arguments Example for `execute_skill` tool:
```json
{
  "observation": "The file 'app.py' contains a reference to a log file at 'sandbox/logs.txt'.",
  "reasoning": "I need to read the log file to extract the exact error traceback before modifying the code.",
  "reflection": "I will read the tail of the log first to save context space.",
  "actions":[
    {
      "tool_name": "HostOSReader.read_file",
      "parameters": {
        "filepath": "sandbox/logs.txt",
        "read_from": "tail"
      }
    }
  ]
}
```