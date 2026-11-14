"""Explicit one-time provisioning only; never invoked during a chart request."""
import argparse
import hashlib
import os
from pathlib import Path
import tempfile
from urllib.request import urlopen

from .ephemeris import KERNEL_URL,KERNEL_SHA256,kernel_path


def provision(destination=None):
    target = Path(destination) if destination is not None else kernel_path()
    if target.exists():
        with target.open('rb') as source:
            if hashlib.file_digest(source,'sha256').hexdigest() == KERNEL_SHA256:
                return target
        raise ValueError('Existing file has an unexpected hash; it was not overwritten')
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='de440s_',dir=target.parent,delete=False) as output:
            temporary = Path(output.name)
            digest = hashlib.sha256()
            size = 0
            with urlopen(KERNEL_URL,timeout=60) as response:
                while chunk := response.read(1024*1024):
                    size += len(chunk)
                    if size > 32726016:
                        raise ValueError('Unexpected kernel size')
                    digest.update(chunk)
                    output.write(chunk)
        if size != 32726016 or digest.hexdigest() != KERNEL_SHA256:
            raise ValueError('Downloaded JPL kernel failed integrity verification')
        # Another provisioner cannot overwrite a file created concurrently.
        os.link(temporary,target)
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='Provision pinned JPL DE440s from NASA (explicit network request)')
    parser.add_argument('--output',type=Path,default=None)
    args = parser.parse_args()
    print(provision(args.output))


if __name__ == '__main__':
    main()
