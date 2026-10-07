"""Asset Commons catalogue engine.

Everything the app knows lives in one SQLite file under the app's storage
directory. The same modules serve three callers: the app's own UI (through
service.py), every agent on the instance (through the app's agent tools), and
the source sync job (sync.py). Nothing here imports Möbius code.
"""

VERSION = '0.5.0'
USER_AGENT = f'AssetCommons/{VERSION} (Mobius community app; open asset index)'
