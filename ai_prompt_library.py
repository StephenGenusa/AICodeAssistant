"""
AI Prompt Library for Programming Assistance.

This module provides a structured way to organize, access, and manage
AI prompts for various programming assistance scenarios.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
import json
import yaml
import datetime
from enum import Enum


class PromptFormat(Enum):
    """Format options for storing and presenting prompts."""
    PLAIN = "plain"
    MARKDOWN = "markdown"
    TRIPLE_QUOTES = "triple_quotes"


@dataclass
class Prompt:
    """
    A single AI prompt for a specific programming task.

    Attributes:
        title: The title/name of the prompt
        text: The actual prompt text
        tags: Optional tags for categorization and search
        format: The format of the prompt text
        created_at: When the prompt was created
        updated_at: When the prompt was last updated
    """
    title: str
    text: str
    tags: Set[str] = field(default_factory=set)
    format: PromptFormat = PromptFormat.TRIPLE_QUOTES
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)
    updated_at: datetime.datetime = field(default_factory=datetime.datetime.now)

    def __repr__(self) -> str:
        return f"Prompt({self.title})"

    def format_text(self) -> str:
        """Return the properly formatted prompt text."""
        if self.format == PromptFormat.TRIPLE_QUOTES:
            return f'"""{self.text}"""'
        return self.text

    def update(self, new_text: str) -> None:
        """Update the prompt text and update timestamp."""
        self.text = new_text
        self.updated_at = datetime.datetime.now()


@dataclass
class Category:
    """
    A category of programming assistance prompts.

    Attributes:
        name: The name of the category
        description: Optional description of the category
        prompts: Dictionary of prompts in this category
    """
    name: str
    description: str = ""
    prompts: Dict[str, Prompt] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"Category({self.name}, {len(self.prompts)} prompts)"

    def add_prompt(self, prompt: Prompt) -> None:
        """Add a prompt to this category."""
        self.prompts[prompt.title] = prompt

    def get_prompt(self, title: str) -> Optional[Prompt]:
        """Get a prompt by its title."""
        return self.prompts.get(title)

    def remove_prompt(self, title: str) -> bool:
        """Remove a prompt by its title. Returns True if successful."""
        if title in self.prompts:
            del self.prompts[title]
            return True
        return False

    def list_prompts(self) -> List[str]:
        """List all prompt titles in this category."""
        return list(self.prompts.keys())


class AIPromptLibrary:
    """
    Main class to manage a library of AI prompts for programming assistance.

    This class organizes prompts by categories and provides methods to
    access, update, and persist prompt data.
    """

    def __init__(self):
        """Initialize an empty prompt library."""
        self.categories: Dict[str, Category] = {}
        self.common_instructions: List[str] = []

    def add_category(self, name: str, description: str = "") -> Category:
        """Add a new category to the library."""
        category = Category(name=name, description=description)
        self.categories[name] = category
        return category

    def get_category(self, name: str) -> Optional[Category]:
        """Get a category by name."""
        return self.categories.get(name)

    def list_categories(self) -> List[str]:
        """List all category names."""
        return list(self.categories.keys())

    def add_prompt(self, category_name: str, prompt: Prompt) -> bool:
        """
        Add a prompt to a specified category.

        Args:
            category_name: Name of the category to add the prompt to
            prompt: The Prompt object to add

        Returns:
            True if successful, False if category doesn't exist
        """
        category = self.get_category(category_name)
        if category:
            category.add_prompt(prompt)
            return True
        return False

    def get_prompt(self, category_name: str, prompt_title: str) -> Optional[Prompt]:
        """Get a prompt by category and title."""
        category = self.get_category(category_name)
        if category:
            return category.get_prompt(prompt_title)
        return None

    def search_prompts(self, query: str) -> List[Prompt]:
        """
        Search for prompts containing the query in title or text.

        Args:
            query: The search string to look for

        Returns:
            A list of matching Prompt objects
        """
        results = []
        query = query.lower()

        for category in self.categories.values():
            for prompt in category.prompts.values():
                if (query in prompt.title.lower() or
                        query in prompt.text.lower()):
                    results.append(prompt)

        return results

    def search_by_tag(self, tag: str) -> List[Prompt]:
        """
        Find all prompts with a specific tag.

        Args:
            tag: The tag to search for

        Returns:
            A list of Prompt objects with the specified tag
        """
        results = []

        for category in self.categories.values():
            for prompt in category.prompts.values():
                if tag in prompt.tags:
                    results.append(prompt)

        return results

    def add_common_instruction(self, instruction: str) -> None:
        """Add a common instruction to be included with prompts."""
        self.common_instructions.append(instruction)

    def get_full_prompt(self, category_name: str, prompt_title: str) -> Optional[str]:
        """
        Get a complete prompt with common instructions included.

        Args:
            category_name: The category containing the prompt
            prompt_title: The title of the specific prompt

        Returns:
            The full prompt text with common instructions, or None if not found
        """
        prompt = self.get_prompt(category_name, prompt_title)
        if not prompt:
            return None

        # Combine common instructions with the specific prompt
        if self.common_instructions:
            common_text = "\n\n".join(self.common_instructions)
            return f"{common_text}\n\n{prompt.format_text()}"

        return prompt.format_text()

    def save_to_json(self, filepath: str) -> bool:
        """
        Save the entire prompt library to a JSON file.

        Args:
            filepath: Path to save the JSON file

        Returns:
            True if successful, False otherwise
        """
        try:
            data = {
                "common_instructions": self.common_instructions,
                "categories": {}
            }

            for cat_name, category in self.categories.items():
                cat_data = {
                    "description": category.description,
                    "prompts": {}
                }

                for prompt_title, prompt in category.prompts.items():
                    cat_data["prompts"][prompt_title] = {
                        "text": prompt.text,
                        "tags": list(prompt.tags),
                        "format": prompt.format.value,
                        "created_at": prompt.created_at.isoformat(),
                        "updated_at": prompt.updated_at.isoformat()
                    }

                data["categories"][cat_name] = cat_data

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            return True
        except Exception as e:
            print(f"Error saving to JSON: {str(e)}")
            return False

    def load_from_json(self, filepath: str) -> bool:
        """
        Load a prompt library from a JSON file.

        Args:
            filepath: Path to the JSON file

        Returns:
            True if successful, False otherwise
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Clear existing data
            self.categories = {}
            self.common_instructions = []

            # Load common instructions
            self.common_instructions = data.get("common_instructions", [])

            # Load categories and prompts
            for cat_name, cat_data in data.get("categories", {}).items():
                category = self.add_category(
                    name=cat_name,
                    description=cat_data.get("description", "")
                )

                for prompt_title, prompt_data in cat_data.get("prompts", {}).items():
                    created_at = datetime.datetime.fromisoformat(
                        prompt_data.get("created_at", datetime.datetime.now().isoformat()))
                    updated_at = datetime.datetime.fromisoformat(
                        prompt_data.get("updated_at", datetime.datetime.now().isoformat()))

                    prompt = Prompt(
                        title=prompt_title,
                        text=prompt_data.get("text", ""),
                        tags=set(prompt_data.get("tags", [])),
                        format=PromptFormat(prompt_data.get("format", PromptFormat.TRIPLE_QUOTES.value)),
                        created_at=created_at,
                        updated_at=updated_at
                    )

                    category.add_prompt(prompt)

            return True
        except Exception as e:
            print(f"Error loading from JSON: {str(e)}")
            return False

    def export_to_yaml(self, filepath: str) -> bool:
        """
        Export the prompt library to YAML format.

        Args:
            filepath: Path to save the YAML file

        Returns:
            True if successful, False otherwise
        """
        try:
            # Use the same structure as for JSON
            data = {
                "common_instructions": self.common_instructions,
                "categories": {}
            }

            for cat_name, category in self.categories.items():
                cat_data = {
                    "description": category.description,
                    "prompts": {}
                }

                for prompt_title, prompt in category.prompts.items():
                    cat_data["prompts"][prompt_title] = {
                        "text": prompt.text,
                        "tags": list(prompt.tags),
                        "format": prompt.format.value,
                        "created_at": prompt.created_at.isoformat(),
                        "updated_at": prompt.updated_at.isoformat()
                    }

                data["categories"][cat_name] = cat_data

            with open(filepath, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, sort_keys=False)

            return True
        except Exception as e:
            print(f"Error exporting to YAML: {str(e)}")
            return False

