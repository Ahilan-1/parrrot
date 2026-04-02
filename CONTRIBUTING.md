# Contributing to Parrrot

We welcome contributions of all kinds — bug fixes, new tools, skills, documentation, and ideas.

## Setup for development

```bash
git clone https://github.com/Ahilan-1/parrrot
cd parrrot
pip install -e ".[dev,all]"
```

## Running tests

```bash
pytest
```

## Adding a new tool

1. Create or edit a file in `parrrot/tools/`
2. Write your function
3. Register it with `registry.register(...)` at the bottom of the file
4. The tool is automatically available in the agent

```python
from parrrot.tools.registry import registry

def my_tool(param: str) -> str:
    return f"Result: {param}"

registry.register(
    "my_tool",
    "Does something useful",
    {"param": "description of the parameter"},
)(my_tool)
```

## Adding a built-in skill example

Drop a `.py` file in `parrrot/skills/examples/` following the skill format in the README.

## Code style

- Python 3.11+
- `ruff` for linting: `ruff check .`
- No type: ignore comments unless truly necessary
- User-facing error messages in plain English — never raw tracebacks

## Pull requests

- Keep PRs focused on one thing
- Add tests for new functionality
- Update README if you add user-facing features
