#!/usr/bin/env python3
import logging
import shutil
from pathlib import Path

from ruamel.yaml import YAML

SPECIAL_PURPOSE_PACKAGES: set[str] = {"utils"}


# ——————————————————————————————————————————————————————————————————————————————————————
# SETUP

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

SRC_PACKAGE = "tickvise"
SRC_PATH = Path(f"src/{SRC_PACKAGE}")
DOCS_PATH = Path("docs/reference")
MKDOCS_PATH = Path("mkdocs.yml")

NAV_SECTION = "Reference"
NAV_OVERVIEW = "Package Structure"

yaml = YAML()
yaml.preserve_quotes = True


# ——————————————————————————————————————————————————————————————————————————————————————
# HELPERS


def format_module_title(module_name: str) -> str:
    """Format module name as a file reference."""
    return f"{module_name}.py"


def format_package_title(package_name: str) -> str:
    """Format package name as a dotted prefix."""
    return f".{package_name}"


def discover_package_structure(package_dir: Path, module_prefix: str) -> dict:
    """Recursively discover package structure to arbitrary depth.

    Returns:
        Dictionary with 'files' (list of .py file stems) and 'subpackages' (nested dict).
    """
    structure: dict = {"files": [], "subpackages": {}}

    for py_file in package_dir.glob("*.py"):
        if py_file.name != "__init__.py":
            structure["files"].append(py_file.stem)

    for subdir in package_dir.iterdir():
        if subdir.is_dir() and (subdir / "__init__.py").exists():
            subpackage_prefix = f"{module_prefix}.{subdir.name}"
            structure["subpackages"][subdir.name] = discover_package_structure(
                subdir, subpackage_prefix
            )

    return structure


def get_module_docstring(module_name: str, submodules: list[str]) -> str:
    """Extract the module-level docstring from a module's file."""
    if module_name in submodules:
        init_file = SRC_PATH / module_name / "__init__.py"
    else:
        init_file = SRC_PATH / f"{module_name}.py"

    if not init_file.exists():
        return ""

    content = init_file.read_text().strip()
    lines = content.split("\n")
    if not lines:
        return ""

    first_line = lines[0].strip()
    if not (first_line.startswith('"""') or first_line.startswith("'''")):
        return ""

    quote = first_line[:3]
    if first_line.count(quote) >= 2:
        return first_line[3 : first_line.index(quote, 3)].strip()

    docstring_lines = []
    if len(first_line) > 3:
        docstring_lines.append(first_line[3:])
    for line in lines[1:]:
        if quote in line:
            end_idx = line.index(quote)
            if end_idx > 0:
                docstring_lines.append(line[:end_idx])
            break
        docstring_lines.append(line)
    return "\n".join(docstring_lines).strip()


def find_first_file_path(structure: dict, prefix: str) -> str | None:
    """Recursively find the first file path in a package structure."""
    if structure.get("files"):
        return f"{prefix}/{sorted(structure['files'])[0]}.md"
    for subpkg_name in sorted(structure.get("subpackages", {}).keys()):
        result = find_first_file_path(
            structure["subpackages"][subpkg_name], f"{prefix}/{subpkg_name}"
        )
        if result:
            return result
    return None


# ——————————————————————————————————————————————————————————————————————————————————————
# DOCUMENTATION GENERATION


def generate_module_page(module_prefix: str, file_stem: str, file_path: Path) -> str:
    """Generate markdown content for a single module page."""
    title = format_module_title(file_stem)
    content = file_path.read_text()
    has_classes_or_functions = "def " in content or "class " in content

    if has_classes_or_functions:
        return (
            f"# {title}\n"
            f"\n"
            f"::: {module_prefix}.{file_stem}\n"
            f"    options:\n"
            f"      show_root_heading: False\n"
            f"      show_source: true\n"
            f"      heading_level: 2\n"
            f"      show_root_toc_entry: False\n"
        )
    else:
        parts = [f"# {title}\n"]
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("type ") and "=" in stripped:
                name = stripped.split("=")[0].replace("type ", "").strip()
                parts.append(f"## `{name}`\n")
                parts.append(f'???+ sourcecode ""')
                parts.append(f"")
                parts.append(f"    ```python")
                parts.append(f"    {stripped}")
                parts.append(f"    ```")
                parts.append(f"")
        return "\n".join(parts)


def generate_docs_recursive(
    package_dir: Path, docs_dir: Path, module_prefix: str, structure: dict
) -> None:
    """Recursively generate documentation for a package and its subpackages."""
    docs_dir.mkdir(parents=True, exist_ok=True)

    for file_stem in structure["files"]:
        file_path = package_dir / f"{file_stem}.py"
        md_content = generate_module_page(module_prefix, file_stem, file_path)
        (docs_dir / f"{file_stem}.md").write_text(md_content)

    for subpkg_name, subpkg_structure in structure["subpackages"].items():
        generate_docs_recursive(
            package_dir / subpkg_name,
            docs_dir / subpkg_name,
            f"{module_prefix}.{subpkg_name}",
            subpkg_structure,
        )


def build_nav_recursive(structure: dict, docs_prefix: str) -> list:
    """Recursively build navigation structure for mkdocs.yml."""
    nav_items = []

    for file_stem in sorted(structure["files"]):
        title = format_module_title(file_stem)
        nav_items.append({title: f"{docs_prefix}/{file_stem}.md"})

    for subpkg_name in sorted(structure["subpackages"].keys()):
        subpkg_nav = build_nav_recursive(
            structure["subpackages"][subpkg_name], f"{docs_prefix}/{subpkg_name}"
        )
        if subpkg_nav:
            title = format_package_title(subpkg_name)
            nav_items.append({title: subpkg_nav})

    return nav_items


