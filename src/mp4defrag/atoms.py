"""Escáner ligero de átomos (boxes) top-level de contenedores MP4/ISO-BMFF.

Lee únicamente el header de cada átomo (8 o 16 bytes) para enumerar los
átomos de nivel superior sin cargar nunca la data de video en memoria.
Se usa para detectar el patrón detrás de jellyfin-roku#834: video partido
en múltiples átomos `mdat` en vez de uno solo contiguo.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Atom:
    type: str
    offset: int
    size: int  # tamaño total, incluyendo el header
    header_size: int


@dataclass
class ScanResult:
    path: Path
    file_size: int
    atoms: list[Atom] = field(default_factory=list)

    @property
    def mdat_atoms(self) -> list[Atom]:
        return [a for a in self.atoms if a.type == "mdat"]

    @property
    def mdat_count(self) -> int:
        return len(self.mdat_atoms)

    @property
    def avg_mdat_size(self) -> float:
        mdats = self.mdat_atoms
        if not mdats:
            return 0.0
        return sum(a.size for a in mdats) / len(mdats)

    def is_fragmented(self, threshold: int) -> bool:
        return self.mdat_count > threshold


def scan_top_level_atoms(path: Path) -> ScanResult:
    """Recorre solo los átomos de nivel superior de un archivo MP4/ISO-BMFF.

    Nunca lee el contenido de un átomo, solo su header — por lo que un
    archivo de varios GB se escanea en un número acotado de lecturas,
    proporcional a la cantidad de átomos top-level, no al tamaño del archivo.
    """
    file_size = path.stat().st_size
    atoms: list[Atom] = []
    with path.open("rb") as f:
        offset = 0
        while offset < file_size:
            f.seek(offset)
            header = f.read(8)
            if len(header) < 8:
                break
            size32, type_bytes = struct.unpack(">I4s", header)
            atom_type = type_bytes.decode("latin-1", errors="replace")
            header_size = 8

            if size32 == 1:
                ext = f.read(8)
                if len(ext) < 8:
                    break
                (size,) = struct.unpack(">Q", ext)
                header_size = 16
            elif size32 == 0:
                size = file_size - offset
            else:
                size = size32

            if size < header_size:
                # Header malformado o archivo truncado — mejor parar que
                # entrar en loop infinito.
                break

            atoms.append(
                Atom(type=atom_type, offset=offset, size=size, header_size=header_size)
            )
            offset += size

    return ScanResult(path=path, file_size=file_size, atoms=atoms)
