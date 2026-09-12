"""All test-owned writes belong to one explicit external run directory."""
import os
from pathlib import Path
import tempfile
import uuid


def output_root():
    name = os.environ.get('AGENTLINK_TEST_OUTPUT_ROOT')
    if not name:
        name = str(Path(tempfile.gettempdir()) / ('agentlink-tests-' + uuid.uuid4().hex[:8]))
        os.environ['AGENTLINK_TEST_OUTPUT_ROOT'] = name
    from app.storage import io_path
    root = Path(name)
    io_path(root).mkdir(parents=True, exist_ok=True)
    return root
