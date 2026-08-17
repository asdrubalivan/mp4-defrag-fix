# mp4-defrag-fix

CLI para detectar y arreglar archivos MP4 cuya data de video está
fragmentada en múltiples átomos `mdat` en vez de uno solo contiguo —
un patrón común en archivos reconstruidos desde streams HLS.

## El problema

El cliente oficial de Jellyfin para Roku falla **silenciosamente** al
reproducir estos archivos: no hay error, no hay logs, el reproductor
simplemente nunca solicita el stream. Es un bug conocido y documentado
del cliente Roku ([jellyfin-roku#834](https://github.com/jellyfin/jellyfin-roku/issues/834)),
no del servidor Jellyfin ni de la red.

`mp4defrag` detecta el patrón leyendo solo los headers de átomos
top-level del contenedor (rápido incluso en archivos de varios GB) y,
si hace falta, remuxea el archivo con `ffmpeg -c copy` para consolidar
la data en un único `mdat` — sin recodificar, cero pérdida de calidad.

## Instalación

Requiere Python 3.10+ y, para `fix`, `ffmpeg` en el `PATH`
(`brew install ffmpeg` / `apt install ffmpeg`).

```bash
pip install git+https://github.com/asdrubalivan/mp4-defrag-fix.git
```

O en local, para desarrollo:

```bash
git clone https://github.com/asdrubalivan/mp4-defrag-fix.git
cd mp4-defrag-fix
pip install -e ".[dev]"
```

## Uso

### `check` — diagnosticar

```bash
mp4defrag check pelicula.mp4
mp4defrag check ./Descargas --recursive
mp4defrag check pelicula.mp4 --threshold 8 --json
```

Reporta, por archivo, la cantidad de átomos `mdat`, el tamaño promedio
de fragmento y un veredicto `OK` / `FRAGMENTADO`. Sale con código
distinto de cero si algún archivo escaneado está fragmentado — útil en
scripts o CI. El threshold es heurístico y configurable: Roku no
documenta un límite oficial, y existen archivos con cientos de `mdat`
que igual reproducen bien.

### `fix` — remuxear sin recodificar

```bash
mp4defrag fix pelicula.mp4                       # crea "pelicula (fixed).mp4"
mp4defrag fix ./Descargas --recursive --output-dir ./arreglados
mp4defrag fix pelicula.mp4 --in-place --keep-backup
mp4defrag fix pelicula.mp4 --dry-run
```

Por defecto **nunca sobreescribe el original**: crea
`<nombre> (fixed).mp4` al lado del archivo de entrada. Antes de dar el
fix por exitoso, valida el remux comparando duración y conteo de
streams contra el original vía `ffprobe`, y re-escanea la salida para
confirmar que quedó en uno (o pocos) `mdat`. Si algo no cuadra, el fix
se marca como fallido y el original no se toca.

| flag | efecto |
|---|---|
| `--recursive` | procesa carpetas completas |
| `--in-place` | reemplaza el original, solo tras validar el remux |
| `--keep-backup` | con `--in-place`, conserva el original como `.bak` |
| `--output-dir DIR` | escribe los arreglados en otra carpeta |
| `--dry-run` | muestra qué se haría, no ejecuta `ffmpeg` |
| `--yes` | salta la confirmación interactiva |

## Cómo funciona

`mp4defrag` trae su propio parser de átomos ISO-BMFF (`mp4defrag/atoms.py`):
lee únicamente el header de cada átomo top-level (8 o 16 bytes) y salta
al siguiente usando el tamaño declarado, sin tocar el contenido — por
eso `check` escanea un archivo de varios GB en segundos. `fix` delega
el remux real a `ffmpeg -c copy -movflags +faststart`.

## Alcance

- No es un watcher/daemon en background.
- No recodifica video ni audio — siempre remux, cero pérdida de calidad.
- Pensado para MP4/MOV/M4V; MKV no sufre este problema (no usa `mdat`
  fragmentado de la misma forma).

## Desarrollo

```bash
pip install -e ".[dev]"
pytest
```

## Licencia

MIT — ver [LICENSE](LICENSE).
