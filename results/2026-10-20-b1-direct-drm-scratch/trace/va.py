# read bytes at a GPU VA from a trace submit dir
import json, sys, os
def load(sub):
    m = json.load(open(os.path.join(sub, 'manifest.json'))); return m
def read(sub, va, n):
    m = load(sub)
    for b in m['binds']:
        a = int(b['va'], 16)
        if a <= va < a + b['dumped']:
            with open(os.path.join(sub, 'bo-%x.bin' % a), 'rb') as f:
                f.seek(va - a); return f.read(n)
    raise KeyError(hex(va))
if __name__ == '__main__':
    sub, va, n = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3])
    sys.stdout.buffer.write(read(sub, va, n))
