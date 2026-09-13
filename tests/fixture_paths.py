"""All test-owned writes belong to one explicit external run directory."""
import os
from pathlib import Path
import tempfile
import uuid


def fs(path):
    """Test-owned Win32 I/O spelling, independent of the product implementation."""
    text=os.path.abspath(path)
    if os.name=='nt' and not text.startswith('\\\\?\\'):
        text=('\\\\?\\UNC\\'+text[2:]) if text.startswith('\\\\') else ('\\\\?\\'+text)
    return Path(text)


def output_root():
    name = os.environ.get('AGENTLINK_TEST_OUTPUT_ROOT')
    if not name:
        name = str(Path(tempfile.gettempdir()) / ('agentlink-tests-' + uuid.uuid4().hex[:8]))
        os.environ['AGENTLINK_TEST_OUTPUT_ROOT'] = name
    root = Path(name)
    fs(root).mkdir(parents=True, exist_ok=True)
    return root
