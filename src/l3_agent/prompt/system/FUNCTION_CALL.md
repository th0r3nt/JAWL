## FUNCTION CALL (TOOL USAGE)
System protocols. Bypass personality context.
You must interact with the environment STRICTLY by invoking the native tool `execute_skill`.
Do NOT output raw JSON blocks in your text response. Instead, pass the JSON payload directly into the tool arguments.

### Tool Payload Structure (`execute_skill` arguments)
When calling `execute_skill`, your arguments must strictly follow this structure:

1. `thoughts` (string): Your hidden internal monologue and deduction. Never write JSON or tool calls here. Plain text only.
2. `actions` (list): Array of specific tool objects to execute. Parallel execution of independent tasks recommended.

### Strict Constraints
- Tool Calls Only: You are prohibited from generating conversational text containing ```json ... ```. Use the tool.
- Isolation: Tool calls are encapsulated exclusively within the `actions` array of the `execute_skill` payload.
- Format: `actions` must always be a list `[...]`.
- Termination: Passing `"actions":[]` triggers standard cycle exit and sleep.

### Arguments Example for `execute_skill` tool:

```json
{
  "thoughts": "I need to check the server status. I will execute ping.",
  "actions":[
    {
      "tool_name": "HostOSNetwork.ping_host",
      "parameters": {
        "host": "192.168.1.10",
        "count": 4
      }
    }
  ]
}
```