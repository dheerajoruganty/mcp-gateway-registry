#!/usr/bin/env python3
"""
Fix OpenSearch Serverless (AOSS) compatibility issues in repository files.

This script:
1. Adds _is_aoss() helper method if not present
2. Wraps all client.index() calls with custom IDs in conditional logic
3. Wraps all client.delete() calls with refresh=True in conditional logic
4. Handles both create and update operations
"""

import re
import sys
from pathlib import Path


def add_is_aoss_method(content: str) -> str:
    """Add _is_aoss() helper method if not present."""
    if "_is_aoss(self)" in content:
        print("  ✓ _is_aoss() method already exists")
        return content

    # Find the location after _get_client() method
    pattern = r"(    async def _get_client\(self\) -> AsyncOpenSearch:.*?return self\._client\n)"
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        print("  ✗ Could not find _get_client() method")
        return content

    is_aoss_method = """

    def _is_aoss(self) -> bool:
        \"\"\"Check if using AWS OpenSearch Serverless (which doesn't support custom IDs).\"\"\"
        return settings.opensearch_auth_type == "aws_iam"
"""

    content = content[:match.end()] + is_aoss_method + content[match.end():]
    print("  ✓ Added _is_aoss() method")
    return content


def fix_client_index_with_id(content: str) -> str:
    """Fix client.index() calls that use custom IDs and refresh=True."""

    # Pattern for index with id and refresh=True
    pattern = r"""([ \t]*)(await client\.index\(
        [ \t]*index=self\._index_name,
        [ \t]*id=(\w+),
        [ \t]*body=(\w+),
        [ \t]*refresh=True
        [ \t]*\))"""

    def replace_index(match):
        indent = match.group(1)
        doc_id_var = match.group(3)
        body_var = match.group(4)

        replacement = f"""{indent}if self._is_aoss():
{indent}    # AOSS doesn't support custom IDs or refresh=true
{indent}    await client.index(
{indent}        index=self._index_name,
{indent}        body={body_var}
{indent}    )
{indent}else:
{indent}    await client.index(
{indent}        index=self._index_name,
{indent}        id={doc_id_var},
{indent}        body={body_var},
{indent}        refresh=True
{indent}    )"""
        return replacement

    content_new = re.sub(pattern, replace_index, content, flags=re.VERBOSE | re.MULTILINE)

    if content_new != content:
        count = len(re.findall(pattern, content, flags=re.VERBOSE | re.MULTILINE))
        print(f"  ✓ Fixed {count} client.index() calls with custom IDs")

    return content_new


def fix_client_delete_with_refresh(content: str) -> str:
    """Fix client.delete() calls that use refresh=True."""

    # Pattern for delete with refresh=True (multi-line)
    pattern = r"""([ \t]*)(await client\.delete\(
        [ \t]*index=self\._index_name,
        [ \t]*id=(\w+),
        [ \t]*refresh=True
        [ \t]*\))"""

    def replace_delete(match):
        indent = match.group(1)
        doc_id_var = match.group(3)

        replacement = f"""{indent}if self._is_aoss():
{indent}    # AOSS doesn't support refresh=true
{indent}    await client.delete(
{indent}        index=self._index_name,
{indent}        id={doc_id_var}
{indent}    )
{indent}else:
{indent}    await client.delete(
{indent}        index=self._index_name,
{indent}        id={doc_id_var},
{indent}        refresh=True
{indent}    )"""
        return replacement

    content_new = re.sub(pattern, replace_delete, content, flags=re.VERBOSE | re.MULTILINE)

    if content_new != content:
        count = len(re.findall(pattern, content, flags=re.VERBOSE | re.MULTILINE))
        print(f"  ✓ Fixed {count} client.delete() calls with refresh=True")

    return content_new


def process_file(file_path: Path) -> bool:
    """Process a single repository file."""
    print(f"\nProcessing {file_path.name}...")

    try:
        content = file_path.read_text()
        original_content = content

        # Apply fixes
        content = add_is_aoss_method(content)
        content = fix_client_index_with_id(content)
        content = fix_client_delete_with_refresh(content)

        # Write back if changed
        if content != original_content:
            file_path.write_text(content)
            print(f"  ✓ Updated {file_path.name}")
            return True
        else:
            print(f"  - No changes needed for {file_path.name}")
            return False

    except Exception as e:
        print(f"  ✗ Error processing {file_path.name}: {e}")
        return False


def main():
    """Main function."""
    repo_dir = Path(__file__).parent.parent / "registry" / "repositories" / "opensearch"

    # Files to process (excluding ones already fixed manually)
    files_to_process = [
        "scope_repository.py",
        "security_scan_repository.py",
        "federation_config_repository.py",
        "search_repository.py",
    ]

    print("=" * 60)
    print("AOSS Compatibility Fixer")
    print("=" * 60)

    updated_count = 0
    for filename in files_to_process:
        file_path = repo_dir / filename
        if file_path.exists():
            if process_file(file_path):
                updated_count += 1
        else:
            print(f"\n✗ File not found: {filename}")

    print("\n" + "=" * 60)
    print(f"Summary: Updated {updated_count} of {len(files_to_process)} files")
    print("=" * 60)


if __name__ == "__main__":
    main()
