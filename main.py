# ai_programming_assistant.py

"""
AI Programming Assistant - A tool to prepare code for AI assistance.

Supports multiple project types via the project_profiles module:
  - Python (default for .py-based projects)
  - SPFx / SharePoint Framework (TypeScript + React)
  - User-defined custom profiles saved at runtime

Required packages:
- tkinter: Usually comes with Python
- pyperclip: For clipboard operations (pip install pyperclip)

For improved token counting:
- toksum: Multi-provider token counter (pip install toksum)
  (toksum uses tiktoken internally for OpenAI models)
"""

import os
import pathlib
import platform
import sys
import json
import threading
import tkinter as tk
import tkinter.messagebox as messagebox
from tkinter import ttk, filedialog, scrolledtext
from typing import List, Optional, Dict, Set

from ai_prompt_library import AIPromptLibrary, create_programmer_assistance_library
from project_profiles import (
    ProjectProfile,
    ProfileManager,
    detect_project_type,
    find_entry_points,
)

# For clipboard functionality
try:
    import pyperclip
except ImportError:
    class PyperclipFallback:
        def copy(self, text):
            print("Warning: pyperclip module not installed. Clipboard copy not available.")
            print("To enable clipboard functionality, install pyperclip: pip install pyperclip")


    pyperclip = PyperclipFallback()

# For token counting
try:
    import toksum
except ImportError:
    toksum = None

try:
    import tiktoken
except ImportError:
    tiktoken = None


# ---------------------------------------------------------------------------
# Sanitization Utility
# ---------------------------------------------------------------------------

def sanitize_output(text: str) -> str:
    """
    Sanitize text to remove potentially sensitive information.

    This function is code-aware: it only redacts values that are enclosed in
    quotes (string literals) to avoid mangling variable names or logic.
    """
    import re

    # Pattern format: (Key_Capture_Group)(Quote_Capture_Group)(Content)(Quote_Backreference)
    # Replacement format: \1\2[REDACTED]\2  (Preserves key and quotes)
    patterns = [
        # Common secret key-value pairs (quoted values only)
        (r'((?:api[_-]?key|password|secret|token|access[_-]?key|client[_-]?id|tenant[_-]?id|connection[_-]?string)\s*[:=]\s*)(["\'])(.*?)\2',
         r'\1\2[REDACTED]\2'),

        # Specific environment variable style assignments
        (r'(CLIENT_SECRET\s*=\s*)(["\'])(.*?)\2', r'\1\2[REDACTED_CLIENT_SECRET]\2'),
        (r'(redirect[_-]?uri\s*=\s*)(["\'])(.*?)\2', r'\1\2[REDACTED_URI]\2'),

        # GUIDs in quotes
        (r'(["\'])([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\1',
         r'\1[REDACTED_GUID]\1'),

        # URLs with embedded tokens/auth in quotes
        (r'(["\'])https?://[^"\'\s]+?(?:token|auth|key|secret|password)=[^"\'\s&]+\1',
         r'\1https://[REDACTED_URL_WITH_AUTH]\1'),

        # Emails (quoted)
        (r'(["\'])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\1',
         r'\1[REDACTED_EMAIL]\1'),

        # Generic IP Addresses (often unquoted in code, but generally safe to redact even if logic depends on it for security reasons)
        # If strict code-logic preservation is needed, this could be restricted to quotes only.
        (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[REDACTED_IP]'),
    ]

    sanitized = text
    for pattern, replacement in patterns:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    return sanitized


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class Config:
    """Manages configuration settings for the application."""

    def __init__(self):
        if platform.system() == "Windows":
            self.config_dir = os.path.join(
                os.environ["APPDATA"], "AIProgrammingAssistant"
            )
        else:
            self.config_dir = os.path.join(
                os.path.expanduser("~"), ".config", "AIProgrammingAssistant"
            )

        self.config_file = os.path.join(self.config_dir, "config.json")

        # Defaults.
        self.initial_dir = str(pathlib.Path.home())
        self.main_file = None
        self.selected_files: list = []
        self.last_prompt_category = ""
        self.last_prompt_title = ""
        self.last_llm_model = "gpt-4"

        # Profile-related state.
        self.last_profile = "Python"
        # Maps absolute directory path -> profile name.
        self.directory_profiles: Dict[str, str] = {}
        # Maps profile name -> {ext: bool} of user overrides vs profile defaults.
        self.file_type_overrides: Dict[str, Dict[str, bool]] = {}

        os.makedirs(self.config_dir, exist_ok=True)
        self.load_config()

    def load_config(self):
        """Load configuration from file if it exists."""
        try:
            if not os.path.exists(self.config_file):
                return

            with open(self.config_file, "r", encoding="utf-8") as f:
                config_data = json.load(f)

            self.initial_dir = config_data.get("initial_dir", self.initial_dir)
            self.main_file = config_data.get("main_file")
            self.last_prompt_category = config_data.get("last_prompt_category", "")
            self.last_prompt_title = config_data.get("last_prompt_title", "")
            self.last_llm_model = config_data.get("last_llm_model", self.last_llm_model)
            self.last_profile = config_data.get("last_profile", self.last_profile)
            self.directory_profiles = config_data.get("directory_profiles", {}) or {}
            self.file_type_overrides = config_data.get("file_type_overrides", {}) or {}

            # Backward compatibility: migrate legacy `selected_file_types` into
            # the Python profile's overrides if no new-style data is present.
            legacy_types = config_data.get("selected_file_types")
            if legacy_types and "Python" not in self.file_type_overrides:
                self.file_type_overrides["Python"] = dict(legacy_types)

            self.selected_files = []
            for file_path in config_data.get("selected_files", []):
                path = pathlib.Path(file_path)
                if path.exists():
                    self.selected_files.append(path)

        except Exception as exc:
            print(f"Error loading config: {exc}")

    def save_config(self, **updates):
        """
        Save configuration to file.

        Accepts keyword overrides matching attribute names. Unspecified values
        are preserved from the current instance state.
        """
        for key, value in updates.items():
            if value is None:
                continue
            if hasattr(self, key):
                if key == "initial_dir":
                    self.initial_dir = str(value)
                elif key == "main_file":
                    self.main_file = str(value) if value else None
                elif key == "selected_files":
                    self.selected_files = [str(f) for f in value]
                else:
                    setattr(self, key, value)

        config_data = {
            "initial_dir": self.initial_dir,
            "main_file": self.main_file,
            "selected_files": [str(f) for f in self.selected_files],
            "last_prompt_category": self.last_prompt_category,
            "last_prompt_title": self.last_prompt_title,
            "last_llm_model": self.last_llm_model,
            "last_profile": self.last_profile,
            "directory_profiles": self.directory_profiles,
            "file_type_overrides": self.file_type_overrides,
        }

        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2)
        except Exception as exc:
            print(f"Error saving config: {exc}")

    # --- Profile-related helpers ---

    def get_directory_profile(self, directory: pathlib.Path) -> Optional[str]:
        """Return the saved profile for a directory, or None."""
        return self.directory_profiles.get(str(pathlib.Path(directory).resolve()))

    def set_directory_profile(self, directory: pathlib.Path, profile_name: str):
        """Persist the directory -> profile mapping."""
        self.directory_profiles[str(pathlib.Path(directory).resolve())] = profile_name

    def get_file_type_overrides(self, profile_name: str) -> Dict[str, bool]:
        """Return saved overrides for a profile (empty dict if none)."""
        return dict(self.file_type_overrides.get(profile_name, {}))

    def set_file_type_overrides(
            self, profile_name: str, overrides: Dict[str, bool]
    ):
        """Replace overrides for a profile."""
        self.file_type_overrides[profile_name] = dict(overrides)


# ---------------------------------------------------------------------------
# CodeCompiler
# ---------------------------------------------------------------------------

