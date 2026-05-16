# project_profiles.py

"""
Project profile system for the AI Programming Assistant.

Defines the ProjectProfile dataclass, built-in profile factories (Python, SPFx),
the ProfileManager for loading/saving/listing profiles, and an auto-detection
function for inferring project type from a directory's contents.

Profiles encapsulate everything that varies between project types:
  - Excluded directories (e.g., __pycache__ vs node_modules)
  - Default file type selections
  - Module marker files (e.g., __init__.py vs index.ts)
  - Entry point patterns (e.g., main.py vs *WebPart.ts)
  - File size limits
  - Default AI instructions text
  - Always-excluded extensions (e.g., .map for SPFx source maps)
"""

from __future__ import annotations

import fnmatch
import json
import pathlib
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Default instruction texts (inline; could be externalized later)
# ---------------------------------------------------------------------------

_PYTHON_INSTRUCTIONS = """\
You will be provided with multiple Python code snippets separated by a line of asterisks (`*`). Your task is to act as an expert Python developer with 20 years of experience and refine these code snippets.

**General Instructions:**

1.  **Maintain Existing Comments:** When modifying existing code, *do not remove* any existing comments. These comments may provide context or represent requirements that are important.
2.  **Professional Code Quality:** New code you write must adhere to professional standards expected of an experienced developer. This includes, but is not limited to:
    *   **Classes and Object-Oriented Design:** Use classes and object-oriented programming principles appropriately when it simplifies structuring data and actions.
    *   **Meaningful Names:** Use variable, function, and class names that are clear, concise, and descriptive of their purpose.
    *   **Docstrings:** Provide comprehensive docstrings for all functions, methods, classes, and modules. Use Google or NumPy style docstrings.
    *   **Type Hints:** Use type hints throughout the code (PEP 484/585/649) to improve readability and enable static analysis.
    *   **Modularity and Reusability:** Break down complex tasks into smaller, manageable functions or classes.
    *   **Error Handling:** Implement robust error handling using `try...except` blocks where appropriate. Provide informative error messages.
    *   **Follow PEP 8:** Adhere to Python style guidelines for code formatting (consistent indentation, line lengths, spacing).
    *   **Efficiency:** Consider performance implications and choose efficient algorithms and data structures.
    *   **Testing:** Consider how the code could be tested. If it adds value, create simple tests to ensure proper functionality.
    *   **Conciseness:** Write simple, easy to understand code. Avoid overly clever implementations.
3.  **Respect Boundaries:** Each code snippet you provide should function as a standalone block. Do not provide unnecessary context about one block when responding to a different block.
4.  **Existing code is not perfectly designed.** You are expected to find the problems and fix them.
5.  **If you don't understand the code or the goal of it:** Ask questions.
6.  **If you need to return code in segments due to your context window limits, break the code into chunks and prompt the user that you will return the next chunk when ready.**

Here is the code for the current Python program being worked on:
"""

_SPFX_INSTRUCTIONS = """\
You will be provided with multiple TypeScript/SPFx code snippets separated by a line of asterisks (`*`). Your task is to act as an expert SharePoint Framework (SPFx) developer with deep TypeScript and React experience and refine these code snippets.

**General Instructions:**

1.  **Maintain Existing Comments:** When modifying existing code, *do not remove* any existing comments. These comments may provide context or represent requirements that are important.
2.  **Professional Code Quality:** New code you write must adhere to professional standards expected of an experienced SPFx developer. This includes, but is not limited to:
    *   **TypeScript Types:** Use explicit interfaces, type aliases, and generics. Avoid `any` unless absolutely necessary; prefer `unknown` with type guards. Enable and respect `strict` mode.
    *   **TSDoc/JSDoc Comments:** Provide TSDoc comments for all exported functions, classes, interfaces, and components, describing purpose, parameters, return values, and side effects.
    *   **React Component Patterns:** Use functional components with hooks. Define explicit `Props` interfaces. Apply `React.memo`, `useMemo`, and `useCallback` only where measurement justifies the complexity.
    *   **SPFx Lifecycle:** Respect the SPFx lifecycle — `onInit` for initialization, `render` for rendering, property pane configuration via `getPropertyPaneConfiguration`. Dispose of resources properly.
    *   **PnPjs for SharePoint Data:** Use `@pnp/sp` for SharePoint REST operations rather than raw `fetch` calls. Handle errors with typed catches.
    *   **Module Imports:** Use ES module `import` statements, not CommonJS `require`. Prefer named imports for tree-shaking.
    *   **Accessibility:** Ensure components have appropriate ARIA labels, semantic HTML, and keyboard navigation. SPFx solutions deployed to SharePoint must meet accessibility requirements.
    *   **JSX in .tsx Files:** Preserve JSX syntax exactly as written — do not escape JSX into string templates or HTML entities.
    *   **Modularity and Reusability:** Separate presentation components from data fetching/services. Co-locate component, styles, and tests where appropriate.
    *   **Error Handling:** Use `try/catch` with typed error handling. Surface user-friendly messages while logging diagnostic detail.
    *   **Bundle Size:** Avoid importing entire libraries when only a few exports are needed. Prefer specific imports (`import { X } from 'lib'`).
    *   **Style Conventions:** Follow ESLint and Prettier conventions enforced by the SPFx generator. Use SCSS modules for component-scoped styles.
    *   **Conciseness:** Write clear, readable code over excessively clever implementations.
3.  **Respect Boundaries:** Each code snippet you provide should function as a standalone block.
4.  **Existing code is not perfectly designed.** You are expected to find the problems and fix them.
5.  **If you don't understand the code or the goal of it:** Ask questions.
6.  **If you need to return code in segments due to your context window limits, break the code into chunks and prompt the user that you will return the next chunk when ready.**

Here is the code for the current SPFx project being worked on:
"""


