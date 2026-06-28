# casino/client/__main__.py
# `python -m casino.client` entry point — delegates to client_cli.

from ..client_cli import main

raise SystemExit(main())