class CodeCompiler:
    """Compiles selected files into a single AI-ready prompt."""

    def __init__(
            self,
            initial_wd: pathlib.Path,
            profile: ProjectProfile,
            output_filename: str = os.path.join(os.path.expanduser('~'), 'Desktop', "For AI Questions.txt"),
    ):
        self.initial_wd = initial_wd
        self.profile = profile
        self.output_filename = self.initial_wd / output_filename
        self._ensure_output_file_does_not_exist()
        self.compiled_content = ""
        self.file_size_limits = dict(profile.file_size_limits)

    def _ensure_output_file_does_not_exist(self) -> None:
        if self.output_filename.exists():
            os.unlink(self.output_filename)

    def add_ai_instructions(self, ai_prompt: str) -> None:
        """Write AI instructions as the file's leading section."""
        if ai_prompt.strip():
            self.compiled_content = f"### AI Instructions ###\n{ai_prompt}\n\n"
        else:
            self.compiled_content = ai_prompt
        with self.output_filename.open("w", encoding="utf-8") as outfile:
            outfile.write(self.compiled_content)

    def compile(
            self,
            files_to_compile: List[pathlib.Path],
            main_file: Optional[pathlib.Path] = None,
    ) -> None:
        """Append all selected files (main file first, if any)."""
        with self.output_filename.open("a", encoding="utf-8") as outfile:
            if main_file and main_file in files_to_compile:
                main_marker = f"The main program file is: {main_file.name}\n\n"
                outfile.write(main_marker)
                self.compiled_content += main_marker

                self._write_file_to_output(main_file, outfile)
                files_to_compile = [f for f in files_to_compile if f != main_file]

            for file in files_to_compile:
                self._write_file_to_output(file, outfile)

    def _write_file_to_output(self, filepath: pathlib.Path, outfile) -> None:
        """Write a single file with its header and (optional) truncation note."""
        # Compute a path relative to the project root; fall back to basename.
        try:
            relative_path = filepath.relative_to(self.initial_wd)
        except ValueError:
            relative_path = filepath.name

        try:
            suffix = filepath.suffix.lower()
            size_limit = self.file_size_limits.get(suffix)
            file_size = filepath.stat().st_size

            header = "*" * 80 + "\n" + f"Here is the code for the file: {relative_path}\n\n"
            outfile.write(header)
            self.compiled_content += header

            if size_limit and file_size > size_limit:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as infile:
                    file_content = infile.read(size_limit)
                    file_content += (
                        f"\n\n[Note: This file has been truncated to "
                        f"{size_limit // 1024}KB due to size constraints. "
                        f"Full size: {file_size // 1024}KB]"
                    )
            else:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as infile:
                    file_content = infile.read()

            outfile.write(file_content)
            self.compiled_content += file_content

            footer = "\n\n"
            outfile.write(footer)
            self.compiled_content += footer

        except UnicodeDecodeError:
            msg = f"Warning: Could not decode file: {filepath}. Skipping.\n"
            print(msg)
            self.compiled_content += msg
        except Exception as exc:
            msg = f"Error processing file {filepath}: {exc}\n"
            print(msg)
            self.compiled_content += msg

    def copy_to_clipboard(self) -> bool:
        """Copy the compiled content to the system clipboard."""
        try:
            pyperclip.copy(self.compiled_content)
            return True
        except Exception as exc:
            print(f"Error copying to clipboard: {exc}")
            return False


# ---------------------------------------------------------------------------
# SaveProfileDialog
# ---------------------------------------------------------------------------