def _overview_card(
    module: str, submodules: list[str], submodule_structure: dict
) -> str:
    """Generate a single overview card for a module or package."""
    docstring = get_module_docstring(module, submodules)

    if module in submodules:
        title = format_package_title(module)
        structure = submodule_structure.get(module)
        if not structure:
            return ""
        link_target = find_first_file_path(structure, module)
        if not link_target:
            return ""
        link_text = f"View `{module}` package API"
    else:
        title = format_module_title(module)
        link_target = f"{module}.md"
        link_text = f"View `{module}.py` API"

    card = f"-   __{title}__&nbsp;&nbsp;\n\n    ---\n\n"
    if docstring:
        indented = "\n    ".join(docstring.split("\n"))
        card += f"    {indented}\n\n"
    card += f"    [:material-link-variant: {link_text}]({link_target})\n\n"
    return card


def generate_overview(
    modules: list[str], submodules: list[str], submodule_structure: dict
) -> str:
    """Generate the overview page with navigation cards."""

    main_packages = [
        m
        for m in sorted(modules)
        if m in submodules and m not in SPECIAL_PURPOSE_PACKAGES
    ]
    special_packages = [
        m for m in sorted(modules) if m in submodules and m in SPECIAL_PURPOSE_PACKAGES
    ]
    standalone_modules = [m for m in sorted(modules) if m not in submodules]

    content = """---
hide:
#  - navigation
#  - toc
---

# Package Structure

## Main Namespaces

Namespaces needed for building and operating the trading infrastructure.

<div class="grid cards" markdown>

"""
    for module in main_packages:
        content += _overview_card(module, submodules, submodule_structure)

    for module in standalone_modules:
        content += _overview_card(module, submodules, submodule_structure)

    content += "</div>\n\n"

    if special_packages:
        content += """## Special-Purpose Namespaces 

Namespaces containing internal plumbing that usually does not need to be touched during 
regular operation. 

<div class="grid cards" markdown>

"""
        for module in special_packages:
            content += _overview_card(module, submodules, submodule_structure)

        if len(special_packages) == 1:
            content += "-   &nbsp;\n    { .card-placeholder }\n\n"

        content += "</div>\n"

    return content


# ——————————————————————————————————————————————————————————————————————————————————————
# MAIN


def main() -> None:
    if not SRC_PATH.exists() or not MKDOCS_PATH.exists():
        raise FileNotFoundError("Script must be run from the project root directory.")

    # Clean and recreate reference docs directory
    if DOCS_PATH.exists():
        shutil.rmtree(DOCS_PATH)
        logger.info(f"Cleaned existing documentation directory: {DOCS_PATH}")
    DOCS_PATH.mkdir(parents=True, exist_ok=True)

    # Discover modules
    py_files: list[str] = []
    submodules: list[str] = []
    submodule_structure: dict[str, dict] = {}

    for py_file in SRC_PATH.glob("*.py"):
        if py_file.name != "__init__.py":
            py_files.append(py_file.stem)

    for subdir in SRC_PATH.iterdir():
        if subdir.is_dir() and (subdir / "__init__.py").exists():
            submodules.append(subdir.name)
            submodule_structure[subdir.name] = discover_package_structure(
                subdir, f"{SRC_PACKAGE}.{subdir.name}"
            )

    modules = py_files + submodules
    logger.info(f"Found {len(modules)} modules: {', '.join(modules)}")

    # Generate module documentation pages
    for module in modules:
        submodule_dir = SRC_PATH / module

        if module in submodules:
            generate_docs_recursive(
                submodule_dir,
                DOCS_PATH / module,
                f"{SRC_PACKAGE}.{module}",
                submodule_structure[module],
            )
            logger.info(f"Generated docs for submodule: {module}")

        else:
            file_path = SRC_PATH / f"{module}.py"
            md_content = generate_module_page(SRC_PACKAGE, module, file_path)
            (DOCS_PATH / f"{module}.md").write_text(md_content)
            logger.info(f"Generated docs for module: {module}")

    # Generate overview page
    overview = generate_overview(modules, submodules, submodule_structure)
    (DOCS_PATH / "package_structure.md").write_text(overview)
    logger.info("Generated overview page")

    # Update mkdocs.yml navigation (preserves comments and formatting)
    with open(MKDOCS_PATH) as f:
        config = yaml.load(f)

    ref_nav: list = [{NAV_OVERVIEW: "reference/package_structure.md"}]

    for module in sorted(modules):
        if module in submodules and submodule_structure.get(module):
            title = format_package_title(module)
            sub_nav = build_nav_recursive(
                submodule_structure[module], f"reference/{module}"
            )
            if sub_nav:
                ref_nav.append({title: sub_nav})
        else:
            title = format_module_title(module)
            ref_nav.append({title: f"reference/{module}.md"})

    replaced = False
    for i, item in enumerate(config["nav"]):
        if isinstance(item, dict) and NAV_SECTION in item:
            config["nav"][i] = {NAV_SECTION: ref_nav}
            replaced = True
            break

    if not replaced:
        config["nav"].append({NAV_SECTION: ref_nav})

    with open(MKDOCS_PATH, "w") as f:
        yaml.dump(config, f)

    logger.info(f"Updated {MKDOCS_PATH}")
    logger.info(f"Done: {len(py_files)} files, {len(submodules)} submodules")


if __name__ == "__main__":
    main()