def create_programmer_assistance_library() -> AIPromptLibrary:
    """
    Create and populate a library with programming assistance prompts.

    Returns:
        An AIPromptLibrary instance populated with categories and prompts
    """
    library = AIPromptLibrary()

    # Add common instructions
    library.add_common_instruction(
        "Follow professional Python coding standards, including PEP 8 guidelines."
    )
    library.add_common_instruction(
        "Use clear, descriptive variable and function names."
    )
    library.add_common_instruction(
        "Include type hints in function signatures when possible."
    )
    library.add_common_instruction(
        "Provide comprehensive docstrings in Google/NumPy style for all functions and classes."
    )

    # Create categories
    bug_fixing = library.add_category(
        "Bug Fixing and Debugging",
        "Prompts for identifying and fixing bugs, performance issues, and unexpected behavior."
    )

    code_generation = library.add_category(
        "Code Generation",
        "Prompts for creating new code, implementing algorithms, and building features."
    )

    code_improvement = library.add_category(
        "Code Improvement",
        "Prompts for refactoring, optimizing, and enhancing existing code."
    )

    translation = library.add_category(
        "Translation and Conversion",
        "Prompts for converting between languages, frameworks, and paradigms."
    )

    learning = library.add_category(
        "Learning and Understanding",
        "Prompts for explaining code, concepts, and providing educational examples."
    )

    integration = library.add_category(
        "Integration and Extension",
        "Prompts for integrating services and extending existing code."
    )

    devops = library.add_category(
        "DevOps and Infrastructure",
        "Prompts for infrastructure as code, deployment, and CI/CD."
    )

    security = library.add_category(
        "Security and Compliance",
        "Prompts for security best practices and compliance requirements."
    )

    specialized = library.add_category(
        "Specialized Tasks",
        "Prompts for domain-specific programming tasks."
    )

    # ==================== BUG FIXING AND DEBUGGING ====================

    bug_fixing.add_prompt(Prompt(
        title="Fix Specific Bug with Error Messages",
        text="""
The following Python code has a bug that needs to be fixed. Each file is separated by a line of asterisks (`*****`).

BUG DESCRIPTION: [user specified]

As an expert Python programmer, please:

1. First, carefully analyze the code and identify the root cause of the bug
2. Explain the issue in clear, concise terms
3. Provide a corrected version of the problematic code section with enough context I can make the fix or fixes required
4. Only if there are many changes required, include a complete fixed file
5. Explain why your solution fixes the issue
6. If there are multiple possible fixes, discuss tradeoffs between approaches

When examining the code, pay special attention to:
- Edge cases and error handling
- Type consistency and conversion issues
- Resource management (file handles, connections)
- Concurrency issues if applicable
- Logical flow and conditional statements
- Function signature mismatches
- Import problems and library versioning

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"bug", "error", "fix", "debug"}
    ))

    bug_fixing.add_prompt(Prompt(
        title="Debug Race Conditions or Concurrency Issues",
        text="""
I'm dealing with a race condition or concurrency issue in the following Python code. Each file is separated by a line of asterisks (`*****`).

ISSUE DESCRIPTION: [user to provide details about the concurrency issue]

As a concurrency expert, please:

1. Analyze the code to identify potential race conditions, deadlocks, or thread safety issues
2. Explain the fundamental problem in clear terms, including how the race condition occurs
3. Provide a solution that addresses the concurrency issue while maintaining the code's functionality
4. Explain your reasoning and any concurrency patterns or primitives you're using (locks, semaphores, queues, etc.)
5. If applicable, suggest any alternative approaches with their respective trade-offs

Pay special attention to:
- Shared resource access patterns
- Lock acquisition ordering
- Thread/process synchronization mechanisms
- Atomicity of operations
- Potential deadlock scenarios
- Resource leaks

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"concurrency", "race condition", "deadlock", "threading", "async"}
    ))

    bug_fixing.add_prompt(Prompt(
        title="Resolve Memory Leaks or Performance Bottlenecks",
        text="""
I'm experiencing memory leaks or performance bottlenecks in the following Python code. Each file is separated by a line of asterisks (`*****`).

ISSUE DESCRIPTION: [user to describe performance problem or memory leak]

As a performance optimization expert, please:

1. Analyze the code to identify potential memory leaks, inefficient algorithms, or performance bottlenecks
2. Explain what specifically is causing the issue and why it's problematic
3. Provide optimized code that addresses the inefficiency while maintaining correctness
4. Explain the performance improvements your solution provides and any trade-offs made
5. If relevant, suggest profiling approaches to verify the improvement

Focus particularly on:
- Time complexity and algorithm efficiency
- Memory usage patterns
- Resource cleanup
- Caching opportunities
- Data structure selections
- I/O or network bottlenecks
- CPU-bound vs. IO-bound operations

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"performance", "memory leak", "optimization", "profiling", "bottleneck"}
    ))

    bug_fixing.add_prompt(Prompt(
        title="Fix Compatibility Issues Between Libraries",
        text="""
I'm experiencing compatibility issues between libraries in the following Python code. Each file is separated by a line of asterisks (`*****`).

ISSUE DESCRIPTION: [user to describe the compatibility problem]
Library Versions:
[user to list relevant library versions]

As a Python expert familiar with library dependencies and compatibility, please:

1. Identify the specific compatibility issues between the libraries or API versions
2. Explain why these issues are occurring
3. Provide code changes that resolve the compatibility problems
4. Suggest any dependency version adjustments that might be needed
5. If applicable, recommend alternative libraries that could avoid these issues

Pay special attention to:
- API changes between library versions
- Dependency conflicts
- Import order issues
- Monkey patching conflicts
- Namespace collisions
- Runtime vs. import-time behaviors

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"compatibility", "libraries", "dependencies", "version conflict"}
    ))

    bug_fixing.add_prompt(Prompt(
        title="Troubleshoot Environment-Specific Issues",
        text="""
I have Python code that works in one environment but fails in another. Each file is separated by a line of asterisks (`*****`).

ENVIRONMENT DETAILS:
Working environment: [user to describe working environment]
Failing environment: [user to describe failing environment]
Error message or behavior: [user to provide]

As a Python environment expert, please:

1. Analyze the code to identify potential environment-specific dependencies or assumptions
2. Explain why the code works in one environment but not the other
3. Provide changes that make the code work consistently across environments
4. Suggest best practices for making the code more environment-agnostic

Consider issues related to:
- Operating system differences
- Python version discrepancies
- Path handling and filesystem access
- Environment variables and configurations
- Platform-specific libraries or features
- Containerization or virtualization factors
- Package installation differences

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"environment", "platform", "compatibility", "docker", "deployment"}
    ))

    bug_fixing.add_prompt(Prompt(
        title="Identify Edge Cases Causing Failures",
        text="""
I have Python code that fails intermittently or in specific edge cases. Each file is separated by a line of asterisks (`*****`).

ISSUE DESCRIPTION: [user to describe the intermittent failure]
Examples of inputs that fail: [user to provide, if available]

As a Python expert focused on robustness, please:

1. Analyze the code to identify potential edge cases that could cause the described failures
2. Explain the specific conditions under which the code would fail
3. Provide code changes that handle these edge cases properly
4. Suggest comprehensive test cases that would verify the fix works for all scenarios

Focus particularly on:
- Boundary conditions
- Null/None/empty input handling
- Type assumptions and coercion
- Error handling and exceptions
- Resource availability
- Timing-sensitive operations
- Numerical precision or overflow issues

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"edge cases", "robustness", "error handling", "testing", "boundary conditions"}
    ))

    # ==================== CODE GENERATION ====================

    code_generation.add_prompt(Prompt(
        title="Generate Boilerplate Code",
        text="""
I need to create boilerplate code for the following purpose:

PURPOSE: [user to describe what they need]
REQUIREMENTS:
- [user to list specific requirements]

Please generate professional, well-structured Python code that:

1. Follows best practices for the specified use case
2. Includes comprehensive documentation and type hints
3. Has proper error handling and validation
4. Is modular and maintainable

For data models or API endpoints, please include:
- Appropriate validation
- Clear class/function interfaces
- Serialization/deserialization where relevant
- Any necessary helper methods

Please format your response with clear section headings and use code blocks with Python syntax highlighting. Explain any design decisions or patterns you've employed.
""",
        tags={"boilerplate", "generate", "template", "scaffold"}
    ))

    code_generation.add_prompt(Prompt(
        title="Implement Algorithm or Data Structure",
        text="""
I need to implement the following algorithm or data structure in Python:

ALGORITHM/DATA STRUCTURE: [user to specify]
REQUIREMENTS:
- [user to list specific requirements]

As an expert Python programmer, please:

1. Implement an efficient and correct version of this algorithm/data structure
2. Include detailed docstrings explaining the approach and time/space complexity
3. Add type hints for all functions and methods
4. Include example usage that demonstrates key functionality
5. Add appropriate error handling and edge case management

If there are multiple implementation approaches, please explain the trade-offs between them and why you chose your specific implementation.

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"algorithm", "data structure", "implementation", "optimization"}
    ))

    code_generation.add_prompt(Prompt(
        title="Create Unit Tests or Test Fixtures",
        text="""
I need comprehensive unit tests for the following Python code. Each file is separated by a line of asterisks (`*****`).

CODE PURPOSE: [user to describe what the code does]

As a testing expert, please:

1. Create thorough unit tests that cover normal operation, edge cases, and error conditions
2. Use pytest or unittest framework (user preference if specified)
3. Include appropriate fixtures, mocks, or stubs as needed
4. Structure the tests logically with clear test names and organization
5. Add docstrings to test functions explaining what they're testing

Consider testing:
- Input validation
- Expected outputs for various inputs
- Error handling
- Edge cases and boundary conditions
- Any business logic or algorithmic correctness

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"testing", "unit tests", "pytest", "unittest", "test fixtures"}
    ))

    code_generation.add_prompt(Prompt(
        title="Generate Documentation and Docstrings",
        text="""
I need to add comprehensive documentation and docstrings to the following Python code. Each file is separated by a line of asterisks (`*****`).

As a documentation expert, please:

1. Add Google/NumPy style docstrings to all functions, methods, and classes
2. Include parameter descriptions, return types, and exceptions raised
3. Add module-level docstrings explaining the overall purpose
4. Where appropriate, provide examples of usage
5. Maintain the existing code functionality unchanged

Focus particularly on:
- Clarity and completeness of explanations
- Consistent formatting and style
- Accurate type specifications
- Documenting side effects or important behaviors
- Making complex logic understandable

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"documentation", "docstrings", "comments", "google style"}
    ))

    code_generation.add_prompt(Prompt(
        title="Build CLI Interface",
        text="""
I need to create a command-line interface for the following functionality. Each file is separated by a line of asterisks (`*****`).

FUNCTIONALITY DESCRIPTION: [user to describe the functionality]
CLI REQUIREMENTS:
- [user to list specific CLI requirements]

As a CLI design expert, please:

1. Create a well-structured CLI using argparse, click, or typer (user preference if specified)
2. Include appropriate command-line arguments, options, and subcommands
3. Provide helpful help text and documentation
4. Implement proper error handling and user feedback
5. Add type validation and conversion where appropriate

Consider including:
- Progress indicators for long-running operations
- Colorized output where appropriate
- Sensible defaults for optional parameters
- Both verbose and quiet modes
- Logging configuration options

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"CLI", "command line", "argparse", "click", "typer"}
    ))

    code_generation.add_prompt(Prompt(
        title="Implement Design Pattern",
        text="""
I need to implement the following design pattern in Python for this specific scenario:

DESIGN PATTERN: [user to specify pattern]
SCENARIO: [user to describe the specific use case]

As a design pattern expert, please:

1. Implement a clean, idiomatic Python version of this design pattern
2. Tailor the implementation to the specific scenario described
3. Include comprehensive docstrings and comments explaining the pattern
4. Add example usage demonstrating how to use the implementation
5. Discuss any Python-specific adaptations of the traditional pattern

If there are alternative approaches or patterns that might work better for this scenario, please mention them and explain your reasoning.

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"design pattern", "architecture", "object-oriented", "software design"}
    ))

    code_generation.add_prompt(Prompt(
        title="Convert Pseudocode or Algorithm to Code",
        text="""
I need to convert the following pseudocode or algorithm description into working Python code:

PSEUDOCODE/ALGORITHM:
```
[user to paste pseudocode or algorithm description]
```

REQUIREMENTS:
- [user to list any specific requirements]

As a Python implementation expert, please:

1. Convert this pseudocode/algorithm to clean, efficient Python code
2. Maintain the logical structure and intent of the original algorithm
3. Choose appropriate data structures and Python idioms
4. Add comprehensive docstrings and comments explaining the implementation
5. Include type hints for better readability and type checking

If there are any ambiguities in the pseudocode/algorithm, please note them and explain your interpretation and implementation decisions.

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"algorithm", "pseudocode", "implementation", "conversion"}
    ))

    code_generation.add_prompt(Prompt(
        title="Scaffold New Project with Proper Structure",
        text="""
I need to set up the structure for a new Python project with the following requirements:

PROJECT TYPE: [user to specify - web app, library, CLI tool, etc.]
FEATURES/FUNCTIONALITY: [user to describe]
ADDITIONAL REQUIREMENTS: [user to specify any specific needs]

As a Python project architecture expert, please:

1. Design a complete project structure with appropriate directories and files
2. Include setup files, configuration, and dependency management
3. Set up proper package structure and imports
4. Add scaffolding for tests, documentation, and CI/CD
5. Provide starter code for key components

Include:
- Directory structure visualization
- Key files with their content (setup.py/pyproject.toml, README.md, etc.)
- Explanation of the architecture and design decisions
- Recommendations for development workflow and tools

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"project structure", "scaffolding", "architecture", "setup", "best practices"}
    ))

    # ==================== CODE IMPROVEMENT ====================

    code_improvement.add_prompt(Prompt(
        title="Refactor Complex Functions",
        text="""
I need to refactor the following complex Python function(s) to improve modularity and readability. Each file is separated by a line of asterisks (`*****`).

REFACTORING GOALS: [user to specify goals - readability, testability, etc.]

As a Python refactoring expert, please:

1. Analyze the existing code and identify areas that need improvement
2. Refactor the code to be more modular, readable, and maintainable
3. Break down complex functions into smaller, more focused functions
4. Improve naming for better code clarity
5. Add appropriate docstrings and type hints
6. Ensure the refactored code preserves the original functionality

Focus on:
- Single Responsibility Principle
- Reducing cognitive complexity
- Eliminating code duplication
- Improving function signatures and interfaces
- Making the code more testable
- Preserving business logic and behavior

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"refactoring", "clean code", "modularity", "readability"}
    ))

    code_improvement.add_prompt(Prompt(
        title="Add Type Hints",
        text="""
I need to add comprehensive type hints to the following Python code to improve code quality and enable static analysis. Each file is separated by a line of asterisks (`*****`).

As a Python typing expert, please:

1. Add appropriate type hints to all function parameters, return values, and variable annotations
2. Use complex types (Union, Optional, Generic, etc.) where appropriate
3. Add TypedDict, Protocol, or custom classes for complex structures
4. Include docstrings that complement the type hints
5. Maintain the existing code functionality and structure

Consider:
- Using appropriate container types (List, Dict, Set, etc.)
- Handling optional values and None properly
- Using TypeVar for generic functions
- Adding appropriate imports (from typing, collections.abc, etc.)
- Using Literal for constrained string/number types
- Handling callable types properly

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"type hints", "typing", "mypy", "static analysis", "documentation"}
    ))

    code_improvement.add_prompt(Prompt(
        title="Improve Error Handling and Input Validation",
        text="""
I need to enhance error handling and input validation in the following Python code. Each file is separated by a line of asterisks (`*****`).

As an expert in robust Python programming, please:

1. Identify areas where error handling or input validation is missing or insufficient
2. Add appropriate try-except blocks, input validation, and error messages
3. Create custom exceptions if they would improve error clarity
4. Ensure errors are handled at the right level of abstraction
5. Add appropriate logging for errors and edge cases
6. Make error messages helpful and informative

Focus on:
- Validating function inputs before processing
- Handling expected and unexpected exceptions
- Providing context in error messages
- Failing early and clearly
- Using appropriate exception types
- Adding defensive programming techniques
- Maintaining the existing code functionality

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"error handling", "exceptions", "validation", "robustness", "logging"}
    ))

    code_improvement.add_prompt(Prompt(
        title="Enhance Logging for Debugging and Monitoring",
        text="""
I need to improve the logging in the following Python code to enable better debugging and monitoring. Each file is separated by a line of asterisks (`*****`).

LOGGING REQUIREMENTS: [user to specify any specific logging needs]

As a Python logging expert, please:

1. Add comprehensive logging throughout the code at appropriate levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
2. Set up proper logger configuration and hierarchy
3. Include contextual information in log messages (function names, parameters, IDs, etc.)
4. Add timing for performance-sensitive operations if appropriate
5. Ensure exception details are properly captured in logs
6. Maintain existing code functionality

Consider:
- Using structured logging where appropriate
- Setting up log rotation or handlers
- Adding appropriate log levels for different types of information
- Including traceback information for errors
- Avoiding logging sensitive information

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"logging", "debugging", "monitoring", "observability", "reporting"}
    ))

    code_improvement.add_prompt(Prompt(
        title="Optimize for Performance",
        text="""
I need to optimize the following Python code for better performance while maintaining its functionality. Each file is separated by a line of asterisks (`*****`).

PERFORMANCE CONCERNS: [user to describe performance issues or goals]

As a Python performance optimization expert, please:

1. Analyze the code to identify performance bottlenecks and inefficiencies
2. Optimize the code focusing on the most impactful changes
3. Explain the performance improvements and the reasoning behind each change
4. Discuss any tradeoffs made (readability, memory usage, etc.)
5. If applicable, suggest how to measure the performance improvement

Focus on:
- Algorithm efficiency and time complexity
- Appropriate data structure selection
- Reducing unnecessary operations or computations
- Memory usage and object creation/destruction
- I/O and network operations optimization
- Using built-in functions and optimized libraries
- Parallelization or concurrency where appropriate

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"performance", "optimization", "efficiency", "algorithms", "profiling"}
    ))

    code_improvement.add_prompt(Prompt(
        title="Convert Synchronous to Asynchronous",
        text="""
I need to convert the following synchronous Python code to use asynchronous patterns. Each file is separated by a line of asterisks (`*****`).

ASYNC REQUIREMENTS: [user to specify async framework preference or requirements]

As an async Python expert, please:

1. Convert the synchronous code to use async/await patterns
2. Use appropriate async libraries and primitives (asyncio, aiohttp, etc.)
3. Identify I/O-bound operations that can benefit from async execution
4. Handle async context management and resource cleanup properly
5. Explain key changes and potential gotchas of the async implementation

Consider:
- Proper task creation and management
- Error handling in async contexts
- Converting blocking calls to async equivalents
- Managing concurrency and parallelism appropriately
- Maintaining the same logical flow and functionality
- Backward compatibility if required

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"async", "asyncio", "concurrency", "non-blocking", "coroutines"}
    ))

    code_improvement.add_prompt(Prompt(
        title="Modernize Legacy Code",
        text="""
I need to modernize the following legacy Python code to use newer language features and best practices. Each file is separated by a line of asterisks (`*****`).

CURRENT PYTHON VERSION: [user to specify]
TARGET PYTHON VERSION: [user to specify]

As a Python modernization expert, please:

1. Update the code to use appropriate features from newer Python versions
2. Replace deprecated functions, methods, or patterns
3. Improve code structure and organization based on modern practices
4. Add type hints, docstrings, and other modern documentation approaches
5. Maintain the existing functionality and behavior

Consider updating:
- String formatting (f-strings vs % formatting)
- Dictionary and set operations
- Context managers and resource handling
- Path manipulation (pathlib vs os.path)
- Using dataclasses or named tuples where appropriate
- Comprehensions instead of loops where appropriate
- Unpacking and assignment expressions
- Updated exception handling patterns

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"modernization", "refactoring", "python3", "legacy code", "upgrade"}
    ))

    # ==================== TRANSLATION AND CONVERSION ====================

    translation.add_prompt(Prompt(
        title="Translate Between Programming Languages",
        text="""
I need to translate the following code from [SOURCE LANGUAGE] to Python. Each file is separated by a line of asterisks (`*****`).

SOURCE LANGUAGE: [user to specify]
SPECIFIC REQUIREMENTS: [user to specify any special needs]

As a language translation expert, please:

1. Translate the code to idiomatic, Pythonic code
2. Preserve the functionality and logic of the original code
3. Use appropriate Python libraries and features
4. Add docstrings and type hints to the Python version
5. Explain any significant translation decisions or challenges

Pay attention to:
- Different language paradigms and how they map to Python
- Appropriate error handling in Python
- Matching the original code's behavior
- Python best practices and idioms
- Performance considerations where relevant

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"translation", "language conversion", "porting", "rewrite"}
    ))

    translation.add_prompt(Prompt(
        title="Convert Between Web Frameworks",
        text="""
I need to convert code from [SOURCE FRAMEWORK] to [TARGET FRAMEWORK]. Each file is separated by a line of asterisks (`*****`).

SOURCE FRAMEWORK: [user to specify, e.g., Flask]
TARGET FRAMEWORK: [user to specify, e.g., FastAPI]

As a web framework expert, please:

1. Convert the code from the source framework to the target framework
2. Maintain the same functionality and behavior
3. Use idiomatic patterns and features of the target framework
4. Highlight key differences and conversion decisions
5. Include any necessary configuration or setup changes

Consider:
- Routing and URL patterns
- Request and response handling
- Authentication and authorization mechanisms
- Template rendering or frontend integration
- Database interactions and ORM usage
- Middleware or extension equivalents
- Configuration and environment management

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"web framework", "conversion", "Flask", "Django", "FastAPI", "migration"}
    ))

    translation.add_prompt(Prompt(
        title="Migrate Between Database ORMs",
        text="""
I need to migrate the following database code from [SOURCE ORM] to [TARGET ORM]. Each file is separated by a line of asterisks (`*****`).

SOURCE ORM: [user to specify, e.g., SQLAlchemy]
TARGET ORM: [user to specify, e.g., Django ORM]

As a database ORM expert, please:

1. Convert the models, queries, and database operations to the target ORM
2. Maintain the same data structure and relationships
3. Preserve transaction handling and integrity constraints
4. Convert any custom queries or advanced features
5. Include any necessary migration steps or configuration

Focus on:
- Model definition and field mappings
- Relationship definitions (one-to-many, many-to-many, etc.)
- Query conversion with equivalent filtering and sorting
- Transaction and session management
- Index and constraint definitions
- Migration strategies for existing data
- Performance considerations

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"database", "ORM", "migration", "SQLAlchemy", "Django", "Peewee"}
    ))

    translation.add_prompt(Prompt(
        title="Update Code for New API Versions",
        text="""
I need to update the following code to work with a newer version of [API/LIBRARY]. Each file is separated by a line of asterisks (`*****`).

CURRENT VERSION: [user to specify]
TARGET VERSION: [user to specify]
API/LIBRARY: [user to specify]

As an API migration expert, please:

1. Update the code to use the newer API version
2. Identify and replace deprecated or removed functionality
3. Implement equivalent functionality using the new API
4. Add any new required configuration or setup
5. Explain key changes and migration decisions

Consider:
- Breaking changes in the API
- Method signature changes
- Configuration and initialization changes
- Error handling and exception changes
- New features that could improve the code
- Backward compatibility requirements if any

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"API migration", "library upgrade", "version update", "compatibility"}
    ))

    translation.add_prompt(Prompt(
        title="Transform to Different Design Pattern",
        text="""
I need to transform the following code to use a different design pattern. Each file is separated by a line of asterisks (`*****`).

CURRENT PATTERN: [user to specify or describe]
TARGET PATTERN: [user to specify]
REASON FOR CHANGE: [user to explain]

As a design pattern expert, please:

1. Restructure the code to implement the target design pattern
2. Maintain the same functionality and external interfaces
3. Apply Python best practices for the target pattern
4. Explain the key changes and benefits of the new pattern
5. Highlight any trade-offs or considerations

Consider:
- Class structure and responsibility changes
- Interface design and abstraction
- State management differences
- Object creation and lifecycle
- Error handling approach
- Testing implications

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"design pattern", "refactoring", "architecture", "software design"}
    ))

    # ==================== LEARNING AND UNDERSTANDING ====================

    learning.add_prompt(Prompt(
        title="Explain Complex Code",
        text="""
I need help understanding the following complex Python code. Each file is separated by a line of asterisks (`*****`).

SPECIFIC AREAS I'M CONFUSED ABOUT: [user to specify, or leave blank for a complete explanation]

As a code explanation expert, please:

1. Break down the code's purpose and functionality in clear, simple terms
2. Explain the overall structure and flow of the code
3. Clarify complex or non-obvious sections with detailed explanations
4. Describe any algorithms, patterns, or techniques being used
5. Highlight important function calls, object interactions, or data transformations

If helpful, include:
- Simplified pseudocode versions of complex logic
- Diagrams or step-by-step execution flows
- Explanations of key variables and their purposes
- Context about libraries or frameworks being used

Please format your response with clear section headings and use code blocks with Python syntax highlighting where appropriate.
""",
        tags={"explanation", "understanding", "documentation", "learning", "complex code"}
    ))

    learning.add_prompt(Prompt(
        title="Provide Examples of Library or Framework Usage",
        text="""
I need examples of how to use [LIBRARY/FRAMEWORK] for the following task(s). 

LIBRARY/FRAMEWORK: [user to specify]
TASK(S): [user to describe what they're trying to accomplish]
MY EXPERIENCE LEVEL: [user to specify: beginner/intermediate/advanced]

As a library expert, please:

1. Provide clear, practical examples of using this library for the specified task(s)
2. Include explanations of the key concepts and components
3. Show best practices and common patterns
4. Explain any configuration or setup requirements
5. Highlight common pitfalls or gotchas to avoid

Examples should:
- Start simple and progress to more advanced usage if appropriate
- Include complete, runnable code snippets
- Show both basic usage and any relevant advanced features
- Cover error handling and edge cases
- Demonstrate idiomatic usage of the library/framework

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"examples", "library", "framework", "tutorial", "how-to"}
    ))

    learning.add_prompt(Prompt(
        title="Generate Educational Examples of Language Features",
        text="""
I need educational examples to understand the following Python feature or concept:

FEATURE/CONCEPT: [user to specify, e.g., decorators, context managers, metaclasses]
MY EXPERIENCE LEVEL: [user to specify: beginner/intermediate/advanced]

As a Python educator, please:

1. Explain the concept in clear, simple terms
2. Provide progressive examples from basic to advanced usage
3. Include practical, real-world use cases
4. Demonstrate best practices and common patterns
5. Highlight common mistakes or misunderstandings

Examples should:
- Be self-contained and runnable
- Include comments explaining key points
- Show both what to do and what not to do
- Demonstrate interactions with other Python features where relevant
- Include any relevant performance or design considerations

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"education", "examples", "language features", "learning", "tutorial"}
    ))

    learning.add_prompt(Prompt(
        title="Create System Architecture Diagrams or Explanations",
        text="""
I need to understand the architecture of the following system or codebase. Each file is separated by a line of asterisks (`*****`).

SPECIFIC AREAS OF INTEREST: [user to specify, or leave blank for a complete overview]

As a system architecture expert, please:

1. Analyze the code to identify key components, services, and their interactions
2. Explain the overall architecture and design patterns used
3. Describe data flow and control flow through the system
4. Identify key interfaces and their purposes
5. Explain any important architectural decisions or trade-offs

Include:
- High-level architecture description in text form
- Component relationships and dependencies
- Key classes/modules and their responsibilities
- Data storage and state management approaches
- External system integrations
- Any significant design patterns or architectural principles

If particular components are complex, please provide more detailed explanations of their internal structure and function.

Please format your response with clear section headings and use code blocks with Python syntax highlighting where appropriate.
""",
        tags={"architecture", "system design", "explanation", "components", "overview"}
    ))

    learning.add_prompt(Prompt(
        title="Summarize Large Codebases",
        text="""
I need a summary of the following large codebase to understand its structure and functionality. Each file is separated by a line of asterisks (`*****`).

SPECIFIC FOCUS AREAS: [user to specify, or leave blank for a complete summary]

As a code analysis expert, please:

1. Provide a high-level overview of the codebase's purpose and functionality
2. Break down the main components, modules, or packages and their responsibilities
3. Identify key classes, functions, or interfaces and their relationships
4. Explain the overall architecture and design patterns used
5. Highlight any notable algorithms, techniques, or approaches

Include:
- Package/module organization and structure
- Dependency relationships between components
- Main entry points and execution flow
- Core data structures and their purposes
- Testing approach and coverage (if visible)
- Potential areas of complexity or technical debt

Please format your response with clear section headings and use code blocks with Python syntax highlighting where appropriate.
""",
        tags={"codebase", "summary", "overview", "analysis", "structure"}
    ))

    # ==================== INTEGRATION AND EXTENSION ====================

    integration.add_prompt(Prompt(
        title="Integrate Third-Party APIs",
        text="""
I need to integrate the [API_NAME] API into the following Python code. Each file is separated by a line of asterisks (`*****`).

API: [user to specify which API]
INTEGRATION REQUIREMENTS: [user to describe what they need to accomplish]
API DOCUMENTATION: [user to provide link or details, if available]

As an API integration expert, please:

1. Implement the integration with the specified API
2. Handle authentication, requests, and responses properly
3. Include appropriate error handling and retry logic
4. Ensure the integration is robust and maintainable
5. Follow best practices for the specific API

Consider:
- Rate limiting and quotas
- Authentication and security
- Data validation and transformation
- Async vs. sync API calls
- Caching strategies if appropriate
- Logging and monitoring

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"API", "integration", "third-party", "requests", "http"}
    ))

    integration.add_prompt(Prompt(
        title="Add New Features to Existing Codebase",
        text="""
I need to add the following new feature to this existing Python codebase. Each file is separated by a line of asterisks (`*****`).

NEW FEATURE: [user to describe the feature]
REQUIREMENTS: [user to list specific requirements]

As a Python feature development expert, please:

1. Analyze the existing code to understand its structure and patterns
2. Design and implement the new feature to integrate seamlessly
3. Follow the existing code style and architecture
4. Add appropriate tests, documentation, and type hints
5. Ensure the new code doesn't break existing functionality

Consider:
- How the feature fits into the existing architecture
- Maintaining compatibility with existing interfaces
- Following established patterns in the codebase
- Performance and scalability implications
- Error handling and edge cases

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"feature", "development", "enhancement", "implementation", "extension"}
    ))

    integration.add_prompt(Prompt(
        title="Create Adapters Between Systems",
        text="""
I need to create an adapter between the following two systems or interfaces. Each file is separated by a line of asterisks (`*****`).

SYSTEM A: [user to describe first system/interface]
SYSTEM B: [user to describe second system/interface]
REQUIREMENTS: [user to describe integration needs]

As a systems integration expert, please:

1. Design and implement an adapter that connects these systems
2. Handle data transformation and mapping between different formats
3. Include robust error handling and logging
4. Ensure the adapter is maintainable and testable
5. Address any performance considerations

Consider:
- Differences in data models and how to map between them
- Synchronous vs. asynchronous communication needs
- Error propagation and recovery
- Validation and data integrity checks
- Configuration and flexibility needs
- Monitoring and observability

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"adapter", "integration", "interface", "systems", "interoperability"}
    ))

    integration.add_prompt(Prompt(
        title="Extend Classes with New Functionality",
        text="""
I need to extend the following class(es) with new functionality while preserving backward compatibility. Each file is separated by a line of asterisks (`*****`).

NEW FUNCTIONALITY: [user to describe what needs to be added]
COMPATIBILITY REQUIREMENTS: [user to specify any compatibility constraints]

As an object-oriented design expert, please:

1. Analyze the existing class(es) and their current interface
2. Extend the class(es) with the requested functionality
3. Maintain backward compatibility with existing code
4. Add appropriate tests, documentation, and type hints
5. Follow good OO design principles

Consider:
- Using inheritance, composition, or decoration appropriately
- Interface design and backward compatibility
- Method signatures and default parameters
- Adding new capabilities without changing existing behavior
- Handling potential edge cases or conflicts

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"extension", "class", "object-oriented", "inheritance", "compatibility"}
    ))

    # ==================== DEVOPS AND INFRASTRUCTURE ====================

    devops.add_prompt(Prompt(
        title="Write Configuration Files",
        text="""
I need to create configuration files (e.g., Docker, CI/CD) for the following Python project. Each file is separated by a line of asterisks (`*****`).

PROJECT TYPE: [user to specify - web app, library, etc.]
CONFIGURATION NEEDED: [user to specify - Docker, CI/CD, etc.]
REQUIREMENTS: [user to list specific requirements]

As a DevOps configuration expert, please:

1. Create appropriate configuration files for the specified needs
2. Follow best practices for the selected technologies
3. Include comprehensive comments explaining key configuration choices
4. Address common security and performance concerns
5. Provide a complete working solution

Depending on the requirements, include:
- Dockerfile(s) and docker-compose files
- CI/CD pipeline configurations (GitHub Actions, GitLab CI, etc.)
- Environment configurations and secrets management
- Testing, linting, and security scanning setup
- Deployment configurations

Please format your response with clear section headings and use code blocks with appropriate syntax highlighting.
""",
        tags={"configuration", "docker", "CI/CD", "DevOps", "infrastructure"}
    ))

    devops.add_prompt(Prompt(
        title="Create Infrastructure as Code",
        text="""
I need infrastructure as code (IaC) for the following Python application. Each file is separated by a line of asterisks (`*****`).

APPLICATION TYPE: [user to specify]
CLOUD PROVIDER(S): [user to specify - AWS, Azure, GCP, etc.]
IaC TOOL: [user to specify - Terraform, CloudFormation, Pulumi, etc.]
REQUIREMENTS: [user to list specific requirements]

As an infrastructure as code expert, please:

1. Create IaC configuration for the specified application and requirements
2. Follow cloud provider and IaC tool best practices
3. Include comprehensive comments explaining the infrastructure design
4. Address security, scalability, and cost considerations
5. Organize resources logically and with proper dependencies

Include configurations for relevant resources such as:
- Compute resources (VMs, containers, serverless)
- Storage (object storage, databases)
- Networking (VPCs, subnets, security groups)
- IAM and security settings
- Monitoring and logging
- CI/CD integration

Please format your response with clear section headings and use code blocks with appropriate syntax highlighting.
""",
        tags={"IaC", "Terraform", "CloudFormation", "infrastructure", "cloud"}
    ))

    devops.add_prompt(Prompt(
        title="Generate Deployment Scripts",
        text="""
I need deployment scripts or automation for the following Python application. Each file is separated by a line of asterisks (`*****`).

APPLICATION TYPE: [user to specify]
DEPLOYMENT TARGET: [user to specify - Kubernetes, serverless, VMs, etc.]
REQUIREMENTS: [user to list specific requirements]

As a deployment automation expert, please:

1. Create deployment scripts or configurations for the specified application
2. Ensure the deployment is automated, reliable, and repeatable
3. Include best practices for the target deployment environment
4. Address concerns like zero-downtime deployment, rollbacks, and monitoring
5. Add comprehensive comments and documentation

Consider including:
- Deployment manifests (Kubernetes YAML, serverless config, etc.)
- Shell scripts for deployment steps
- Configuration management
- Environment-specific configurations
- Health checks and validation steps
- Rollback procedures

Please format your response with clear section headings and use code blocks with appropriate syntax highlighting.
""",
        tags={"deployment", "automation", "Kubernetes", "serverless", "scripts"}
    ))

    # ==================== SECURITY AND COMPLIANCE ====================

    security.add_prompt(Prompt(
        title="Identify and Fix Security Vulnerabilities",
        text="""
I need to identify and fix security vulnerabilities in the following Python code. Each file is separated by a line of asterisks (`*****`).

CONTEXT: [user to provide any specific security concerns]

As a Python security expert, please:

1. Analyze the code for potential security vulnerabilities
2. Identify and explain each security issue found
3. Provide fixed code that addresses the vulnerabilities
4. Explain the security improvements and best practices applied
5. Suggest additional security measures where appropriate

Look for vulnerabilities such as:
- Injection vulnerabilities (SQL, command, etc.)
- Authentication and authorization flaws
- Sensitive data exposure
- Insecure cryptographic implementations
- CSRF, XSS, and other web vulnerabilities if applicable
- Insecure deserialization
- Dependency vulnerabilities
- Path traversal and file access issues

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"security", "vulnerabilities", "secure coding", "penetration testing"}
    ))

    security.add_prompt(Prompt(
        title="Implement Security Best Practices",
        text="""
I need to implement security best practices for authentication and authorization in the following Python code. Each file is separated by a line of asterisks (`*****`).

APPLICATION TYPE: [user to specify - web app, API, etc.]
SECURITY REQUIREMENTS: [user to list specific requirements]

As a security implementation expert, please:

1. Analyze the existing code and identify security gaps
2. Implement robust authentication and authorization mechanisms
3. Apply security best practices appropriate for the application type
4. Ensure secure handling of sensitive data
5. Provide clear explanations of the security improvements

Consider implementing:
- Secure password handling and storage
- Multi-factor authentication where appropriate
- Proper session management
- Role-based or attribute-based access control
- Input validation and output encoding
- CSRF protection for web applications
- Rate limiting and brute force protection
- Secure communication (TLS, etc.)

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"security", "authentication", "authorization", "RBAC", "secure coding"}
    ))

    security.add_prompt(Prompt(
        title="Make Code Compliant with Standards",
        text="""
I need to make the following Python code compliant with [STANDARD/REGULATION]. Each file is separated by a line of asterisks (`*****`).

STANDARD/REGULATION: [user to specify - GDPR, HIPAA, PCI DSS, etc.]
SPECIFIC REQUIREMENTS: [user to list specific compliance needs]

As a compliance and security expert, please:

1. Analyze the code for compliance gaps with the specified standard
2. Explain the specific compliance issues identified
3. Modify the code to address these compliance requirements
4. Provide documentation on the compliance measures implemented
5. Suggest any additional steps needed beyond code changes

Consider aspects such as:
- Data privacy and protection measures
- Audit logging and traceability
- Access controls and authentication
- Data retention and deletion
- Encryption requirements
- User consent mechanisms
- Documentation and policy requirements

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"compliance", "regulations", "GDPR", "HIPAA", "standards"}
    ))

    # ==================== SPECIALIZED TASKS ====================

    specialized.add_prompt(Prompt(
        title="Write SQL Queries or Database Migrations",
        text="""
I need to create SQL queries or database migrations for the following scenario in Python. Each file is separated by a line of asterisks (`*****`).

DATABASE TYPE: [user to specify - PostgreSQL, MySQL, SQLite, etc.]
REQUIREMENT: [user to describe query or migration needs]

As a database expert, please:

1. Create efficient SQL queries or migration scripts for the specified requirements
2. Ensure proper indexing, constraints, and performance considerations
3. If using an ORM, provide both raw SQL and ORM versions
4. Explain the query design and any performance optimizations
5. Include appropriate error handling and transaction management

Consider:
- Query performance and execution plans
- Database-specific features and syntax
- Proper data types and constraints
- Migration safety and reversibility
- Transaction isolation levels
- Indexing strategy

Please format your response with clear section headings and use code blocks with appropriate SQL and Python syntax highlighting.
""",
        tags={"SQL", "database", "migrations", "queries", "ORM"}
    ))

    specialized.add_prompt(Prompt(
        title="Create Regular Expressions",
        text="""
I need to create regular expressions in Python for the following pattern matching requirements:

PATTERNS TO MATCH: [user to describe what needs to be matched]
EXAMPLES: [user to provide example strings]

As a regex expert, please:

1. Create efficient and accurate regular expressions for the specified patterns
2. Explain the regex pattern components and how they work
3. Provide Python code demonstrating the regex in use
4. Include test cases showing matches and non-matches
5. Consider edge cases and potential pitfalls

The solution should:
- Be as readable as possible while being accurate
- Handle edge cases appropriately
- Use appropriate regex flags (case insensitivity, multiline, etc.)
- Include comments explaining complex parts
- Follow Python best practices for regex usage

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"regex", "regular expressions", "pattern matching", "text processing"}
    ))

    specialized.add_prompt(Prompt(
        title="Develop Data Processing Pipelines",
        text="""
I need to create a data processing or ETL pipeline in Python for the following requirements:

DATA SOURCE(S): [user to specify]
DATA TRANSFORMATION: [user to describe]
DATA DESTINATION: [user to specify]
ADDITIONAL REQUIREMENTS: [user to list any specific needs]

As a data pipeline expert, please:

1. Design an efficient data processing pipeline architecture
2. Implement the pipeline with appropriate error handling and logging
3. Include data validation and quality checks
4. Consider performance, scalability, and maintainability
5. Provide clear documentation of the pipeline components

Consider using relevant technologies such as:
- Pandas, NumPy, or other data processing libraries
- Parallel processing where appropriate
- Streaming vs. batch processing considerations
- Appropriate file formats and compression
- Checkpointing and pipeline resumability
- Monitoring and error notification

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"data pipeline", "ETL", "data processing", "pandas", "data engineering"}
    ))

    specialized.add_prompt(Prompt(
        title="Build Parsers or Interpreters",
        text="""
I need to build a parser or interpreter for a domain-specific language in Python:

LANGUAGE/FORMAT DESCRIPTION: [user to describe the language or format]
EXAMPLE INPUT: [user to provide sample input]
REQUIREMENTS: [user to list specific requirements]

As a parsing and compiler expert, please:

1. Design and implement a parser for the specified language/format
2. Create appropriate abstract syntax tree (AST) or data representation
3. Implement the interpreter or processor for the parsed structure
4. Include comprehensive error handling and reporting
5. Provide example usage and test cases

Consider using:
- Parser libraries (like ANTLR, PLY, lark) or hand-written parsers
- Appropriate design patterns for interpreters/compilers
- Efficient algorithms for parsing and processing
- Clear separation of lexing, parsing, and evaluation
- Good error messages and debugging support

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"parser", "interpreter", "compiler", "DSL", "language design"}
    ))

    specialized.add_prompt(Prompt(
        title="Implement Machine Learning Model Serving",
        text="""
I need to create code to serve a machine learning model in Python:

MODEL TYPE: [user to specify]
SERVING REQUIREMENTS: [user to describe deployment needs]
PERFORMANCE CONSTRAINTS: [user to specify any constraints]

As a machine learning deployment expert, please:

1. Implement code to load, serve, and make predictions with the specified ML model
2. Create appropriate API endpoints or interfaces
3. Include input validation and preprocessing
4. Implement performance optimizations (caching, batching, etc.)
5. Add monitoring, logging, and error handling

Consider:
- Model serialization and loading approaches
- Serving infrastructure (FastAPI, Flask, TensorFlow Serving, etc.)
- Scaling and performance considerations
- Input/output data handling and validation
- Model versioning and A/B testing if relevant
- Monitoring model drift and performance metrics

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"machine learning", "model serving", "ML deployment", "inference", "API"}
    ))

    specialized.add_prompt(Prompt(
        title="Optimize Code for Specific Hardware",
        text="""
I need to optimize the following Python code for specific hardware or constraints:

TARGET HARDWARE: [user to specify - GPU, embedded system, etc.]
CONSTRAINTS: [user to describe memory, CPU, or other limitations]
CODE PURPOSE: [user to describe what the code does]

As a performance optimization expert, please:

1. Analyze the code for optimization opportunities for the target hardware
2. Implement optimizations while maintaining the code's functionality
3. Explain the optimization techniques and their expected impact
4. Consider trade-offs between readability, maintainability, and performance
5. Suggest any additional libraries or tools that could help

Optimization areas might include:
- Vectorization and parallelization
- Memory usage and data structures
- Algorithm selection for the specific hardware
- Use of specialized libraries (NumPy, CuPy, etc.)
- Code compilation or JIT techniques
- Hardware-specific optimizations

Please format your response with clear section headings and use code blocks with Python syntax highlighting.
""",
        tags={"optimization", "hardware", "performance", "GPU", "embedded", "parallel"}
    ))

    return library



# Example usage
if __name__ == "__main__":
    # Create and populate the library
    prompt_library = create_programmer_assistance_library()

    # Save to JSON for persistence
    prompt_library.save_to_json("programming_prompts.json")

    # Example of accessing a prompt
    prompt = prompt_library.get_full_prompt(
        "Bug Fixing and Debugging",
        "Fix Specific Bug with Error Messages"
    )

    if prompt:
        print("Example Prompt:")
        print(prompt)
