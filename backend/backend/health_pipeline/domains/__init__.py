"""Domain registry. Importing this module triggers each domain module to
register itself by exposing a module-level `DOMAIN` instance."""
from __future__ import annotations

from .base import Domain
from . import sleep as _sleep
from . import cardio as _cardio
from . import training as _training
from . import nutrition as _nutrition
from . import triage as _triage


DOMAIN_REGISTRY: dict[str, Domain] = {
    _sleep.DOMAIN.name: _sleep.DOMAIN,
    _cardio.DOMAIN.name: _cardio.DOMAIN,
    _training.DOMAIN.name: _training.DOMAIN,
    _nutrition.DOMAIN.name: _nutrition.DOMAIN,
    _triage.DOMAIN.name: _triage.DOMAIN,
}


__all__ = ["Domain", "DOMAIN_REGISTRY"]