# ---------------------------------------------------------------------------
# ProjectProfile dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProjectProfile:
    """
    Immutable description of a project type's collection and presentation rules.

    Attributes:
        name: Short, filesystem-safe identifier (also used as profile filename).
        display_name: Human-readable name shown in the UI dropdown.
        excluded_dirs: Directory names skipped during file collection.
        default_file_types: Mapping of extension (with leading dot) to default
            checkbox state when this profile is selected.
        module_markers: File names that mark a directory as a "module" for the
            "Select Modules" feature (e.g., __init__.py, index.ts).
        entry_point_patterns: fnmatch patterns identifying likely main/entry
            files; used to prioritize the main-file dropdown.
        file_size_limits: Per-extension byte limits for inclusion (truncated
            beyond this size). Use 0 to indicate no read.
        default_instructions: Default text for the AI instructions textarea.
        always_excluded_extensions: Extensions that are never included
            regardless of checkbox state (e.g., .map source maps).
        is_builtin: True for the framework-provided profiles; False for
            user-saved custom profiles.
    """

    name: str
    display_name: str
    excluded_dirs: frozenset[str]
    default_file_types: dict[str, bool]
    module_markers: frozenset[str]
    entry_point_patterns: list[str]
    file_size_limits: dict[str, int]
    default_instructions: str
    always_excluded_extensions: frozenset[str] = field(default_factory=frozenset)
    is_builtin: bool = False

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "excluded_dirs": sorted(self.excluded_dirs),
            "default_file_types": dict(self.default_file_types),
            "module_markers": sorted(self.module_markers),
            "entry_point_patterns": list(self.entry_point_patterns),
            "file_size_limits": dict(self.file_size_limits),
            "default_instructions": self.default_instructions,
            "always_excluded_extensions": sorted(self.always_excluded_extensions),
            "is_builtin": False,  # Custom profiles are never built-in.
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectProfile":
        """Deserialize from a JSON-compatible dictionary."""
        return cls(
            name=data["name"],
            display_name=data.get("display_name", data["name"]),
            excluded_dirs=frozenset(data.get("excluded_dirs", [])),
            default_file_types=dict(data.get("default_file_types", {})),
            module_markers=frozenset(data.get("module_markers", [])),
            entry_point_patterns=list(data.get("entry_point_patterns", [])),
            file_size_limits=dict(data.get("file_size_limits", {})),
            default_instructions=data.get("default_instructions", ""),
            always_excluded_extensions=frozenset(
                data.get("always_excluded_extensions", [])
            ),
            is_builtin=False,
        )


# ---------------------------------------------------------------------------
# Built-in profile factories
# ---------------------------------------------------------------------------

