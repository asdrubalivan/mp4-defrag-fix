from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import typer

from . import __version__
from .atoms import scan_top_level_atoms

app = typer.Typer(
    name="mp4defrag",
    help=(
        "Detecta y arregla archivos MP4 con data de video fragmentada en "
        "múltiples átomos mdat — la causa de jellyfin-roku#834, donde el "
        "cliente de Jellyfin para Roku falla silenciosamente al reproducirlos."
    ),
    no_args_is_help=True,
)

DEFAULT_THRESHOLD = 8
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v"}


def _iter_input_files(path: Path, recursive: bool) -> list[Path]:
    if path.is_file():
        return [path]
    pattern = "**/*" if recursive else "*"
    return sorted(
        p
        for p in path.glob(pattern)
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    )


@app.command()
def check(
    target: Path = typer.Argument(..., exists=True, help="Archivo o carpeta a escanear."),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Escanear carpetas recursivamente."),
    threshold: int = typer.Option(
        DEFAULT_THRESHOLD, "--threshold", help="Máximo de átomos mdat antes de marcar FRAGMENTADO."
    ),
    as_json: bool = typer.Option(False, "--json", help="Salida en JSON."),
) -> None:
    """Escanea uno o varios MP4 y reporta si tienen data fragmentada en múltiples mdat."""
    files = _iter_input_files(target, recursive)
    if not files:
        typer.secho(f"No se encontraron archivos {sorted(VIDEO_EXTENSIONS)} en {target}", fg=typer.colors.YELLOW)
        raise typer.Exit(code=0)

    results = []
    any_fragmented = False
    for f in files:
        scan = scan_top_level_atoms(f)
        fragmented = scan.is_fragmented(threshold)
        any_fragmented = any_fragmented or fragmented
        results.append(
            {
                "file": str(f),
                "mdat_count": scan.mdat_count,
                "avg_mdat_size_bytes": round(scan.avg_mdat_size),
                "file_size_bytes": scan.file_size,
                "verdict": "FRAGMENTADO" if fragmented else "OK",
            }
        )

    if as_json:
        typer.echo(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        for r in results:
            color = typer.colors.RED if r["verdict"] == "FRAGMENTADO" else typer.colors.GREEN
            typer.secho(
                f"{r['file']}: {r['verdict']}  (mdat={r['mdat_count']}, avg={r['avg_mdat_size_bytes']:,} bytes)",
                fg=color,
            )

    raise typer.Exit(code=1 if any_fragmented else 0)


def _ffmpeg_path() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        typer.secho(
            "ffmpeg no está en el PATH. Instálalo con `brew install ffmpeg` (macOS) "
            "o `apt install ffmpeg` (Debian/Ubuntu) y vuelve a intentar.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)
    return exe


def _ffprobe_summary(path: Path) -> Optional[dict]:
    """Duración y conteo de streams vía ffprobe, para validar el remux."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    proc = subprocess.run(
        [
            ffprobe,
            "-v", "error",
            "-show_entries", "format=duration:stream=index",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    data = json.loads(proc.stdout)
    duration = float(data.get("format", {}).get("duration", 0.0))
    stream_count = len(data.get("streams", []))
    return {"duration": duration, "stream_count": stream_count}


def _remux(src: Path, dst: Path) -> None:
    ffmpeg = _ffmpeg_path()
    dst.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [ffmpeg, "-y", "-i", str(src), "-c", "copy", "-movflags", "+faststart", str(dst)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-2000:])


def _validate_remux(src: Path, dst: Path, threshold: int) -> tuple[bool, str]:
    src_info = _ffprobe_summary(src)
    dst_info = _ffprobe_summary(dst)
    if src_info and dst_info:
        dur_diff = abs(src_info["duration"] - dst_info["duration"])
        if dur_diff > max(1.0, src_info["duration"] * 0.01):
            return False, f"duración difiere: {src_info['duration']:.2f}s -> {dst_info['duration']:.2f}s"
        if src_info["stream_count"] != dst_info["stream_count"]:
            return False, f"streams difieren: {src_info['stream_count']} -> {dst_info['stream_count']}"

    scan = scan_top_level_atoms(dst)
    if scan.is_fragmented(threshold):
        return False, f"la salida sigue fragmentada ({scan.mdat_count} átomos mdat)"
    return True, "ok"


@app.command()
def fix(
    target: Path = typer.Argument(..., exists=True, help="Archivo o carpeta a arreglar."),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Procesar carpetas recursivamente."),
    in_place: bool = typer.Option(False, "--in-place", help="Reemplaza el original tras validar el remux."),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", help="Carpeta destino para los archivos arreglados."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Solo muestra qué se haría, no ejecuta ffmpeg."),
    yes: bool = typer.Option(False, "--yes", help="Salta la confirmación interactiva."),
    keep_backup: bool = typer.Option(
        False, "--keep-backup", help="Con --in-place, conserva el original como .bak."
    ),
    threshold: int = typer.Option(
        DEFAULT_THRESHOLD, "--threshold", help="Umbral de átomos mdat usado para la validación post-remux."
    ),
) -> None:
    """Remuxea (sin recodificar) para consolidar la data de video en un único mdat."""
    files = _iter_input_files(target, recursive)
    if not files:
        typer.secho(f"No se encontraron archivos {sorted(VIDEO_EXTENSIONS)} en {target}", fg=typer.colors.YELLOW)
        raise typer.Exit(code=0)

    if output_dir and in_place:
        typer.secho("--output-dir y --in-place son mutuamente excluyentes.", fg=typer.colors.RED)
        raise typer.Exit(code=2)

    if not dry_run and not yes:
        typer.confirm(f"¿Arreglar {len(files)} archivo(s)?", abort=True)

    if not dry_run:
        _ffmpeg_path()

    any_failed = False
    for src in files:
        if output_dir:
            dst = output_dir / src.name
        elif in_place:
            dst = src.with_name(f".{src.stem}.mp4defrag-tmp{src.suffix}")
        else:
            dst = src.with_name(f"{src.stem} (fixed){src.suffix}")

        if dry_run:
            typer.echo(f"[dry-run] {src} -> {dst}")
            continue

        typer.echo(f"Remuxeando {src} -> {dst} ...")
        try:
            _remux(src, dst)
        except RuntimeError as exc:
            any_failed = True
            typer.secho(f"FALLÓ el remux de {src}: {exc}", fg=typer.colors.RED)
            dst.unlink(missing_ok=True)
            continue

        ok, reason = _validate_remux(src, dst, threshold)
        if not ok:
            any_failed = True
            typer.secho(f"FALLÓ la validación de {src}: {reason}. El original no fue tocado.", fg=typer.colors.RED)
            dst.unlink(missing_ok=True)
            continue

        if in_place:
            if keep_backup:
                src.rename(src.with_suffix(src.suffix + ".bak"))
            else:
                src.unlink()
            dst.rename(src)
            typer.secho(f"OK: {src} arreglado in-place.", fg=typer.colors.GREEN)
        else:
            typer.secho(f"OK: {dst}", fg=typer.colors.GREEN)

    raise typer.Exit(code=1 if any_failed else 0)


@app.command()
def version() -> None:
    """Muestra la versión instalada."""
    typer.echo(__version__)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
