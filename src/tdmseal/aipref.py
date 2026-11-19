"""Preferencias de uso para IA según el vocabulario del IETF (AIPREF).

Fuentes (consultadas el 19-nov-2026, ver resources/SOURCES.md):

- draft-ietf-aipref-vocab-08 (14-sep-2026): categorías `train-ai` (entrenar
  modelos de IA generativa), `ai-use` (usar el contenido como entrada de un
  modelo generativo, p. ej. respuestas con recuperación) y `search` (buscar
  y enlazar). Valores `y` / `n`. Sintaxis: diccionario de Structured Fields
  (RFC 9651), p. ej. `train-ai=n, ai-use=n, search=y`.
- draft-ietf-aipref-attach-05 (19-ago-2026): cabecera HTTP `Content-Usage` y
  regla `Content-Usage:` en robots.txt. **No define cómo incrustar la
  preferencia en archivos** (sec. 1.3.1).

Son borradores, no RFC: el vocabulario puede cambiar. Por eso aquí solo se
aceptan las categorías del borrador vigente (un error de tecleo no debe
producir una señal que nadie entiende) y la versión se registra en cada
reporte.

Relación con TDMRep: TDMRep tiene un único interruptor (reservado o no) que
cubre toda la minería de textos y datos, entrenamiento de IA incluido.
AIPREF afina por uso. Si se niega `train-ai` o `ai-use`, la reserva TDMRep
debe ser 1; lo contrario sería contradictorio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

VOCAB_DRAFT = "draft-ietf-aipref-vocab-08"
ATTACH_DRAFT = "draft-ietf-aipref-attach-05"
CATEGORIES = ("train-ai", "ai-use", "search")
DEFAULT_PREFERENCES = "train-ai=n, ai-use=n, search=y"

_ITEM_RE = re.compile(r"^([a-z*][a-z0-9_.*-]*)=([a-z*][a-z0-9_.:/%*-]*)$")


class AiPrefError(ValueError):
    """Preferencia AIPREF mal escrita o con una categoría que el borrador no define."""


@dataclass(frozen=True)
class AiPreferences:
    """Preferencias por categoría: 'y', 'n' o None (sin declarar)."""

    values: tuple[tuple[str, str], ...]

    @classmethod
    def parse(cls, text: str) -> AiPreferences:
        """Lee `train-ai=n, search=y`. Rechaza categorías o valores desconocidos."""
        items: dict[str, str] = {}
        for raw in (text or "").split(","):
            item = raw.strip().split(";")[0].strip()  # los parámetros se ignoran (vocab §6)
            if not item:
                continue
            match = _ITEM_RE.match(item)
            if not match:
                raise AiPrefError(f"preferencia AIPREF mal escrita: {raw.strip()!r}")
            key, value = match.groups()
            if key not in CATEGORIES:
                raise AiPrefError(
                    f"categoría AIPREF desconocida: {key!r}. El borrador vigente "
                    f"({VOCAB_DRAFT}) define: {', '.join(CATEGORIES)}"
                )
            if value not in ("y", "n"):
                raise AiPrefError(f"valor AIPREF inválido para {key}: {value!r} (use y o n)")
            items[key] = value  # clave repetida: gana la última (vocab §6)
        if not items:
            raise AiPrefError("no se indicó ninguna preferencia AIPREF")
        ordered = tuple((c, items[c]) for c in CATEGORIES if c in items)
        return cls(ordered)

    def get(self, category: str) -> str | None:
        return dict(self.values).get(category)

    def serialize(self) -> str:
        """Forma de Structured Fields para `Content-Usage`: `train-ai=n, search=y`."""
        return ", ".join(f"{k}={v}" for k, v in self.values)

    def denies_ai(self) -> bool:
        return self.get("train-ai") == "n" or self.get("ai-use") == "n"

    def check_consistency(self, tdm_reservation: int) -> list[str]:
        """Avisos si la preferencia contradice la reserva TDMRep."""
        if self.denies_ai() and tdm_reservation == 0:
            return [
                "Contradicción: AIPREF niega usos de IA pero tdm-reservation es 0 "
                "(TDM permitido). Si se reservan los usos de IA, use tdm-reservation 1."
            ]
        return []

    def to_report(self) -> dict:
        return {
            "content_usage": self.serialize(),
            "categories": dict(self.values),
            "vocabulary": VOCAB_DRAFT,
            "attachment": ATTACH_DRAFT,
            "embedded_in_file": False,
            "note": (
                "AIPREF no define todavía cómo incrustar la preferencia en PDF ni EPUB "
                f"({ATTACH_DRAFT}, sec. 1.3.1); se expresa en la cabecera HTTP "
                "Content-Usage y en robots.txt (ver `tdmseal site`)."
            ),
        }


def default_preferences() -> AiPreferences:
    return AiPreferences.parse(DEFAULT_PREFERENCES)
