# PRD: mp4-defrag-fix

## Problema

El cliente oficial de Jellyfin para Roku falla silenciosamente al reproducir archivos MP4
cuya data de video está fragmentada en múltiples átomos `mdat` en vez de uno solo
contiguo (patrón común en archivos reconstruidos desde streams HLS). No hay error,
no hay logs, el reproductor simplemente nunca solicita el stream. Es un bug conocido
y documentado del cliente Roku ([jellyfin-roku#834](https://github.com/jellyfin/jellyfin-roku/issues/834)),
no del servidor Jellyfin ni de la red.

## Objetivo

Una herramienta CLI simple, instalable vía pip, que:
1. Detecte si uno o varios archivos MP4 tienen este problema de fragmentación excesiva.
2. Ofrezca remuxearlos (sin recodificar) para consolidar la data en un único `mdat`,
   resolviendo la incompatibilidad con Roku (y potencialmente otros clientes limitados).

## No-objetivos

- No es un watcher/daemon en background (posible v2, no en este alcance).
- No tiene GUI.
- No recodifica video/audio (siempre remux `-c copy`, cero pérdida de calidad).
- No soporta contenedores distintos a MP4/MOV/M4V (MKV no tiene este problema).

## Usuarios

Self-hosters de Jellyfin (u otro media server) con clientes Roku/smart TV que
descargan o reciben archivos MP4 de fuentes variadas (rips, conversores HLS, etc.)
y quieren diagnosticar/arreglar problemas de reproducción antes de que ocurran.

## Requerimientos funcionales

### Comando `check`

```
mp4defrag check <archivo_o_carpeta> [--recursive] [--threshold N] [--json]
```

- Escanea el/los archivo(s) MP4 leyendo únicamente los headers de átomos top-level
  (parser propio, ligero — sin dependencia de ffprobe para este paso).
- Reporta por archivo: cantidad total de átomos `mdat`, tamaño promedio de fragmento,
  y un veredicto `OK` / `FRAGMENTADO` según `--threshold` (default sugerido: >8 átomos
  `mdat` se considera sospechoso; ajustable porque no hay un límite oficial documentado
  por Roku).
- `--recursive` para escanear carpetas completas.
- `--json` para salida parseable (integraciones futuras).
- Exit code no-cero si algún archivo escaneado está fragmentado (útil para scripts/CI).

### Comando `fix`

```
mp4defrag fix <archivo_o_carpeta> [--recursive] [--in-place] [--output-dir DIR] [--dry-run] [--yes]
```

- Requiere `ffmpeg` en PATH; si no está, error claro con instrucción de instalación.
- Por defecto: **nunca sobreescribe el original**. Crea `<nombre> (fixed).mp4` al lado
  del original (mismo comportamiento validado manualmente en la sesión de debugging).
- `--in-place`: tras un remux exitoso Y verificado (ver validación abajo), reemplaza el
  original (con backup `.bak` opcional vía `--keep-backup`).
- `--output-dir DIR`: escribe los archivos arreglados en otra carpeta, preservando nombres.
- `--dry-run`: solo muestra qué se haría, no ejecuta ffmpeg.
- `--yes`: salta la confirmación interactiva (para uso scripteado).
- Internamente ejecuta: `ffmpeg -i <in> -c copy -movflags +faststart <out>`.
- **Validación post-remux** (antes de considerar el fix exitoso): comparar duración
  (`RunTime`/duration) y conteo de streams del archivo de salida contra el original
  (vía el mismo parser de átomos o un check ligero de duración) — si difieren
  significativamente, marcar el fix como fallido y no tocar el original.
- Solo re-escanea el archivo de salida para confirmar que quedó en 1 (o pocos) `mdat`.

### Comando `version` / `--help`

Estándar de Typer, sin requerimientos especiales.

## Requerimientos no funcionales

- **Stack**: Python 3.10+, [Typer](https://typer.tiangolo.com/) para la CLI,
  empaquetado con `pyproject.toml` (build backend `hatchling` o `setuptools`, a elección
  al implementar).
- **Dependencias externas**: `ffmpeg` (requerido solo para `fix`, no para `check`).
- **Multiplataforma**: macOS y Linux como objetivo principal (Windows best-effort).
- **Rendimiento**: `check` debe poder escanear un archivo de varios GB en segundos,
  leyendo solo headers de átomos (8-16 bytes por átomo), nunca el archivo completo.
- **Seguridad de datos**: ninguna operación destruye el original salvo que el usuario
  pida explícitamente `--in-place` (y aun así, solo tras validar el remux).
- **Open source**: MIT license (sugerido, confirmar con el usuario antes de publicar),
  repo nuevo en GitHub, README con el contexto del bug de Roku y ejemplos de uso.

## Métricas de éxito

- Un archivo fragmentado conocido (caso real de la sesión de debugging) es detectado
  correctamente por `check` y arreglado correctamente por `fix`, quedando reproducible
  en el cliente Roku de Jellyfin.
- Cero falsos positivos en archivos MP4 "normales" (ej. `Lupin.mp4` del caso real,
  ~1074 mdat pero que sí funciona en Roku — el threshold debe calibrarse para no
  marcarlo como problemático, o el PRD debe reconocer que el threshold es heurístico
  y exponerlo como configurable, no un valor fijo interno).

## Futuro / fuera de alcance v1

- Modo watcher/daemon que vigile una carpeta de descargas.
- Integración directa como plugin de Jellyfin.
- Soporte para detectar y arreglar otros patrones de incompatibilidad de Roku
  (más allá de fragmentación de mdat), si aparecen reportados.