class SaveProfileDialog:
    """Modal dialog for capturing a new profile name and saving it."""

    def __init__(self, parent: tk.Tk, profile_manager: ProfileManager):
        self.parent = parent
        self.profile_manager = profile_manager
        self.result: Optional[str] = None
        self.dialog: Optional[tk.Toplevel] = None
        self.name_var: Optional[tk.StringVar] = None

    def show(self) -> Optional[str]:
        """Display the dialog modally and return the chosen name (or None)."""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Save as Profile")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        self.dialog.resizable(False, False)

        # Center on the parent.
        self.dialog.update_idletasks()
        w, h = 460, 220
        x = self.parent.winfo_rootx() + (self.parent.winfo_width() - w) // 2
        y = self.parent.winfo_rooty() + (self.parent.winfo_height() - h) // 2
        self.dialog.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")

        frame = ttk.Frame(self.dialog, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text=(
                "Save current settings as a new profile.\n\n"
                "This captures the active profile's exclusion rules and module "
                "markers, plus your current file-type selections and AI "
                "instructions text."
            ),
            wraplength=420,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 10))

        ttk.Label(frame, text="Profile name:").pack(anchor=tk.W)
        self.name_var = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=self.name_var, width=40)
        entry.pack(fill=tk.X, pady=(2, 10))
        entry.focus_set()

        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X)

        ttk.Button(button_frame, text="Cancel", command=self._cancel).pack(
            side=tk.RIGHT, padx=5
        )
        ttk.Button(button_frame, text="Save", command=self._save).pack(
            side=tk.RIGHT, padx=5
        )

        self.dialog.bind("<Return>", lambda _e: self._save())
        self.dialog.bind("<Escape>", lambda _e: self._cancel())
        self.dialog.protocol("WM_DELETE_WINDOW", self._cancel)

        self.parent.wait_window(self.dialog)
        return self.result

    def _save(self):
        name = (self.name_var.get() or "").strip()
        if not name:
            messagebox.showwarning(
                "Invalid Name", "Profile name cannot be empty.",
                parent=self.dialog,
            )
            return

        if self.profile_manager.is_builtin(name):
            messagebox.showerror(
                "Invalid Name",
                f"'{name}' is a built-in profile name. Choose a different name.",
                parent=self.dialog,
            )
            return

        invalid = set('/\\:*?"<>|')
        if any(c in invalid for c in name):
            messagebox.showerror(
                "Invalid Name",
                f"Profile name contains invalid characters: {''.join(sorted(invalid))}",
                parent=self.dialog,
            )
            return

        # Confirm overwrite if a custom profile already exists with this name.
        existing = self.profile_manager.load_profile(name)
        if existing is not None and not existing.is_builtin:
            confirm = messagebox.askyesno(
                "Overwrite Profile",
                f"A custom profile named '{name}' already exists. Overwrite it?",
                parent=self.dialog,
            )
            if not confirm:
                return

        self.result = name
        self.dialog.destroy()

    def _cancel(self):
        self.result = None
        self.dialog.destroy()


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class AIProgrammingAssistantDialog:
    """File-tree, profile, and prompt selection dialog."""

    def __init__(
            self,
            profile_manager: ProfileManager,
            initial_profile: ProjectProfile,
            config: Config,
            title: str = "AI Programming Assistant",
            width: int = 900,
            height: int = 700,
    ):
        self.profile_manager = profile_manager
        self.current_profile = initial_profile
        self.config = config
        self.title = title
        self.width = width
        self.height = height

        self.result: dict = {
            "selected_files": [],
            "status": "cancel",
            "general_ai_instructions": "",
            "main_file": None,
            "profile": initial_profile,
            "sanitize_output": False,  # Added for OK button flow
        }

        self.item_id_to_path: Dict[str, pathlib.Path] = {}
        self.selected_items: Set[str] = set()
        self.root_dir: Optional[pathlib.Path] = None
        self.module_dirs: Set[pathlib.Path] = set()

        # Initial exclusion set from the active profile.
        self.excluded_dirs: Set[str] = set(initial_profile.excluded_dirs)
        self.show_full_paths = False

        self.root: Optional[tk.Tk] = None
        self.main_frame = None
        self.paned_window = None
        self.tree = None
        self.display_name_to_path: Dict[str, pathlib.Path] = {}

        self.prompt_library: AIPromptLibrary = create_programmer_assistance_library()
        self.category_var: Optional[tk.StringVar] = None
        self.prompt_var: Optional[tk.StringVar] = None
        self.category_dropdown = None
        self.prompt_dropdown = None
        self.current_category = None
        self.current_prompts: list = []
        self.initial_dir_files_prioritized = False

        # File type checkbox state (built once per dialog session over the
        # union of all known extensions, then check-states swapped per profile).
        self.file_type_vars: Dict[str, tk.BooleanVar] = {}
        self.all_extensions: list[str] = self.profile_manager.all_known_extensions()

        # Token counting.
        self.file_size_label = None
        self.token_count_label = None
        self.token_calc_thread: Optional[threading.Thread] = None
        self.cancel_calculation = False
        # Debounce timer ID for token recalculation; coalesces rapid triggers.
        self._token_recalc_after_id: Optional[str] = None
        self.supported_models = self._get_supported_llm_models()

        # Profile UI.
        self.profile_var: Optional[tk.StringVar] = None
        self.profile_dropdown = None
        self.sanitize_var: Optional[tk.BooleanVar] = None  # Added for checkbox
        self.instructions_manually_edited = False

    # ------------------------------------------------------------------
    # Token model list (unchanged from the original)
    # ------------------------------------------------------------------

    def _get_supported_llm_models(self):
        """Build the model list from toksum's registry, falling back to a
            minimal hard-coded list if toksum is not installed."""
        if toksum:
            try:
                models_by_provider = toksum.get_supported_models()
                # Flatten all provider lists into a single sorted list.
                all_models = sorted(set(
                    model
                    for models in models_by_provider.values()
                    for model in models
                ))
                if all_models:
                    return all_models
            except Exception as exc:
                print(f"Warning: could not read toksum model list: {exc}")

    # ------------------------------------------------------------------
    # Dialog lifecycle
    # ------------------------------------------------------------------

    def show(self, file_list, default_ai_instructions=""):
        """Display the dialog. Returns (files, status, instructions, main_file, profile, sanitize_flag)."""
        if file_list:
            self.root_dir = self._find_common_root([str(p) for p in file_list])

        self.result["selected_files"] = []
        self.result["status"] = "cancel"
        self.result["general_ai_instructions"] = default_ai_instructions
        self.result["main_file"] = None
        self.result["profile"] = self.current_profile
        self.result["sanitize_output"] = False

        try:
            self._identify_modules(file_list)
        except Exception as exc:
            print(f"Error identifying modules: {exc}")

        try:
            self.root = tk.Tk()
            self.root.title(self.title)
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after_idle(lambda: self.root.attributes("-topmost", False))

            if platform.system() == "Windows":
                self.root.focus_force()

            def safe_close():
                try:
                    self._on_exit()
                except Exception:
                    self.root.destroy()

            self.root.protocol("WM_DELETE_WINDOW", safe_close)
            self._calculate_window_size_and_position()
            self._create_widgets(file_list, default_ai_instructions)
            self.root.after(100, self._configure_window_size)
            # Kick off the initial token calculation once the UI has settled.
            # Using the debounced scheduler here ensures any selection-change
            # `after` calls fired during widget construction are coalesced into
            # a single calculation.
            self._schedule_token_recalc(delay_ms=300)
            self.root.mainloop()
        except Exception as exc:
            print(f"Error in dialog: {exc}")

        return (
            self.result["selected_files"],
            self.result["status"],
            self.result["general_ai_instructions"],
            self.result["main_file"],
            self.result["profile"],
            self.result["sanitize_output"],  # Return the checkbox state
        )

    def _calculate_window_size_and_position(self):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        top_margin, bottom_margin = 20, 100
        width = int(screen_width * 0.8)
        height = screen_height - top_margin - bottom_margin
        self.width = min(width, 1200)
        self.height = height
        x = (screen_width - self.width) // 2
        y = top_margin
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")

    def _configure_window_size(self):
        try:
            self.root.minsize(min(800, self.width), min(600, self.height))
            self._configure_resize_behavior()
        except Exception as exc:
            print(f"Error configuring window size: {exc}")

    def _configure_resize_behavior(self):
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(0, weight=1)
        self.main_frame.columnconfigure(0, weight=1)

    def _identify_modules(self, file_list: List[pathlib.Path]):
        """Use the active profile's module markers to identify module dirs."""
        markers = self.current_profile.module_markers
        dirs: Set[pathlib.Path] = set()
        for file_path in file_list:
            if file_path.name in markers:
                dirs.add(file_path.parent)

        self.module_dirs = set(dirs)
        checked_dirs: Set[pathlib.Path] = set()

        # Walk parents only for marker-based languages where nested modules
        # are conventional (e.g., Python packages).
        for dir_path in dirs:
            parent = dir_path.parent
            while (
                    parent.exists()
                    and parent not in checked_dirs
                    and (
                            self.root_dir is None
                            or self.root_dir in parent.parents
                            or parent == self.root_dir
                    )
            ):
                checked_dirs.add(parent)
                if any((parent / m).exists() for m in markers):
                    self.module_dirs.add(parent)
                parent = parent.parent

    def _find_common_root(self, paths: List[str]) -> pathlib.Path:
        if not paths:
            return pathlib.Path.cwd()
        return pathlib.Path(os.path.commonpath(paths))

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------

    def _create_widgets(self, file_list, default_ai_instructions):
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.paned_window = ttk.PanedWindow(self.main_frame, orient=tk.VERTICAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True)

        # --- Profile selection ---
        profile_frame = ttk.Frame(self.paned_window)
        self.paned_window.add(profile_frame, weight=0)
        self._create_profile_widgets(profile_frame)

        # --- File type checkboxes ---
        file_type_frame = ttk.Frame(self.paned_window)
        self.paned_window.add(file_type_frame, weight=0)
        self._create_file_type_checkboxes(file_type_frame)

        # --- Token / model row ---
        token_frame = ttk.Frame(self.paned_window)
        self.paned_window.add(token_frame, weight=0)
        self._create_token_counting_widgets(token_frame)

        # --- File tree ---
        file_frame = ttk.Frame(self.paned_window)
        self.paned_window.add(file_frame, weight=2)

        toolbar_frame = ttk.Frame(file_frame)
        toolbar_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(toolbar_frame, text="Select files to include:").pack(
            side=tk.LEFT, padx=(0, 10)
        )
        ttk.Button(toolbar_frame, text="Select All",
                   command=self._select_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar_frame, text="Deselect All",
                   command=self._deselect_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar_frame, text="Select Modules",
                   command=self._select_modules).pack(side=tk.LEFT, padx=2)

        self.full_path_var = tk.BooleanVar(value=self.show_full_paths)
        ttk.Checkbutton(
            toolbar_frame, text="Show Full Paths",
            variable=self.full_path_var, command=self._toggle_path_display,
        ).pack(side=tk.RIGHT, padx=5)

        self.exclude_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            toolbar_frame, text="Exclude System Dirs",
            variable=self.exclude_var, command=self._rebuild_tree,
        ).pack(side=tk.RIGHT, padx=5)

        self._create_tree_view(file_frame, file_list)

        # --- Main program file ---
        main_file_frame = ttk.Frame(self.paned_window)
        self.paned_window.add(main_file_frame, weight=0)
        ttk.Label(main_file_frame, text="Main Program File:").pack(
            anchor=tk.W, pady=(5, 5)
        )
        self.main_file_var = tk.StringVar()
        self.main_combobox = ttk.Combobox(
            main_file_frame, textvariable=self.main_file_var,
            width=60, state="readonly",
        )
        self.main_combobox.pack(fill=tk.X, pady=(0, 5))
        self.update_main_file_combobox()

        # --- Prompt category / specific prompt ---
        prompt_selection_frame = ttk.Frame(self.paned_window)
        self.paned_window.add(prompt_selection_frame, weight=0)
        prompt_selection_frame.columnconfigure(0, weight=0)
        prompt_selection_frame.columnconfigure(1, weight=1)

        ttk.Label(prompt_selection_frame, text="Prompt Category:").grid(
            row=0, column=0, sticky="w", padx=(0, 5), pady=(5, 5)
        )
        self.category_var = tk.StringVar()
        self.category_dropdown = ttk.Combobox(
            prompt_selection_frame, textvariable=self.category_var,
            width=40, state="readonly",
        )
        self.category_dropdown.grid(
            row=0, column=1, sticky="we", padx=(0, 5), pady=(5, 5)
        )
        categories = self.prompt_library.list_categories()
        self.category_dropdown["values"] = ["[Select a category]"] + categories
        self.category_dropdown.current(0)
        self.category_dropdown.bind("<<ComboboxSelected>>", self._on_category_selected)

        ttk.Label(prompt_selection_frame, text="Specific Prompt:").grid(
            row=1, column=0, sticky="w", padx=(0, 5), pady=(5, 5)
        )
        self.prompt_var = tk.StringVar()
        self.prompt_dropdown = ttk.Combobox(
            prompt_selection_frame, textvariable=self.prompt_var,
            width=40, state="disabled",
        )
        self.prompt_dropdown.grid(
            row=1, column=1, sticky="we", padx=(0, 5), pady=(5, 5)
        )
        self.prompt_dropdown.bind("<<ComboboxSelected>>", self._on_prompt_selected)

        # --- AI instructions ---
        ai_frame = ttk.Frame(self.paned_window)
        self.paned_window.add(ai_frame, weight=1)
        ai_frame.columnconfigure(0, weight=1)
        ai_frame.rowconfigure(1, weight=1)
        ttk.Label(ai_frame, text="General AI Instructions:").grid(
            row=0, column=0, sticky="w", pady=(5, 5)
        )
        self.ai_instructions_text = scrolledtext.ScrolledText(ai_frame, wrap=tk.WORD)
        self.ai_instructions_text.grid(row=1, column=0, sticky="nsew", pady=(0, 5))
        self.ai_instructions_text.insert(tk.END, default_ai_instructions)
        # Track manual edits AND trigger debounced token recount on each
        # keystroke. <KeyRelease> fires *after* the character has been inserted
        # into the widget, so the recount sees the post-edit text.
        self.ai_instructions_text.bind("<KeyRelease>", self._on_instructions_key)

        # --- Buttons ---
        button_frame = ttk.Frame(self.main_frame)
        button_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(button_frame, text="Compile and Close", command=self._on_ok).pack(
            side=tk.RIGHT, padx=5
        )
        ttk.Button(button_frame, text="Exit", command=self._on_exit).pack(
            side=tk.RIGHT, padx=5
        )
        ttk.Button(button_frame, text="Refresh Files", command=self._on_refresh).pack(
            side=tk.RIGHT, padx=5
        )
        ttk.Button(button_frame, text="Prompt to Clipboard", command=self._on_copy_prompt).pack(
            side=tk.RIGHT, padx=5
        )
        ttk.Button(button_frame, text="Compile", command=self._on_compile).pack(
            side=tk.RIGHT, padx=5
        )

        # Restore last-used prompt selection.
        if (self.config.last_prompt_category and self.config.last_prompt_title
                and self.config.last_profile == self.current_profile.name):
            if self.config.last_prompt_category in categories:
                self.category_dropdown.set(self.config.last_prompt_category)
                # Populate the specific-prompt dropdown without firing
                # _on_prompt_selected (which would clobber the instructions box).
                category = self.prompt_library.get_category(self.config.last_prompt_category)
                if category:
                    self.current_category = category
                    prompt_titles = category.list_prompts()
                    self.prompt_dropdown["values"] = prompt_titles
                    self.current_prompts = prompt_titles
                    if prompt_titles:
                        self.prompt_dropdown.configure(state="readonly")
                    if self.config.last_prompt_title in prompt_titles:
                        self.prompt_dropdown.set(self.config.last_prompt_title)

    # ------------------------------------------------------------------
    # Profile UI
    # ------------------------------------------------------------------

    def _create_profile_widgets(self, parent):
        """Create the profile dropdown and 'Save as Profile...' button."""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=5)

        ttk.Label(frame, text="Project Type:").pack(side=tk.LEFT, padx=(0, 5))

        self.profile_var = tk.StringVar(value=self.current_profile.name)
        self.profile_dropdown = ttk.Combobox(
            frame,
            textvariable=self.profile_var,
            values=self.profile_manager.list_profiles(),
            width=30,
            state="readonly",
        )
        self.profile_dropdown.pack(side=tk.LEFT, padx=(0, 10))
        self.profile_dropdown.set(self.current_profile.name)
        self.profile_dropdown.bind("<<ComboboxSelected>>", self._on_profile_changed)

        ttk.Button(
            frame, text="Save as Profile...", command=self._on_save_as_profile,
        ).pack(side=tk.LEFT, padx=5)

        active_label = ttk.Label(
            frame,
            text=f"Active: {self.current_profile.display_name}",
            foreground="gray",
        )
        active_label.pack(side=tk.LEFT, padx=10)

        # Added Sanitize Checkbox
        self.sanitize_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame, text="Sanitize Output", variable=self.sanitize_var
        ).pack(side=tk.LEFT, padx=10)

    def _on_instructions_key(self, _event):
        """Mark instructions as user-modified and debounce a token recount."""
        self.instructions_manually_edited = True
        # Slightly longer delay than checkbox/selection events: typing produces
        # bursts and we don't want to recount on every character.
        self._schedule_token_recalc(delay_ms=600)

    def _on_profile_changed(self, _event):
        """Handle a profile selection change."""
        new_name = self.profile_var.get()
        if new_name == self.current_profile.name:
            return

        new_profile = self.profile_manager.load_profile(new_name)
        if new_profile is None:
            messagebox.showerror(
                "Profile Error",
                f"Could not load profile '{new_name}'.",
            )
            self.profile_dropdown.set(self.current_profile.name)
            return

        # Confirm before overwriting manual edits to instructions.
        if self.instructions_manually_edited:
            confirm = messagebox.askyesno(
                "Replace Instructions?",
                "You've modified the AI instructions. Switching profiles will "
                "replace them with the new profile's defaults. Continue?",
            )
            if not confirm:
                self.profile_dropdown.set(self.current_profile.name)
                return

        self.current_profile = new_profile
        self.excluded_dirs = set(new_profile.excluded_dirs)

        # Apply new profile's checkbox defaults (with any saved overrides).
        overrides = self.config.get_file_type_overrides(new_profile.name)
        effective = dict(new_profile.default_file_types)
        effective.update(overrides)
        for ext, var in self.file_type_vars.items():
            var.set(effective.get(ext, False))

        # Replace instructions text with the new profile defaults.
        self.ai_instructions_text.delete("1.0", tk.END)
        self.ai_instructions_text.insert(tk.END, new_profile.default_instructions)
        self.instructions_manually_edited = False

        # Re-identify modules under new markers, rebuild tree.
        self._rebuild_tree_from_disk()
        self._schedule_token_recalc()

    def _on_save_as_profile(self):
        """Open the save-profile dialog and persist a snapshot."""
        dialog = SaveProfileDialog(self.root, self.profile_manager)
        new_name = dialog.show()
        if not new_name:
            return

        # Snapshot: current file-type checkbox states + current instructions.
        # Inherit non-UI fields (excluded_dirs, markers, etc.) from active profile.
        current_file_types = {
            ext: var.get() for ext, var in self.file_type_vars.items()
        }
        current_instructions = self.ai_instructions_text.get("1.0", tk.END).rstrip("\n")

        snapshot = ProjectProfile(
            name=new_name,
            display_name=new_name,
            excluded_dirs=self.current_profile.excluded_dirs,
            default_file_types=current_file_types,
            module_markers=self.current_profile.module_markers,
            entry_point_patterns=list(self.current_profile.entry_point_patterns),
            file_size_limits=dict(self.current_profile.file_size_limits),
            default_instructions=current_instructions,
            always_excluded_extensions=self.current_profile.always_excluded_extensions,
            is_builtin=False,
        )

        try:
            self.profile_manager.save_profile(snapshot)
        except (ValueError, OSError) as exc:
            messagebox.showerror(
                "Save Failed", f"Could not save profile:\n\n{exc}",
            )
            return

        # Refresh dropdown list, switch to the new profile.
        self.profile_dropdown["values"] = self.profile_manager.list_profiles()
        self.profile_dropdown.set(new_name)
        self.current_profile = snapshot
        # Newly-saved profile defaults match current UI; clear override entries.
        self.config.set_file_type_overrides(new_name, {})
        self.instructions_manually_edited = False

        messagebox.showinfo(
            "Profile Saved",
            f"Profile '{new_name}' saved successfully.\n\n"
            f"Custom profiles are stored under:\n{self.profile_manager.profiles_dir}",
        )

    # ------------------------------------------------------------------
    # Compile
    # ------------------------------------------------------------------

    def _on_compile(self):
        """Compile the selected files without closing the dialog."""
        try:
            selected_files = [
                self.item_id_to_path[item_id]
                for item_id in self.selected_items
                if item_id in self.item_id_to_path
            ]
            if not selected_files:
                messagebox.showwarning(
                    "No Files Selected",
                    "Please select at least one file to compile.",
                )
                return

            main_file_display = self.main_file_var.get()
            main_file = None
            if main_file_display and main_file_display != "[None]":
                main_file = self.display_name_to_path.get(main_file_display)

            instructions = self.ai_instructions_text.get("1.0", tk.END)

            # Save current state to config so if the user closes later, it's saved.
            current_category = self.category_var.get()
            current_prompt = self.prompt_var.get()

            self.config.set_directory_profile(self.root_dir, self.current_profile.name)
            self.config.save_config(
                initial_dir=self.root_dir,
                main_file=main_file,
                selected_files=selected_files,
                last_prompt_category=(
                    current_category if current_category != "[Select a category]" else ""
                ),
                last_prompt_title=current_prompt,
                last_llm_model=self.model_var.get(),
                last_profile=self.current_profile.name,
                directory_profiles=self.config.directory_profiles,
                file_type_overrides=self.config.file_type_overrides,
            )

            compiler = CodeCompiler(self.root_dir, self.current_profile)
            compiler.add_ai_instructions(instructions)
            compiler.compile(selected_files, main_file)

            # Apply sanitization if checked
            if self.sanitize_var.get():
                compiler.compiled_content = sanitize_output(compiler.compiled_content)
                # Overwrite the file with sanitized content
                with compiler.output_filename.open("w", encoding="utf-8") as outfile:
                    outfile.write(compiler.compiled_content)

            clipboard_success = compiler.copy_to_clipboard()

            message = (
                f"Successfully compiled {len(selected_files)} files to "
                f"'{compiler.output_filename}'.\n"
                f"Profile used: {self.current_profile.display_name}"
            )
            if self.sanitize_var.get():
                message += "\nOutput has been sanitized."
            if main_file:
                message += f"\nMain program file: {main_file.name}"
            if clipboard_success:
                message += "\nContent has been copied to clipboard."
            else:
                message += (
                    "\nNote: Could not copy to clipboard. "
                    "Install pyperclip module for clipboard support."
                )
            messagebox.showinfo("Compilation Complete", message)

        except Exception as exc:
            messagebox.showerror(
                "Error", f"An error occurred during compilation: {exc}"
            )

    def _on_refresh(self):
        """Refresh the file tree by re-walking the filesystem."""
        self._rebuild_tree_from_disk()

    # ------------------------------------------------------------------
    # Copy
    # ------------------------------------------------------------------

    def _on_copy_prompt(self):
        try:
            prompt_text = self.ai_instructions_text.get("1.0", tk.END)
            if self.sanitize_var.get():
                prompt_text = sanitize_output(prompt_text)
            pyperclip.copy(prompt_text)
            status = "The current prompt has been copied to your clipboard."
            if self.sanitize_var.get():
                status = "The sanitized prompt has been copied to your clipboard."
            messagebox.showinfo("Copy Complete", status)
        except Exception as exc:
            messagebox.showerror(
                "Copy Error",
                f"An error occurred while copying to clipboard: {exc}\n\n"
                "Note: Please ensure you have pyperclip installed to use this feature.",
            )

    # ------------------------------------------------------------------
    # File-type checkboxes
    # ------------------------------------------------------------------

    def _create_file_type_checkboxes(self, parent):
        """Create checkboxes over the union of all known extensions."""
        ttk.Label(parent, text="Include File Types:", padding=(0, 5, 0, 0)).pack(
            anchor=tk.W
        )

        checkbox_frame = ttk.Frame(parent)
        checkbox_frame.pack(fill=tk.X, pady=5)

        # Effective checkbox state = profile defaults overlaid with overrides.
        overrides = self.config.get_file_type_overrides(self.current_profile.name)
        effective = dict(self.current_profile.default_file_types)
        effective.update(overrides)

        # Render in alphabetical order, wrapping to a second row at a sane count.
        cols_per_row = 12
        for index, ext in enumerate(self.all_extensions):
            var = tk.BooleanVar(value=effective.get(ext, False))
            self.file_type_vars[ext] = var

            cb = ttk.Checkbutton(
                checkbox_frame, text=ext, variable=var,
                command=self._on_file_type_changed,
            )
            row, col = divmod(index, cols_per_row)
            cb.grid(row=row, column=col, padx=5, pady=2, sticky="w")

    def _on_file_type_changed(self):
        """Persist override + rebuild tree on any checkbox toggle."""
        # An override is anything that differs from the profile's default.
        defaults = self.current_profile.default_file_types
        overrides = {
            ext: var.get()
            for ext, var in self.file_type_vars.items()
            if var.get() != defaults.get(ext, False)
        }
        self.config.set_file_type_overrides(self.current_profile.name, overrides)
        self.config.save_config(file_type_overrides=self.config.file_type_overrides)

        self._rebuild_tree_from_disk()
        self._schedule_token_recalc()

    # ------------------------------------------------------------------
    # Token counting / model selection
    # ------------------------------------------------------------------

    def _create_token_counting_widgets(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=5)

        ttk.Label(frame, text="LLM Model:").pack(side=tk.LEFT, padx=(0, 5))

        self.model_var = tk.StringVar(value=self.config.last_llm_model)
        self.model_dropdown = ttk.Combobox(
            frame, textvariable=self.model_var, values=self.supported_models,
            width=35, state="readonly",
        )
        self.model_dropdown.pack(side=tk.LEFT, padx=(0, 10))

        if self.config.last_llm_model in self.supported_models:
            self.model_dropdown.set(self.config.last_llm_model)
        else:
            self.model_dropdown.set(
                "gpt-4" if "gpt-4" in self.supported_models else self.supported_models[0]
            )

        self.model_dropdown.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._schedule_token_recalc(),
        )

        self.token_count_label = ttk.Label(frame, text="Token Count: Calculating...")
        self.token_count_label.pack(side=tk.LEFT, padx=10)

        self.file_size_label = ttk.Label(frame, text="Total Size: 0 KB")
        self.file_size_label.pack(side=tk.RIGHT, padx=10)

        # Note: the initial calculation is now kicked off from `show()` after
        # all widgets are constructed and the tree has been populated, so we
        # don't schedule one here (it would race with selection-change events).

    def _schedule_token_recalc(self, delay_ms: int = 300):
        """
        Debounced trigger for token recalculation.

        Coalesces rapid successive calls (e.g., a burst of `_set_item_selected`
        invocations during tree population) into a single calculation that
        runs `delay_ms` after the last trigger.
        """
        if self.root is None:
            return
        # Cancel any previously-scheduled recount so we only run once.
        if self._token_recalc_after_id is not None:
            try:
                self.root.after_cancel(self._token_recalc_after_id)
            except Exception:
                pass
            self._token_recalc_after_id = None
        try:
            self._token_recalc_after_id = self.root.after(
                delay_ms, self._calculate_tokens_and_size
            )
        except tk.TclError:
            # Root is being destroyed; ignore.
            self._token_recalc_after_id = None

    def _calculate_tokens_and_size(self):
        """
        Start (or restart) the background token-count thread.

        The previous racy "if a thread is running, just bail" logic has been
        removed; instead we set `cancel_calculation` to signal the in-flight
        thread (if any) to abort early, then immediately spawn a new one.
        Concurrent threads are harmless because only the most-recent one's
        result will reach `_update_count_labels` (older threads either abort
        on the cancel flag or complete quickly).
        """
        # Clear the debounce ID since we're now firing.
        self._token_recalc_after_id = None

        # Capture all main-thread state the worker needs *before* spawning,
        # so the worker never touches Tk widgets directly.
        try:
            instructions_text = self.ai_instructions_text.get("1.0", tk.END)
        except Exception:
            instructions_text = ""

        selected_files = [
            self.item_id_to_path[item_id]
            for item_id in self.selected_items
            if item_id in self.item_id_to_path
        ]
        model = self.model_var.get() if self.model_var else "gpt-4"

        # Show "Calculating..." only when there's actually work to do; if
        # nothing is selected and instructions are empty, show 0 immediately.
        if not selected_files and not instructions_text.strip():
            self._update_count_labels(0, 0)
            return

        self.token_count_label.config(text="Token Count: Calculating...")

        # Signal any running thread to stop, then start a fresh one.
        self.cancel_calculation = True
        self.cancel_calculation = False  # reset for the new thread
        self.token_calc_thread = threading.Thread(
            target=self._background_token_calculation,
            args=(selected_files, instructions_text, model),
            daemon=True,
        )
        self.token_calc_thread.start()

    def _count_tokens(self, text: str, model_name: str) -> tuple[int, str]:
        """Return (token_count, source). 'source' indicates which backend was used."""
        _O200K_PREFIXES = ("gpt-4o", "gpt-4.1", "gpt-4.5", "gpt-5",
                           "o1", "o3", "o4", "chatgpt-4o")

        if not text:
            return 0, "empty"

        # 1. toksum — broadest model coverage.
        # toksum raises its own TokenizationError; the class lives at different
        # paths across versions, so look it up defensively and always keep a
        # broad Exception net so failures drop through to tiktoken.
        if toksum:
            toksum_error = (
                    getattr(toksum, "TokenizationError", None)
                    or getattr(getattr(toksum, "exceptions", None),
                               "TokenizationError", None)
            )
            try:
                return toksum.count_tokens(text, model_name), "toksum"
            except Exception as exc:
                kind = type(exc).__name__
                if toksum_error and isinstance(exc, toksum_error):
                    print(f"toksum TokenizationError for {model_name!r}: {exc}. "
                          f"Falling back to tiktoken.")
                else:
                    print(f"toksum failed for {model_name!r} ({kind}): {exc}. "
                          f"Falling back to tiktoken.")

        # 2. tiktoken — exact for OpenAI; let it pick the encoding by model name.
        if tiktoken:
            try:
                try:
                    encoding = tiktoken.encoding_for_model(model_name)
                except KeyError:
                    # Pick a sensible default by model family rather than blanket
                    # cl100k_base, which undercounts modern OpenAI models.
                    default = ("o200k_base"
                               if any(model_name.startswith(p) for p in _O200K_PREFIXES)
                               else "cl100k_base")
                    encoding = tiktoken.get_encoding(default)
                return len(encoding.encode(text)), "tiktoken"
            except Exception as exc:
                print(f"tiktoken failed for {model_name!r} "
                      f"({type(exc).__name__}): {exc}. Falling back to char approx.")

        # 3. Last-resort heuristic (English-biased, ~25% error typical).
        return max(1, len(text) // 4), "char_approx"

    def _background_token_calculation(
            self,
            selected_files: List[pathlib.Path],
            instructions_text: str,
            model: str,
    ):
        """
        Compute total bytes + token count for the AI instructions plus all
        selected files. Runs on a background thread; must not touch Tk
        widgets directly — results are marshaled back via `root.after(0, ...)`.
        """
        try:
            total_size = len(instructions_text.encode("utf-8"))
            # Start combined_text with the AI instructions so edits to that
            # textarea are reflected in the token count.
            combined_text = instructions_text + "\n\n" if instructions_text else ""

            for file_path in selected_files:
                if self.cancel_calculation:
                    return
                try:
                    size = file_path.stat().st_size
                    suffix = file_path.suffix.lower()
                    size_limit = self.current_profile.file_size_limits.get(suffix)

                    if size_limit and size > size_limit:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read(size_limit)
                    else:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()

                    total_size += len(content.encode("utf-8"))
                    combined_text += content + "\n\n"
                except Exception as exc:
                    print(f"Error processing file {file_path}: {exc}")

            try:
                token_count, method_used = self._count_tokens(combined_text, model)
            except Exception as exc:
                print(f"Token counting error: {exc}")
                token_count, method_used = len(combined_text) // 4, "exception_fallback"

            if self.cancel_calculation:
                return

            # Marshal back to the Tk thread. Guard against the root being
            # destroyed between scheduling and execution.
            try:
                self.root.after(
                    0,
                    lambda: self._update_count_labels(
                        total_size, token_count, method=method_used
                    ),
                )
            except (tk.TclError, RuntimeError):
                pass
        except Exception as exc:
            print(f"Error in token calculation thread: {exc}")
            if not self.cancel_calculation:
                try:
                    self.root.after(
                        0, lambda: self._update_count_labels(0, 0, error=str(exc))
                    )
                except (tk.TclError, RuntimeError):
                    pass

    def _update_count_labels(self, total_size, token_count, error=None, method="unknown"):
        # Guard: the root may have been destroyed before this `after` callback
        # was invoked (e.g. user clicked OK during a recount).
        try:
            if not self.token_count_label or not self.token_count_label.winfo_exists():
                return
        except tk.TclError:
            return

        if error:
            self.token_count_label.config(text="Token Count: Error")
            self.file_size_label.config(text="Total Size: Error")
            return

        if total_size < 1024:
            size_str = f"{total_size} bytes"
        elif total_size < 1024 * 1024:
            size_str = f"{total_size / 1024:.1f} KB"
        else:
            size_str = f"{total_size / (1024 * 1024):.1f} MB"

        token_note = ""
        if method.endswith("_approx") or method == "exception_fallback":
            token_note = " (approx)"

        self.token_count_label.config(
            text=f"Token Count: {token_count:,}{token_note}"
        )
        self.file_size_label.config(text=f"Total Size: {size_str}")
        self.config.save_config(last_llm_model=self.model_var.get())

    # ------------------------------------------------------------------
    # Tree view
    # ------------------------------------------------------------------

    def _create_tree_view(self, parent, file_list: List[pathlib.Path]):
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal")

        style = ttk.Style()
        style.configure("Module.Treeview.Item", foreground="blue")

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("fullpath", "type"),
            displaycolumns=[],
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
            selectmode="none",
        )
        vsb.config(command=self.tree.yview)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.config(command=self.tree.xview)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree.heading("#0", text="Files", anchor=tk.W)
        self.tree.column("#0", width=500, minwidth=200)

        self._populate_tree(file_list)

        for item in self.tree.get_children():
            self.tree.item(item, open=True)

        self.tree.bind("<ButtonRelease-1>", self._toggle_selection)
        self.tree.bind("<Double-1>", self._handle_double_click)

    def _should_include_file(self, file_path: pathlib.Path) -> bool:
        """True if extension is enabled and not always-excluded by profile."""
        ext = file_path.suffix.lower()
        if ext in self.current_profile.always_excluded_extensions:
            return False
        if ext in self.file_type_vars:
            return self.file_type_vars[ext].get()
        return False

    def _populate_tree(self, file_list: List[pathlib.Path]):
        self.tree.delete(*self.tree.get_children())
        self.item_id_to_path = {}
        self.selected_items = set()

        dir_structure: dict = {}
        for file_path in file_list:
            if (
                    self.exclude_var.get()
                    and any(excl in file_path.parts for excl in self.excluded_dirs)
            ):
                continue
            try:
                rel_path = (
                    file_path.relative_to(self.root_dir) if self.root_dir else file_path
                )
            except ValueError:
                rel_path = file_path

            parts = list(rel_path.parts)
            current_dict = dir_structure
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    current_dict.setdefault("__files__", []).append((part, file_path))
                else:
                    current_dict = current_dict.setdefault(part, {})

        self._add_tree_nodes("", dir_structure, "")
        self._select_root_files_only()

    def _select_root_files_only(self):
        for item_id in self.item_id_to_path:
            self._set_item_selected(item_id, False)
        for item_id, path in self.item_id_to_path.items():
            try:
                if path.parent == self.root_dir:
                    self._set_item_selected(item_id, True)
            except Exception:
                continue

    def _add_tree_nodes(self, parent_id, dir_dict, path_so_far):
        # Directories first.
        for name, content in sorted(dir_dict.items()):
            if name == "__files__":
                continue
            new_path = f"{path_so_far}/{name}" if path_so_far else name
            full_path = (
                self.root_dir / new_path if self.root_dir else pathlib.Path(new_path)
            )
            is_module = full_path in self.module_dirs
            text = str(full_path) if self.show_full_paths else name
            icon = "🔹" if is_module else "📁"
            node_id = self.tree.insert(
                parent_id, "end",
                text=f"[ ] {icon} {text}",
                values=(str(full_path), "directory"),
                open=False,
            )
            self._add_tree_nodes(node_id, content, new_path)

        # Files.
        if "__files__" in dir_dict:
            markers = self.current_profile.module_markers
            for name, file_path in sorted(dir_dict["__files__"]):
                if not self._should_include_file(file_path):
                    continue
                display_name = str(file_path) if self.show_full_paths else name

                # Profile-aware iconography.
                lower = name.lower()
                if name in markers:
                    icon = "🔸"
                elif lower.endswith((".py", ".pyw")):
                    icon = "🐍"
                elif lower.endswith((".ts", ".tsx")):
                    icon = "🔷"
                elif lower.endswith((".js", ".jsx")):
                    icon = "📜"
                elif lower.endswith((".scss", ".sass", ".css")):
                    icon = "🎨"
                elif lower.endswith((".html", ".htm")):
                    icon = "🌐"
                elif lower.endswith((".json", ".yaml", ".yml", ".toml", ".ini", ".cfg")):
                    icon = "🔧"
                elif lower.endswith((".md", ".rst", ".txt")):
                    icon = "📝"
                elif lower.endswith(".xml"):
                    icon = "📋"
                else:
                    icon = "📄"

                item_id = self.tree.insert(
                    parent_id, "end",
                    text=f"[ ] {icon} {display_name}",
                    values=(str(file_path), "file"),
                )
                self.item_id_to_path[item_id] = file_path
                should_select = parent_id == "" and path_so_far == ""
                self._set_item_selected(item_id, should_select)

    def _toggle_path_display(self):
        self.show_full_paths = self.full_path_var.get()
        self._rebuild_tree_from_disk()

    def _rebuild_tree(self):
        """Alias retained for backward compatibility with toolbar handlers."""
        self._rebuild_tree_from_disk()

    def _rebuild_tree_from_disk(self):
        """Re-walk the filesystem honoring the current profile and rebuild the tree."""
        selected_paths = {
            self.item_id_to_path[item_id]
            for item_id in self.selected_items
            if item_id in self.item_id_to_path
        }

        all_files: List[pathlib.Path] = collect_project_files(
            self.root_dir,
            self.current_profile,
            self.exclude_var.get()
        )
        self._populate_tree(all_files)

        for item_id, path in self.item_id_to_path.items():
            if path in selected_paths:
                self._set_item_selected(item_id, True)

        self.update_main_file_combobox()
        self._schedule_token_recalc()

    def _set_item_selected(self, item_id, selected):
        if item_id not in self.item_id_to_path:
            return
        text = self.tree.item(item_id, "text")
        if selected:
            new_text = text.replace("[ ]", "[✓]", 1)
            self.selected_items.add(item_id)
        else:
            new_text = text.replace("[✓]", "[ ]", 1)
            self.selected_items.discard(item_id)
        self.tree.item(item_id, text=new_text)
        self._update_parent_selection(self.tree.parent(item_id))

        if hasattr(self, "main_combobox"):
            self.update_main_file_combobox()
        # Use the debounced scheduler so a burst of selection changes (e.g.,
        # `_select_all`, initial population) collapses to a single recount.
        if hasattr(self, "token_count_label") and self.token_count_label is not None:
            self._schedule_token_recalc()

    def _update_parent_selection(self, parent_id):
        if not parent_id:
            return
        children = self.tree.get_children(parent_id)
        if not children:
            return
        all_selected = all(
            "[ ]" not in self.tree.item(child, "text") for child in children
        )
        any_selected = any(
            "[✓]" in self.tree.item(child, "text") for child in children
        )
        text = self.tree.item(parent_id, "text")
        if all_selected:
            new_text = text.replace("[ ]", "[✓]", 1).replace("[~]", "[✓]", 1)
        elif any_selected:
            new_text = text.replace("[ ]", "[~]", 1).replace("[✓]", "[~]", 1)
        else:
            new_text = text.replace("[✓]", "[ ]", 1).replace("[~]", "[ ]", 1)
        self.tree.item(parent_id, text=new_text)
        self._update_parent_selection(self.tree.parent(parent_id))

    def _handle_double_click(self, event):
        x, y = event.x, event.y
        item_id = self.tree.identify("item", x, y)
        if not item_id:
            return
        if x >= 30:
            item_type = (
                self.tree.item(item_id, "values")[1]
                if self.tree.item(item_id, "values")
                else None
            )
            if item_type == "directory":
                self.tree.item(item_id, open=not self.tree.item(item_id, "open"))

    def _toggle_selection(self, event):
        x, y = event.x, event.y
        # Identify which part of the tree was clicked
        region = self.tree.identify_region(x, y)
        item_id = self.tree.identify("item", x, y)

        if not item_id:
            return

        element = self.tree.identify_element(x, y)
        if element == "Treeitem.indicator":
            return

        # 'tree' region means the main column with the icons/text
        # 'heading' means the column header
        if region == "tree":
            text = self.tree.item(item_id, "text")
            item_type = (
                self.tree.item(item_id, "values")[1]
                if self.tree.item(item_id, "values")
                else None
            )

            if item_type == "file":
                self._set_item_selected(item_id, "[✓]" not in text)
            elif item_type == "directory":
                is_selected = "[✓]" in text
                is_partial = "[~]" in text
                should_select = not (is_selected or is_partial)
                self._toggle_all_children(item_id, should_select)
                self._update_parent_selection(self.tree.parent(item_id))

    def _toggle_all_children(self, item_id, select):
        for child in self.tree.get_children(item_id):
            child_type = (
                self.tree.item(child, "values")[1]
                if self.tree.item(child, "values")
                else None
            )
            if child_type == "file":
                self._set_item_selected(child, select)
            else:
                text = self.tree.item(child, "text")
                if select:
                    new_text = text.replace("[ ]", "[✓]", 1).replace("[~]", "[✓]", 1)
                else:
                    new_text = text.replace("[✓]", "[ ]", 1).replace("[~]", "[ ]", 1)
                self.tree.item(child, text=new_text)
                self._toggle_all_children(child, select)

    def _select_all(self):
        for item_id in self.item_id_to_path:
            self._set_item_selected(item_id, True)
        self._schedule_token_recalc()

    def _deselect_all(self):
        for item_id in self.item_id_to_path:
            self._set_item_selected(item_id, False)
        self._schedule_token_recalc()

    def _select_modules(self):
        """Select files matching the active profile's module markers."""
        self._deselect_all()
        markers = self.current_profile.module_markers
        for item_id, path in self.item_id_to_path.items():
            if path.name in markers:
                self._set_item_selected(item_id, True)
        self._schedule_token_recalc()

    # ------------------------------------------------------------------
    # Main-file combobox
    # ------------------------------------------------------------------

    def update_main_file_combobox(self):
        selected_files = [
            self.item_id_to_path[item_id]
            for item_id in self.selected_items
            if item_id in self.item_id_to_path
        ]

        # Profile-aware prioritization: entry points first, then root-dir, then rest.
        entry_points = set(find_entry_points(selected_files, self.current_profile))
        root_files: list = []
        other_files: list = []
        entry_files: list = []

        for file_path in selected_files:
            if file_path in entry_points:
                entry_files.append(file_path)
            elif file_path.parent == self.root_dir:
                root_files.append(file_path)
            else:
                other_files.append(file_path)

        entry_files.sort(key=lambda p: p.name.lower())
        root_files.sort(key=lambda p: p.name.lower())
        other_files.sort(key=lambda p: p.name.lower())
        prioritized = entry_files + root_files + other_files

        self.display_name_to_path = {}
        display_names: list[str] = []

        basename_counts: dict[str, int] = {}
        for path in prioritized:
            basename_counts[path.name] = basename_counts.get(path.name, 0) + 1

        for file_path in prioritized:
            basename = file_path.name
            if basename_counts.get(basename, 0) > 1:
                display_name = f"{file_path.parent.name}/{basename}"
                count = 1
                while display_name in self.display_name_to_path:
                    try:
                        parts = list(file_path.relative_to(self.root_dir).parts)
                        if len(parts) > count + 1:
                            display_name = "/".join(parts[-(count + 1):])
                        else:
                            display_name = str(file_path)
                        count += 1
                    except Exception:
                        display_name = str(file_path)
                        break
            else:
                display_name = basename
            display_names.append(display_name)
            self.display_name_to_path[display_name] = file_path

        values = ["[None]"] + display_names
        current = self.main_file_var.get()
        self.main_combobox["values"] = values
        if current in values:
            self.main_combobox.set(current)
        else:
            self.main_combobox.current(0)
        self.initial_dir_files_prioritized = True

    # ------------------------------------------------------------------
    # Prompt selection
    # ------------------------------------------------------------------

    def _on_category_selected(self, _event):
        category_name = self.category_var.get()
        if category_name == "[Select a category]":
            self.prompt_dropdown["values"] = []
            self.prompt_dropdown.set("")
            self.prompt_dropdown.configure(state="disabled")
            self.current_category = None
            self.current_prompts = []
            return

        category = self.prompt_library.get_category(category_name)
        if not category:
            return
        self.current_category = category
        prompt_titles = category.list_prompts()
        self.prompt_dropdown["values"] = prompt_titles
        self.current_prompts = prompt_titles
        if prompt_titles:
            self.prompt_dropdown.configure(state="readonly")
            self.prompt_dropdown.current(0)
            self._on_prompt_selected(None)
        else:
            self.prompt_dropdown.configure(state="disabled")

    def _on_prompt_selected(self, _event):
        if not self.current_category or not self.prompt_var.get():
            return
        category_name = self.category_var.get()
        prompt_title = self.prompt_var.get()
        if not prompt_title:
            return

        prompt_text = self.prompt_library.get_full_prompt(category_name, prompt_title)
        if prompt_text:
            self.ai_instructions_text.delete(1.0, tk.END)
            self.ai_instructions_text.insert(tk.END, prompt_text)
            # Programmatic update; reset manual-edit flag.
            self.instructions_manually_edited = False
            self.config.save_config(
                last_prompt_category=(
                    category_name if category_name != "[Select a category]" else ""
                ),
                last_prompt_title=prompt_title,
            )
            # Instruction body changed — refresh the token count.
            self._schedule_token_recalc()

    # ------------------------------------------------------------------
    # Shutdown helpers
    # ------------------------------------------------------------------

    def _cancel_pending_after_ids(self):
        """
        Cancel every `after` callback we have queued so none of them fire
        against destroyed widgets after `root.destroy()`.

        This is the structural fix for the
        `ttk::progressbar::Autoincrement` / `winfo exists` style errors:
        Tk's own widgets register recurring `after` callbacks too, but as
        long as we don't tear down the root mid-flight (we drain pending
        events first), Tk cleans them up correctly.
        """
        if self._token_recalc_after_id is not None:
            try:
                self.root.after_cancel(self._token_recalc_after_id)
            except Exception:
                pass
            self._token_recalc_after_id = None

    # ------------------------------------------------------------------
    # OK / Cancel
    # ------------------------------------------------------------------

    def _on_ok(self):
        try:
            selected_files = [
                self.item_id_to_path[item_id]
                for item_id in self.selected_items
                if item_id in self.item_id_to_path
            ]
            if not selected_files:
                messagebox.showwarning(
                    "No Files Selected",
                    "Please select at least one file to proceed.",
                )
                return

            main_file_display = self.main_file_var.get()
            main_file = None
            if main_file_display and main_file_display != "[None]":
                main_file = self.display_name_to_path.get(main_file_display)

            current_category = self.category_var.get()
            current_prompt = self.prompt_var.get()

            # Stop any in-flight background work and cancel any queued
            # `after` callbacks before destroying the root window. This
            # prevents the
            #   `can't invoke "winfo" command: application has been destroyed`
            # error from queued callbacks (token recalc, etc.) firing against
            # widgets whose interpreter has been torn down.
            self.cancel_calculation = True
            self._cancel_pending_after_ids()

            self.result["selected_files"] = selected_files
            self.result["general_ai_instructions"] = self.ai_instructions_text.get(
                "1.0", tk.END
            )
            self.result["main_file"] = main_file
            self.result["status"] = "ok"
            self.result["profile"] = self.current_profile
            self.result["sanitize_output"] = self.sanitize_var.get()  # Save checkbox state

            # Persist profile-related state.
            self.config.set_directory_profile(self.root_dir, self.current_profile.name)
            self.config.save_config(
                initial_dir=self.root_dir,
                main_file=main_file,
                selected_files=selected_files,
                last_prompt_category=(
                    current_category if current_category != "[Select a category]" else ""
                ),
                last_prompt_title=current_prompt,
                last_llm_model=self.model_var.get(),
                last_profile=self.current_profile.name,
                directory_profiles=self.config.directory_profiles,
                file_type_overrides=self.config.file_type_overrides,
            )

            # Drain any pending Tk events (especially `after` callbacks that
            # were already queued and can no longer be cancelled) before we
            # destroy the root. Without this drain, callbacks like the
            # ttk::progressbar autoincrement timer can fire on destroyed
            # widgets and raise a TclError.
            try:
                self.root.update_idletasks()
            except tk.TclError:
                pass

            self.root.destroy()

        except Exception as exc:
            try:
                self.root.destroy()
            except Exception:
                pass
            messagebox.showerror(
                "Error", f"An error occurred while processing: {exc}"
            )

    def _on_exit(self):
        self.cancel_calculation = True
        self._cancel_pending_after_ids()
        self.result["status"] = "cancel"
        try:
            self.root.update_idletasks()
        except tk.TclError:
            pass
        self.root.destroy()


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------
def collect_project_files(
        directory: pathlib.Path,
        profile: ProjectProfile,
        exclude_dirs: bool = True
) -> List[pathlib.Path]:
    """
    Walk the directory, applying profile-driven directory exclusions and
    always-excluded extensions. Ignores file type selection (UI concern).
    """
    excluded_dirs = set(profile.excluded_dirs)
    always_excluded = profile.always_excluded_extensions
    collected: List[pathlib.Path] = []

    for root, dirs, files in os.walk(directory):
        if exclude_dirs:
            dirs[:] = [d for d in dirs if d not in excluded_dirs]
        for filename in files:
            file_path = pathlib.Path(root) / filename
            ext = file_path.suffix.lower()
            if ext in always_excluded:
                continue
            collected.append(file_path)

    return collected


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

