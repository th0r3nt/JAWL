"""
Tree of Thoughts (ToT) generation schema.
Utilizes recursive fractal structures to model nested simulation thought branches.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class ThoughtBranch(BaseModel):
    name: str
    # Optional description to prevent model failures on terse responses
    description: str = ""
    pros: List[str] = Field(default_factory=list)
    cons: List[str] = Field(default_factory=list)
    # Recursive self-reference for nested simulations
    sub_branches: Optional[List["ThoughtBranch"]] = Field(default_factory=list)


# Rebuild recursive Pydantic schema
ThoughtBranch.model_rebuild()


class TreeResponse(BaseModel):
    branches: List[ThoughtBranch] = Field(default_factory=list)


TOT_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "submit_tree",
            "description": "Submits the generated recursive thoughts tree to the system.",
            "parameters": {
                "type": "object",
                "properties": {
                    "branches": {
                        "type": "array",
                        "description": "List of macro-strategies (top-level branches).",
                        "items": {"$ref": "#/$defs/ThoughtBranch"},
                    }
                },
                "required": ["branches"],
                "additionalProperties": False,
                "$defs": {
                    "ThoughtBranch": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Short title of the strategy or path.",
                            },
                            "description": {
                                "type": "string",
                                "description": "Detailed description of logic or tactics.",
                            },
                            "pros": {
                                "type": "array",
                                "description": "List of pros and advantages of this path.",
                                "items": {"type": "string"},
                            },
                            "cons": {
                                "type": "array",
                                "description": "List of cons, risks, and vulnerabilities of this path.",
                                "items": {"type": "string"},
                            },
                            "sub_branches": {
                                "type": "array",
                                "description": "Nested scenarios (micro-tactics).",
                                "items": {"$ref": "#/$defs/ThoughtBranch"},
                            },
                        },
                        "required": [
                            "name",
                        ],
                        "additionalProperties": False,
                    }
                },
            },
        },
    }
]