def python_profile() -> ProjectProfile:
    """Return the built-in Python project profile."""
    return ProjectProfile(
        name="Python",
        display_name="Python",
        excluded_dirs=frozenset({
            "__pycache__", ".git", ".idea", "venv", ".venv", "env",
            ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
            "dist", "build", "node_modules",
        }),
        default_file_types={
            ".py": True,
            ".pyw": True,
            ".toml": True,
            ".cfg": True,
            ".ini": True,
            ".txt": True,
            ".md": True,
            ".rst": True,
            ".yaml": True,
            ".yml": True,
            ".json": True,
            ".xml": False,
            # SPFx extensions present so the checkbox UI is consistent across
            # profiles; default off for Python projects.
            ".ts": False,
            ".tsx": False,
            ".scss": False,
            ".css": False,
            ".html": False,
            ".js": False,
            ".jsx": False,
        },
        module_markers=frozenset({"__init__.py"}),
        entry_point_patterns=[
            "main.py", "app.py", "manage.py", "wsgi.py", "asgi.py",
            "__main__.py", "run.py", "cli.py",
        ],
        file_size_limits={
            ".json": 5120,
            ".xml": 5120,
        },
        default_instructions=_PYTHON_INSTRUCTIONS,
        always_excluded_extensions=frozenset({".pyc", ".pyo"}),
        is_builtin=True,
    )


def spfx_profile() -> ProjectProfile:
    """Return the built-in SharePoint Framework (SPFx) project profile."""
    return ProjectProfile(
        name="SPFx",
        display_name="SPFx (SharePoint Framework)",
        excluded_dirs=frozenset({
            ".git", "node_modules", "dist", "lib", "coverage",
            ".cache", ".temp", "temp", "obj", "release", "sharepoint",
            ".heft", "release-notes",
            # Keep Python exclusions for mixed repos.
            "__pycache__", ".idea", "venv", ".venv", ".mypy_cache",
        }),
        default_file_types={
            ".ts": True,
            ".tsx": True,
            ".scss": True,
            ".css": True,
            ".html": True,
            ".json": True,
            ".yaml": True,
            ".yml": True,
            ".md": True,
            ".txt": True,
            ".xml": True,
            ".js": False,         # Usually generated/bundled.
            ".jsx": False,
            ".py": False,
            ".pyw": False,
            ".toml": False,
            ".cfg": False,
            ".ini": False,
            ".rst": False,
        },
        module_markers=frozenset({"index.ts", "index.tsx"}),
        entry_point_patterns=[
            "*WebPart.ts",
            "*Extension.ts",
            "*CommandSet.ts",
            "*FormCustomizer.ts",
            "*ApplicationCustomizer.ts",
            "*FieldCustomizer.ts",
        ],
        file_size_limits={
            ".json": 10240,        # Larger limit; package.json/tsconfig.json.
            ".xml": 5120,
            ".scss": 8192,
            ".css": 8192,
            ".html": 8192,
        },
        default_instructions=_SPFX_INSTRUCTIONS,
        always_excluded_extensions=frozenset({
            ".map",                # JS/CSS source maps — never useful as context.
            ".min.js", ".min.css",
        }),
        is_builtin=True,
    )


# ---------------------------------------------------------------------------
# ProfileManager
# ---------------------------------------------------------------------------

class ProfileManager:
    """
    Manages built-in and user-defined project profiles.

    Built-ins are returned from in-memory factories; custom profiles are
    persisted as JSON files under `<config_dir>/profiles/<name>.json`.
    """

    def __init__(self, config_dir: pathlib.Path):
        """
        Args:
            config_dir: Application config directory (parent of profiles/).
        """
        self.config_dir = pathlib.Path(config_dir)
        self.profiles_dir = self.config_dir / "profiles"
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

        self._builtins: dict[str, ProjectProfile] = {
            "Python": python_profile(),
            "SPFx": spfx_profile(),
        }

    def list_profiles(self) -> list[str]:
        """Return all profile names (built-ins first, then sorted custom)."""
        builtin_names = list(self._builtins.keys())
        custom_names = sorted(
            p.stem for p in self.profiles_dir.glob("*.json")
            if p.stem not in self._builtins
        )
        return builtin_names + custom_names

    def load_profile(self, name: str) -> Optional[ProjectProfile]:
        """Load a profile by name. Returns None if not found."""
        if name in self._builtins:
            return self._builtins[name]

        path = self.profiles_dir / f"{name}.json"
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return ProjectProfile.from_dict(data)
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            print(f"Error loading custom profile '{name}': {exc}")
            return None

    def save_profile(self, profile: ProjectProfile) -> None:
        """
        Save a custom profile to disk.

        Raises:
            ValueError: If the name collides with a built-in or contains
                filesystem-unsafe characters.
        """
        if profile.name in self._builtins:
            raise ValueError(
                f"Cannot overwrite built-in profile: {profile.name}"
            )
        invalid = set('/\\:*?"<>|')
        if any(c in invalid for c in profile.name) or not profile.name.strip():
            raise ValueError(
                f"Profile name contains invalid characters or is empty: "
                f"{profile.name!r}"
            )

        path = self.profiles_dir / f"{profile.name}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(profile.to_dict(), f, indent=2)

    def delete_profile(self, name: str) -> None:
        """Delete a custom profile. Built-ins cannot be deleted."""
        if name in self._builtins:
            raise ValueError(f"Cannot delete built-in profile: {name}")
        path = self.profiles_dir / f"{name}.json"
        if path.exists():
            path.unlink()

    def is_builtin(self, name: str) -> bool:
        """Return True if the named profile is a built-in."""
        return name in self._builtins

    def all_known_extensions(self) -> list[str]:
        """
        Return the sorted union of file extensions across all profiles.

        Used to build a stable, comprehensive checkbox list independent of
        which profile is active.
        """
        exts: set[str] = set()
        for name in self.list_profiles():
            profile = self.load_profile(name)
            if profile is not None:
                exts.update(profile.default_file_types.keys())
        return sorted(exts)


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------