def main():
    """Application entry point."""
    config = Config()
    profile_manager = ProfileManager(pathlib.Path(config.config_dir))

    temp_root = tk.Tk()
    temp_root.withdraw()
    initial_dir_str = filedialog.askdirectory(
        title="Select Project Directory", initialdir=config.initial_dir
    )
    temp_root.destroy()

    if not initial_dir_str:
        print("No directory selected. Exiting.")
        sys.exit(0)

    initial_wd = pathlib.Path(initial_dir_str).resolve()
    config.save_config(initial_dir=initial_wd)

    # Profile resolution: directory mapping > auto-detect > last used > Python.
    saved_profile_name = config.get_directory_profile(initial_wd)
    detected_name = detect_project_type(initial_wd)
    profile_name = (
            saved_profile_name
            or detected_name
            or config.last_profile
            or "Python"
    )
    profile = profile_manager.load_profile(profile_name)
    if profile is None:
        # Fall back gracefully if a saved custom profile was deleted on disk.
        print(f"Profile '{profile_name}' not found; falling back to Python.")
        profile = profile_manager.load_profile("Python")
        profile_name = "Python"

    # Compute effective file-type selection: defaults overlaid with overrides.
    file_type_selection = dict(profile.default_file_types)
    file_type_selection.update(config.get_file_type_overrides(profile_name))

    files = collect_project_files(initial_wd, profile, exclude_dirs=True)
    if not files:
        messagebox.showwarning(
            "No Files Found",
            f"No files of the selected types found in the specified directory "
            f"under the '{profile.display_name}' profile.",
        )
        sys.exit(1)

    dialog = AIProgrammingAssistantDialog(
        profile_manager=profile_manager,
        initial_profile=profile,
        config=config,
        title="AI Programming Assistant",
        width=900,
        height=700,
    )

    # Unpack the new sanitize_output flag from the dialog result
    selected_files, status, instructions, main_file, final_profile, sanitize_flag = dialog.show(
        files, default_ai_instructions=profile.default_instructions,
    )

    if status == "cancel":
        print("Operation cancelled by user.")
        sys.exit(0)

    if not selected_files:
        messagebox.showwarning(
            "No Files Selected", "No files were selected for compilation."
        )
        sys.exit(1)

    try:
        compiler = CodeCompiler(initial_wd, final_profile)
        compiler.add_ai_instructions(instructions)
        compiler.compile(selected_files, main_file)

        # Apply sanitization if checked in the dialog
        if sanitize_flag:
            compiler.compiled_content = sanitize_output(compiler.compiled_content)
            # Overwrite the file with sanitized content
            with compiler.output_filename.open("w", encoding="utf-8") as outfile:
                outfile.write(compiler.compiled_content)

        clipboard_success = compiler.copy_to_clipboard()

        message = (
            f"Successfully compiled {len(selected_files)} files to "
            f"'{compiler.output_filename}'.\n"
            f"Profile used: {final_profile.display_name}"
        )
        if sanitize_flag:
            message += "\nOutput has been sanitized."
        if main_file:
            message += f"\nMain program file: {main_file.name}"
        if clipboard_success:
            message += "\nContent has been copied to clipboard."
        else:
            message += (
                "\nNote: Could not copy to clipboard. "
                "Install pyperclip module for clipboard support."
            )
        messagebox.showinfo("Compilation Complete", message)

    except Exception as exc:
        messagebox.showerror(
            "Error", f"An error occurred during compilation: {exc}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
