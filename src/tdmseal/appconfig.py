"""Valores por defecto del usuario (editorial, reserva TDM), persistidos localmente.

No es parte del algoritmo de sellado ni de TDMRep: es solo una comodidad para
no reescribir los mismos datos en cada sesión. Vive en el perfil del usuario
(`~/.tdmseal/config.json`), fuera del repositorio y de cualquier PDF.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from tdmseal.aipref import DEFAULT_PREFERENCES
from tdmseal.models import PublisherInfo

DEFAULT_CONFIG_PATH = Path.home() / ".tdmseal" / "config.json"


@dataclass
class AppDefaults:
    publisher: PublisherInfo = field(default_factory=PublisherInfo)
    reservation: int = 1
    policy_url: str | None = None
    # Preferencias IETF AIPREF (ver tdmseal/aipref.py), en forma `train-ai=n, ...`.
    aipref: str = DEFAULT_PREFERENCES


def load_defaults(path: Path = DEFAULT_CONFIG_PATH) -> AppDefaults:
    if not path.exists():
        return AppDefaults()
    data = json.loads(path.read_text(encoding="utf-8"))
    publisher_data = data.get("publisher", {})
    tdm_data = data.get("tdm", {})
    return AppDefaults(
        publisher=PublisherInfo(
            name=publisher_data.get("name"),
            acronym=publisher_data.get("acronym"),
            website=publisher_data.get("website"),
            rights_email=publisher_data.get("rights_email"),
        ),
        reservation=tdm_data.get("reservation", 1),
        policy_url=tdm_data.get("policy_url"),
        aipref=data.get("aipref") or DEFAULT_PREFERENCES,
    )


def save_defaults(defaults: AppDefaults, path: Path = DEFAULT_CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "publisher": asdict(defaults.publisher),
        "tdm": {"reservation": defaults.reservation, "policy_url": defaults.policy_url},
        "aipref": defaults.aipref,
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