def detect_project_type(directory: pathlib.Path) -> Optional[str]:
    """
    Heuristically detect a project type from the top-level contents.

    Scans only the immediate directory (no deep recursion) for speed.
    Returns the profile name (e.g., "SPFx", "Python") or None if signals
    are absent or ambiguous.
    """
    directory = pathlib.Path(directory)
    if not directory.exists() or not directory.is_dir():
        return None

    spfx_score = 0
    python_score = 0

    # --- SPFx signals ---
    yo_rc = directory / ".yo-rc.json"
    if yo_rc.exists():
        try:
            with yo_rc.open("r", encoding="utf-8") as f:
                data = json.load(f)
            # Yeoman generators are top-level keys; check for SPFx generator.
            if any("generator-sharepoint" in str(k) for k in data.keys()):
                spfx_score += 10
        except (OSError, json.JSONDecodeError):
            pass

    package_json = directory / "package.json"
    if package_json.exists():
        try:
            with package_json.open("r", encoding="utf-8") as f:
                data = json.load(f)
            deps: dict = {}
            deps.update(data.get("dependencies", {}))
            deps.update(data.get("devDependencies", {}))
            if any(k.startswith("@microsoft/sp-") for k in deps.keys()):
                spfx_score += 8
            elif any(k.startswith("@microsoft/generator-sharepoint") for k in deps.keys()):
                spfx_score += 6
        except (OSError, json.JSONDecodeError):
            pass

    tsconfig = directory / "tsconfig.json"
    src_dir = directory / "src"
    if tsconfig.exists() and src_dir.is_dir():
        try:
            # Limit scan to immediate src/ subdirs to keep this fast.
            tsx_found = any(src_dir.rglob("*.tsx"))
            if tsx_found:
                spfx_score += 4
        except OSError:
            pass

    # --- Python signals ---
    if (directory / "setup.py").exists():
        python_score += 8
    if (directory / "pyproject.toml").exists():
        python_score += 8
    if (directory / "requirements.txt").exists():
        python_score += 6
    if (directory / "Pipfile").exists():
        python_score += 6

    # Fall back to top-level .py file presence only when no other signals exist.
    if python_score == 0 and not package_json.exists():
        try:
            if any(directory.glob("*.py")):
                python_score += 2
        except OSError:
            pass

    if spfx_score == 0 and python_score == 0:
        return None
    if spfx_score > python_score:
        return "SPFx"
    if python_score > spfx_score:
        return "Python"
    return None  # Ambiguous tie; let caller fall back.


def find_entry_points(
    file_list: list[pathlib.Path],
    profile: ProjectProfile,
) -> list[pathlib.Path]:
    """
    Return files matching any of the profile's entry-point fnmatch patterns.

    Used by the main-file dropdown to surface likely program entry points.
    """
    matches: list[pathlib.Path] = []
    seen: set[pathlib.Path] = set()
    for file_path in file_list:
        for pattern in profile.entry_point_patterns:
            if fnmatch.fnmatch(file_path.name, pattern):
                if file_path not in seen:
                    matches.append(file_path)
                    seen.add(file_path)
                break
    return matches