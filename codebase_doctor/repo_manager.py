"""
Repository Manager
Handles cloning GitHub repositories, scanning local codebases, and inspecting git diffs.
"""

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union


class RepoManager:
    """Manages repository discovery, cloning, and file reading."""

    DEFAULT_IGNORED_DIRS: Set[str] = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        "venv",
        ".venv",
        "env",
        ".env",
        "node_modules",
        ".idea",
        ".vscode",
        "dist",
        "build",
        "target",
        "bin",
        "obj",
        ".gradle",
        ".cargo",
        ".next",
        ".nuxt",
        "vendor",
        "cmake-build-debug",
        ".mypy_cache",
        ".tox",
        ".eggs",
    }

    # Comprehensive polyglot language extension map
    LANGUAGE_MAP: Dict[str, str] = {
        ".py": "Python",
        ".pyw": "Python",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".mjs": "JavaScript",
        ".cjs": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".vue": "Vue",
        ".svelte": "Svelte",
        ".c": "C",
        ".h": "C/C++ Header",
        ".cpp": "C++",
        ".cc": "C++",
        ".cxx": "C++",
        ".hpp": "C++ Header",
        ".hxx": "C++ Header",
        ".ino": "Arduino/C++",
        ".java": "Java",
        ".kt": "Kotlin",
        ".scala": "Scala",
        ".go": "Go",
        ".rs": "Rust",
        ".cs": "C#",
        ".php": "PHP",
        ".rb": "Ruby",
        ".sh": "Shell",
        ".bash": "Shell",
        ".zsh": "Shell",
        ".ps1": "PowerShell",
        ".sql": "SQL",
        ".json": "JSON",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".toml": "TOML",
        ".xml": "XML",
        ".env": "Config",
        ".ini": "Config",
        ".cfg": "Config",
        ".html": "HTML",
        ".css": "CSS",
    }

    DEFAULT_EXTENSIONS: Set[str] = set(LANGUAGE_MAP.keys())
    SPECIAL_FILENAMES: Set[str] = {"dockerfile", "makefile", "cmakelists.txt", "jenkinsfile"}
    GIT_URL_PREFIXES: Tuple[str, ...] = ("http://", "https://", "git@", "git://", "github.com/", "gitlab.com/")

    def __init__(
        self,
        root_path: str,
        supported_extensions: Optional[Set[str]] = None,
        clone_dir: Optional[str] = None,
    ):
        root_str = str(root_path).strip()
        self.remote_url: Optional[str] = None
        self.is_cloned: bool = False

        if any(root_str.startswith(prefix) for prefix in self.GIT_URL_PREFIXES) or root_str.endswith(".git"):
            # Auto-clone remote repository
            self.remote_url = root_str
            self.root_path = self._clone_repo(root_str, clone_dir=clone_dir)
            self.is_cloned = True
        else:
            self.root_path = Path(root_path).resolve()
            if not self.root_path.exists():
                raise FileNotFoundError(f"Repository path does not exist: {self.root_path}")

        self.supported_extensions = supported_extensions or self.DEFAULT_EXTENSIONS

    @classmethod
    def detect_language(cls, file_path: str) -> str:
        """Determines the programming language of a file."""
        name = Path(file_path).name.lower()
        if name in cls.SPECIAL_FILENAMES:
            if "dockerfile" in name:
                return "Dockerfile"
            if "make" in name or "cmake" in name:
                return "Build/Make"
            return "Config"

        suffix = Path(file_path).suffix.lower()
        return cls.LANGUAGE_MAP.get(suffix, "Unknown")

    @classmethod
    def _clone_repo(cls, repo_url: str, clone_dir: Optional[str] = None) -> Path:
        """Clones a remote git repository into clone_dir or a temporary directory."""
        clean_url = repo_url
        if clean_url.startswith("github.com/"):
            clean_url = f"https://{clean_url}"
        elif clean_url.startswith("gitlab.com/"):
            clean_url = f"https://{clean_url}"

        target = Path(clone_dir) if clone_dir else Path(tempfile.mkdtemp(prefix="repo_doctor_"))
        target.mkdir(parents=True, exist_ok=True)

        cmd = ["git", "clone", "--depth", "1", clean_url, str(target)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to clone {clean_url}: {result.stderr}")

        return target.resolve()

    @classmethod
    def from_github(cls, repo_url: str, clone_dir: Optional[str] = None) -> "RepoManager":
        """Clones a GitHub repository and returns a RepoManager instance."""
        target = cls._clone_repo(repo_url, clone_dir=clone_dir)
        instance = cls(str(target))
        instance.remote_url = repo_url
        instance.is_cloned = True
        return instance

    @classmethod
    def is_test_file(cls, file_path: Path | str) -> bool:
        """Determines if a file is a test file based on directory and filename conventions."""
        p = Path(file_path)
        parts = [part.lower() for part in p.parts]
        test_dir_names = {"test", "tests", "__tests__", "spec", "specs"}
        if any(part in test_dir_names for part in parts[:-1]):
            return True
        stem = p.stem.lower()
        if stem.startswith("test_") or stem.endswith(("_test", ".test", ".spec")) or stem == "test":
            return True
        return False

    def get_source_files(self, language: Optional[str] = None, exclude_tests: bool = False) -> List[Path]:
        """Discovers all source code files within the repository, ignoring non-source trees."""
        source_files: List[Path] = []
        for root, dirs, files in os.walk(self.root_path):
            # Prune ignored directories in-place
            dirs[:] = [d for d in dirs if d not in self.DEFAULT_IGNORED_DIRS and not d.startswith(".")]

            for file_name in files:
                file_path = Path(root) / file_name
                is_supported = (
                    file_path.suffix.lower() in self.supported_extensions
                    or file_name.lower() in self.SPECIAL_FILENAMES
                )
                if is_supported:
                    if exclude_tests and self.is_test_file(file_path):
                        continue
                    if language:
                        file_lang = self.detect_language(str(file_path)).lower()
                        if file_lang != language.lower():
                            continue
                    source_files.append(file_path)

        return sorted(source_files)

    def get_languages(self) -> Dict[str, int]:
        """Counts discovered files per programming language."""
        counts: Dict[str, int] = {}
        for f in self.get_source_files():
            lang = self.detect_language(str(f))
            counts[lang] = counts.get(lang, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))

    def get_relative_path(self, path: Path) -> str:
        """Returns relative path from the repository root."""
        try:
            return str(path.resolve().relative_to(self.root_path)).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")

    def read_file(self, relative_or_abs_path: str) -> str:
        """Reads file contents using UTF-8 with fallback decoding."""
        path = Path(relative_or_abs_path)
        if not path.is_absolute():
            path = self.root_path / path

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="latin-1")

    def compute_file_hash(self, file_path: Union[str, Path]) -> str:
        """Computes SHA-256 hash of a file's raw content."""
        path = Path(file_path)
        if not path.is_absolute():
            path = self.root_path / path
        if not path.exists() or path.is_dir():
            return ""
        hasher = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except (OSError, PermissionError):
            return ""

    def get_file_state(
        self, language: Optional[str] = None, exclude_tests: bool = False
    ) -> Dict[str, str]:
        """
        Returns a mapping of relative file paths to their SHA-256 content hashes
        for all discovered source files in the repository.
        """
        state: Dict[str, str] = {}
        for f in self.get_source_files(language=language, exclude_tests=exclude_tests):
            rel_path = self.get_relative_path(f)
            h = self.compute_file_hash(f)
            if h:
                state[rel_path] = h
        return state

    def get_incremental_changes(
        self,
        previous_state: Dict[str, str],
        language: Optional[str] = None,
        exclude_tests: bool = False,
    ) -> Dict[str, List[str]]:
        """
        Compares current repository file hashes against previous_state.
        Returns a dict with 'added', 'modified', 'deleted', and 'unchanged' relative file paths.
        """
        current_state = self.get_file_state(language=language, exclude_tests=exclude_tests)
        added: List[str] = []
        modified: List[str] = []
        unchanged: List[str] = []
        deleted: List[str] = []

        for rel_path, curr_hash in current_state.items():
            if rel_path not in previous_state:
                added.append(rel_path)
            elif curr_hash != previous_state[rel_path]:
                modified.append(rel_path)
            else:
                unchanged.append(rel_path)

        for rel_path in previous_state:
            if rel_path not in current_state:
                deleted.append(rel_path)

        return {
            "added": sorted(added),
            "modified": sorted(modified),
            "deleted": sorted(deleted),
            "unchanged": sorted(unchanged),
        }

    def is_git_repo(self) -> bool:
        """Checks if the repository is a valid initialized git repository."""
        if (self.root_path / ".git").exists():
            return True
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=str(self.root_path),
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0:
                top_level = Path(res.stdout.strip()).resolve()
                # Do not treat user's home directory as project git repo
                if top_level == Path.home().resolve() and self.root_path.resolve() != Path.home().resolve():
                    return False
                return top_level == self.root_path.resolve() or (self.root_path / ".git").exists()
            return False
        except Exception:
            return False

    def get_changed_files(
        self,
        base_ref: Optional[str] = None,
        include_untracked: bool = True,
    ) -> List[str]:
        """
        Inspects git changes:
        - If base_ref is provided (e.g. 'main' or 'HEAD~1'): diffs against base_ref.
        - If base_ref is None: inspects uncommitted changes (unstaged + staged + untracked),
          falling back to HEAD~1 if working tree is clean.
        """
        if not self.is_git_repo():
            return []

        changed: Set[str] = set()

        def _clean_and_add(lines: List[str]):
            for line in lines:
                cleaned = line.strip().replace("\\", "/")
                if not cleaned:
                    continue
                parts = Path(cleaned).parts
                if any(part in self.DEFAULT_IGNORED_DIRS for part in parts):
                    continue
                # Check extension support
                suffix = Path(cleaned).suffix.lower()
                is_supp = (
                    suffix in self.supported_extensions
                    or Path(cleaned).name.lower() in self.SPECIAL_FILENAMES
                )
                if is_supp:
                    changed.add(cleaned)

        try:
            if base_ref:
                # Diff against specified base reference / branch
                cmd = ["git", "diff", "--relative", "--name-only", base_ref]
                res = subprocess.run(cmd, cwd=str(self.root_path), capture_output=True, text=True, check=False)
                if res.returncode != 0:
                    raise ValueError(f"Git base reference '{base_ref}' not found or invalid: {res.stderr.strip()}")
                _clean_and_add(res.stdout.splitlines())

                # Also include uncommitted working tree changes on top of base_ref
                cmd_unstaged = ["git", "diff", "--relative", "--name-only"]
                res_unstaged = subprocess.run(cmd_unstaged, cwd=str(self.root_path), capture_output=True, text=True, check=False)
                if res_unstaged.returncode == 0:
                    _clean_and_add(res_unstaged.stdout.splitlines())

                cmd_staged = ["git", "diff", "--relative", "--name-only", "--cached"]
                res_staged = subprocess.run(cmd_staged, cwd=str(self.root_path), capture_output=True, text=True, check=False)
                if res_staged.returncode == 0:
                    _clean_and_add(res_staged.stdout.splitlines())
            else:
                # 1. Unstaged changes in working tree
                cmd_unstaged = ["git", "diff", "--relative", "--name-only"]
                res_unstaged = subprocess.run(cmd_unstaged, cwd=str(self.root_path), capture_output=True, text=True, check=False)
                if res_unstaged.returncode == 0:
                    _clean_and_add(res_unstaged.stdout.splitlines())

                # 2. Staged changes
                cmd_staged = ["git", "diff", "--relative", "--name-only", "--cached"]
                res_staged = subprocess.run(cmd_staged, cwd=str(self.root_path), capture_output=True, text=True, check=False)
                if res_staged.returncode == 0:
                    _clean_and_add(res_staged.stdout.splitlines())

                # 3. If working tree clean, check last commit HEAD~1
                if not changed:
                    cmd_head = ["git", "diff", "--relative", "--name-only", "HEAD~1"]
                    res_head = subprocess.run(cmd_head, cwd=str(self.root_path), capture_output=True, text=True, check=False)
                    if res_head.returncode == 0:
                        _clean_and_add(res_head.stdout.splitlines())

            # 4. Untracked source files
            if include_untracked:
                cmd_untracked = ["git", "ls-files", "--others", "--exclude-standard"]
                res_untracked = subprocess.run(cmd_untracked, cwd=str(self.root_path), capture_output=True, text=True, check=False)
                if res_untracked.returncode == 0:
                    _clean_and_add(res_untracked.stdout.splitlines())

        except ValueError:
            raise
        except Exception:
            pass

        return sorted(list(changed))

    def get_changed_files_from_git(self, base_ref: str = "HEAD~1") -> List[str]:
        """Detects changed files from git diff if this is a git repo (backward compatibility)."""
        return self.get_changed_files(base_ref=base_ref)

    def get_git_diff(
        self,
        base_ref: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> str:
        """Returns the git diff for a specific file or the entire repository."""
        if not self.is_git_repo():
            return ""

        try:
            if base_ref:
                cmd = ["git", "diff", "--relative", base_ref]
                if file_path:
                    cmd.extend(["--", file_path])
                res = subprocess.run(cmd, cwd=str(self.root_path), capture_output=True, text=True, check=False)
                return res.stdout

            # Uncommitted diff: combine unstaged + staged
            cmd_unstaged = ["git", "diff", "--relative"]
            if file_path:
                cmd_unstaged.extend(["--", file_path])
            res1 = subprocess.run(cmd_unstaged, cwd=str(self.root_path), capture_output=True, text=True, check=False)

            cmd_staged = ["git", "diff", "--relative", "--cached"]
            if file_path:
                cmd_staged.extend(["--", file_path])
            res2 = subprocess.run(cmd_staged, cwd=str(self.root_path), capture_output=True, text=True, check=False)

            out = (res1.stdout or "") + ("\n" if res1.stdout and res2.stdout else "") + (res2.stdout or "")
            if not out.strip():
                # Fallback to HEAD~1
                cmd_head = ["git", "diff", "--relative", "HEAD~1"]
                if file_path:
                    cmd_head.extend(["--", file_path])
                res3 = subprocess.run(cmd_head, cwd=str(self.root_path), capture_output=True, text=True, check=False)
                return res3.stdout or ""
            return out
        except Exception:
            return ""

    def get_diff_stats(self, base_ref: Optional[str] = None) -> Dict[str, Any]:
        """Calculates diff statistics (files changed, insertions, deletions)."""
        default_stats = {
            "files_changed": 0,
            "insertions": 0,
            "deletions": 0,
            "stat_text": "",
        }
        if not self.is_git_repo():
            return default_stats

        try:
            cmd = ["git", "diff", "--relative", "--stat"]
            if base_ref:
                cmd.append(base_ref)
            else:
                cmd.append("HEAD")

            res = subprocess.run(cmd, cwd=str(self.root_path), capture_output=True, text=True, check=False)
            output = res.stdout.strip()
            if not output and not base_ref:
                # Try unstaged + cached
                res_unstaged = subprocess.run(["git", "diff", "--relative", "--stat"], cwd=str(self.root_path), capture_output=True, text=True, check=False)
                res_staged = subprocess.run(["git", "diff", "--relative", "--stat", "--cached"], cwd=str(self.root_path), capture_output=True, text=True, check=False)
                output = f"{res_unstaged.stdout.strip()}\n{res_staged.stdout.strip()}".strip()

            if not output and not base_ref:
                # Fallback to HEAD~1
                res_head = subprocess.run(["git", "diff", "--relative", "--stat", "HEAD~1"], cwd=str(self.root_path), capture_output=True, text=True, check=False)
                if res_head.returncode == 0:
                    output = res_head.stdout.strip()

            if not output:
                return default_stats

            files_changed = 0
            insertions = 0
            deletions = 0

            import re
            m_files = re.search(r"(\d+)\s+file[s]?\s+changed", output)
            if m_files:
                files_changed = int(m_files.group(1))
            m_ins = re.search(r"(\d+)\s+insertion[s]?\(\+\)", output)
            if m_ins:
                insertions = int(m_ins.group(1))
            m_del = re.search(r"(\d+)\s+deletion[s]?\(-\)", output)
            if m_del:
                deletions = int(m_del.group(1))

            return {
                "files_changed": files_changed,
                "insertions": insertions,
                "deletions": deletions,
                "stat_text": output,
            }
        except Exception:
            return default_stats

    def summary(self) -> Dict[str, any]:
        """Generates summary metrics about the repository."""
        files = self.get_source_files()
        total_loc = 0
        for f in files:
            try:
                total_loc += len(self.read_file(str(f)).splitlines())
            except Exception:
                pass

        return {
            "root_path": str(self.root_path),
            "total_files": len(files),
            "total_loc": total_loc,
            "languages": self.get_languages(),
            "is_git_repo": (self.root_path / ".git").exists(),
        }
