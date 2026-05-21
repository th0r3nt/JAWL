"""
Single Source of Truth for the graph database.
Defines node table names and a strict list of possible relationships (edges) and categories.
"""

from typing import Literal

# ================================================================
# Schema for the agent's general graph
# ================================================================

GRAPH_NODE_TABLE = "Concept"

# Strict list of possible relationships between concepts
GRAPH_EDGE_TABLES = [
    "IS_A",  # Inheritance / Classification
    "PART_OF",  # Composition / Belonging
    "REQUIRES",  # Dependency
    "CAUSES",  # Cause -> Effect
    "OWNS",  # Possession / Attribute
    "PRODUCES",  # Product of activity
    "CONFLICTS_WITH",  # Antagonism / Incompatibility
    "RELATES_TO",  # General association (when others do not apply)
]  # Literal so that the LLM understands in arguments that argument options are strictly predefined

# Type for strict validation of links by the Pydantic Guard Layer
RelationType = Literal[
    "IS_A", "PART_OF", "REQUIRES", "CAUSES", "OWNS", "PRODUCES", "CONFLICTS_WITH", "RELATES_TO"
]

ConceptCategory = Literal[
    "PERSON",  # Subjects: Specific people, users, agents, authors
    "ORGANIZATION",  # Groups: Companies, communities, teams
    "LOCATION",  # Locations: Physical locations, URL links, file paths
    "SOFTWARE",  # Software: Programs, scripts, frameworks, languages
    "HARDWARE",  # Hardware: Physical devices, PCs, servers
    "DOCUMENT",  # Data: Files, articles, logs, repositories, posts
    "EVENT",  # Events: Occurrences, errors, meetings, historical facts
    "PROJECT",  # Processes: Tasks, global goals, epics
    "CONCEPT",  # Abstractions: Ideas, algorithms, theories, rules of behavior
]

# ================================================================
# Schema for Code Graph
# ================================================================

CODE_NODE_TABLE = "CodeNode"

CODE_EDGE_TABLES = [
    "IMPORTS",  # File imports file or class
    "CONTAINS",  # File contains class/function
    "DEFINES",  # Class defines method
    "CALLS",  # Function calls function
]

CodeRelationType = Literal["IMPORTS", "CONTAINS", "DEFINES", "CALLS"]
CodeNodeType = Literal["FILE", "CLASS", "FUNCTION"]
