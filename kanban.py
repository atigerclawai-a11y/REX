#!/usr/bin/env python3
"""Kanban board tools — read/write Obsidian Kanban plugin boards.
Usage: python3 kanban.py status "REX Build"
       python3 kanban.py move "Fix auth" --to "Done" --board "REX Build"
       python3 kanban.py list
"""

import sys, os, re, json

VAULT = os.path.expanduser("~/Documents/GHS-Vault")
HOME = os.path.expanduser("~/.hermes/rexxie_vault/kanban_cache")
os.makedirs(HOME, exist_ok=True)

def find_boards():
    """Find all Kanban boards in the vault."""
    boards = {}
    for root, dirs, files in os.walk(VAULT):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if f.endswith('.md'):
                path = os.path.join(root, f)
                try:
                    with open(path, 'r') as fh:
                        content = fh.read(5000)
                    if 'kanban-plugin' in content:
                        name = f.replace('.md', '')
                        boards[name] = path
                except Exception:
                    pass
    return boards

def parse_kanban(content):
    """Parse a Kanban markdown file into lists and items."""
    lists = {}
    current_list = None
    
    for line in content.split('\n'):
        list_match = re.match(r'^##\s+(.+)$', line)
        item_match = re.match(r'^-\s+\[(.)\]\s+(.+)$', line)
        
        if list_match:
            current_list = list_match.group(1)
            lists[current_list] = []
        elif item_match and current_list:
            checked = item_match.group(1) != ' '
            text = item_match.group(2)
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
            lists[current_list].append({
                'text': text,
                'done': checked,
                'date': date_match.group(1) if date_match else None
            })
    
    return lists

def cmd_list():
    """List all Kanban boards with summary."""
    boards = find_boards()
    if not boards:
        return "No Kanban boards found."
    
    lines = ["# Kanban Boards\n"]
    for name, path in sorted(boards.items()):
        with open(path) as f:
            content = f.read()
        parsed = parse_kanban(content)
        total = sum(len(items) for items in parsed.values())
        cols = ' | '.join(f"{col}: {len(items)}" for col, items in parsed.items())
        lines.append(f"**{name}** — {total} items ({cols})")
    
    return '\n'.join(lines)

def cmd_status(board_name):
    """Show a specific board's status."""
    boards = find_boards()
    
    # Fuzzy match
    matches = [name for name in boards if board_name.lower() in name.lower()]
    if not matches:
        return f"Board '{board_name}' not found. Available: {', '.join(boards.keys())}"
    if len(matches) > 1:
        return f"Multiple matches: {', '.join(matches)}. Be more specific."
    
    name = matches[0]
    with open(boards[name]) as f:
        content = f.read()
    parsed = parse_kanban(content)
    
    lines = [f"# {name}\n"]
    for col, items in parsed.items():
        lines.append(f"## {col} ({len(items)})")
        for item in items:
            check = 'x' if item['done'] else ' '
            lines.append(f"- [{check}] {item['text'][:100]}")
        lines.append("")
    
    return '\n'.join(lines)

def cmd_move(task_name, to_list, board_name=None):
    """Move a task between columns."""
    boards = find_boards()
    
    if board_name:
        matches = [name for name in boards if board_name.lower() in name.lower()]
        if not matches:
            return f"Board '{board_name}' not found."
        name = matches[0]
    else:
        name = list(boards.keys())[0] if boards else None
        if not name:
            return "No boards found."
    
    path = boards[name]
    with open(path) as f:
        content = f.read()
    
    parsed = parse_kanban(content)
    
    # Find the task
    found_col = None
    found_item = None
    for col, items in parsed.items():
        for item in items:
            if task_name.lower() in item['text'].lower():
                found_col = col
                found_item = item
                break
        if found_col:
            break
    
    if not found_item:
        return f"Task '{task_name}' not found on board '{name}'."
    
    if to_list not in parsed:
        return f"Column '{to_list}' not found. Available: {', '.join(parsed.keys())}"
    
    # Move: remove from source, add to destination
    old_line = f"- [{'x' if found_item['done'] else ' '}] {found_item['text']}"
    new_line = f"- [ ] {found_item['text']} \u2190 moved from {found_col}"
    
    new_content = content.replace(old_line, '', 1)
    # Add to destination column
    dest_header = f"## {to_list}"
    new_content = new_content.replace(dest_header, f"{dest_header}\n{new_line}")
    
    with open(path, 'w') as f:
        f.write(new_content)
    
    return f"✅ Moved '{found_item['text'][:60]}' from {found_col} → {to_list} on '{name}'"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "list":
        print(cmd_list())
    elif cmd == "status":
        print(cmd_status(sys.argv[2] if len(sys.argv) > 2 else ""))
    elif cmd == "move":
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("task")
        parser.add_argument("--to", required=True)
        parser.add_argument("--board")
        args = parser.parse_args(sys.argv[2:])
        print(cmd_move(args.task, args.to, args.board))
    else:
        print(f"Unknown: {cmd}")