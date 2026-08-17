---
name: mp4-defrag-fix
description: Detect and fix MP4/MOV/M4V files whose video data is split across many `mdat` atoms instead of one contiguous one — the cause of jellyfin-roku#834, where Jellyfin's official Roku client silently refuses to play the file (no error, no logs, playback just never starts). Use when a user reports an MP4 that won't play on Roku/Jellyfin, asks to check or diagnose MP4 atom fragmentation, or wants a fragmented MP4 remuxed/fixed without re-encoding.
---

# mp4-defrag-fix

CLI propio (`mp4defrag`) que diagnostica y arregla el bug
[jellyfin-roku#834](https://github.com/jellyfin/jellyfin-roku/issues/834):
el cliente Roku de Jellyfin falla silenciosamente con MP4 cuya data de
video quedó repartida en muchos átomos `mdat` (típico de archivos
reconstruidos desde HLS). El fix es un remux `-c copy` con `ffmpeg` —
nunca recodifica, cero pérdida de calidad.

## Setup (una sola vez por máquina)

```bash
command -v mp4defrag >/dev/null || pip install --user -e "$HOME/.claude/skills/mp4-defrag-fix"
```

`fix` además requiere `ffmpeg` en el PATH (`brew install ffmpeg` / `apt install ffmpeg`).

## Pasos

1. **Diagnosticar** con `check` antes de tocar nada:

   ```bash
   mp4defrag check <archivo_o_carpeta> [--recursive] [--json]
   ```

   Verdicto por archivo: `OK` o `FRAGMENTADO`, según la cantidad de
   átomos `mdat` contra `--threshold` (default 8). El threshold es
   heurístico — no hay límite oficial documentado por Roku, así que un
   archivo con muchos `mdat` que ya reproduce bien en Roku no es un
   falso positivo a corregir, es la señal de que el threshold local
   necesita subir.

2. Si el veredicto es `FRAGMENTADO`, **confirmar con el usuario** qué
   modo de `fix` quiere antes de ejecutar — la copia segura por
   defecto no requiere confirmación extra, pero `--in-place` sí es
   destructivo sin `--keep-backup`:

   - Por defecto: crea `<nombre> (fixed).mp4` junto al original, nunca lo toca.
   - `--output-dir DIR`: escribe los arreglados en otra carpeta.
   - `--in-place [--keep-backup]`: reemplaza el original — solo tras
     validar el remux; pedir confirmación explícita del usuario para
     este modo.
   - `--dry-run`: para mostrar el plan sin ejecutar `ffmpeg`.

3. **Ejecutar** `fix` con los flags acordados:

   ```bash
   mp4defrag fix <archivo_o_carpeta> [--recursive] [--in-place|--output-dir DIR] [--dry-run] --yes
   ```

   `fix` valida el remux (duración y streams vía `ffprobe`, y
   re-escaneo de `mdat` en la salida) antes de dar el fix por exitoso;
   si algo no cuadra, lo reporta como fallido y no toca el original.

4. **Reportar** al usuario el veredicto de `check` y, si corrió `fix`,
   la ruta del archivo resultante y si quedó validado.

## Referencia completa

Flags, formato de salida `--json`, y detalles de implementación del
parser de átomos: [`README.md`](README.md).
