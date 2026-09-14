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


def entries(path,method,*args,**kwargs):
    """Enumerate through Win32 spelling, return ordinary Paths for relative comparisons."""
    for value in getattr(fs(path),method)(*args,**kwargs):
        text=str(value)
        if text.startswith('\\\\?\\UNC\\'):text='\\\\'+text[8:]
        elif text.startswith('\\\\?\\'):text=text[4:]
        yield Path(text)


class FixtureTemporaryDirectory(tempfile.TemporaryDirectory):
    """Only fixture cleanup uses extended paths; product cleanup remains unpatched."""
    @classmethod
    def _rmtree(cls,name,ignore_errors=False,repeated=False):
        target=Path(name).resolve();allowed=output_root().resolve()
        # Prefix-normalized comparison before recursive deletion of this fixture.
        def normal(p):
            text=str(p)
            if text.startswith('\\\\?\\UNC\\'):text='\\\\'+text[8:]
            elif text.startswith('\\\\?\\'):text=text[4:]
            return Path(text)
        if not normal(target).is_relative_to(normal(allowed)) or normal(target)==normal(allowed):
            raise ValueError('Refusing fixture cleanup outside owned output root')
        return super()._rmtree(str(fs(target)),ignore_errors=ignore_errors,repeated=repeated)
