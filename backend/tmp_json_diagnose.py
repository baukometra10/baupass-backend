import sys
import importlib.util
import os

print('sys.path:')
for p in sys.path[:20]:
    print(repr(p))

spec = importlib.util.find_spec('json')
print('json spec:', spec)
print('json path:', spec.origin if spec else None)

import json
print('json module file:', getattr(json, '__file__', None))
print('json package path:', getattr(json, '__path__', None))
print('scanner exists:', os.path.exists(os.path.join(os.path.dirname(spec.origin), 'scanner.py')))
