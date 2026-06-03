"""Trading Platform backend (FastAPI modular monolith).

The platform kernel lives in :mod:`app.core`; bounded domain modules live in
:mod:`app.modules`. The same package powers both the API process
(:mod:`app.main`) and the ARQ worker (:mod:`app.worker`).
"""

__version__ = "0.1.0"
