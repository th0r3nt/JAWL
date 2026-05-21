# Meta Access Levels (`meta.access_level`)

The Meta interface allows the agent to modify the system configuration "on the fly" without a reboot or manual editing of YAML files.

* **0 (SAFE):** The agent has the right to modify only basic LLM parameters (target model name and generation temperature).
* **1 (CONFIGURATOR):** The agent receives the right to manage memory limits and context depth.
* **2 (ARCHITECT):** The agent receives access to the system lifecycle (commands to shutdown and reboot), as well as the ability to programmatically enable or disable L2 interfaces.
* **3 (CREATOR):** Maximum level. Grants the agent the right to write Python scripts in the sandbox and dynamically register them in the core as its own native skills (`execute_skill`). The agent gains the ability to autonomously extend its own functionality and integrate with any external APIs.