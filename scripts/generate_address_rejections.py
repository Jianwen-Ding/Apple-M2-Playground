#!/usr/bin/env python3
"""Generate LLVM IR for address-candidate pruning compilation measurements."""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--candidates', type=int, default=50000)
    args = parser.parse_args()
    if args.candidates < 1:
        parser.error('--candidates must be positive')
    with args.output.open('w') as stream:
        stream.write('define agx_kernel void @reject(ptr addrspace(1) %out, i64 %a) {\n')
        for index in range(1, args.candidates + 1):
            stream.write(f'  %x{index} = add i64 %a, {index}\n'
                         f'  store volatile i64 %x{index}, ptr addrspace(1) %out\n')
        stream.write('  ret void\n}\n')


if __name__ == '__main__':
    main()
