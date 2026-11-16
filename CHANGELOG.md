# Historial de StemMIDI Studio

## 2.0.0 — 2026-11-17 · macOS Intel

- Paquete macOS Intel autónomo con la interfaz, los motores de audio/IA,
  las herramientas nativas y SoundFont General MIDI.
- Instalador selectivo de 11 modelos de IA utilizados en el desarrollo,
  con seis recomendados y tamaños verificados.
- Descarga de pesos solo tras consentimiento; archivos temporales,
  validación SHA-256 e instalación reversible sin sobrescritura silenciosa.
- Catálogo de IAs adicionales en Preferencias → Modelos de IA.
- Los pesos externos no se incluyen en el instalador público.
- Se conserva el modelo agregado de composición propio, sin fuentes
  de entrenamiento ni colecciones MIDI de terceros.
- Cambios de interfaz y de módulos de macOS realizados desde 1.1.0.

**Limitaciones:** paquete Intel (no ARM nativo), firma ad hoc no notarizada.
Se recomienda validar captura del sistema, permisos y motores IA en
una instalación limpia antes de usarlo en producción.
La versión 3.0 para Windows queda pendiente.

## 1.1.0 — 2026-11-04

- Publicacion del estado actual de los modulos de StemMIDI Studio.
- Inicio 3×4 con intercambios exactos entre dos tarjetas.
- Pestañas profesionales MIDI→audio y Mezclador; presets vocales unificados.
- Resultados compacto y arrastre/copias de archivos entre modulos.
- EQ, ganancia y balance en la ruta PCM de grabacion.
- Analizadores de onda y espectro posprocesamiento, y escucha procesada
  opcional con seleccion de salida y proteccion contra realimentacion.
- Compositor MIDI/audio multipista y Piano Roll ampliado.
- Modelo estadistico multinstrumental agregado de 42 perfiles, sin subir
  canciones MIDI/KAR ni bases ritmicas originales.
- Documentacion, permisos, configuracion Git y pruebas publicas.

**Limitaciones verificables:** siguen pendientes verificaciones exhaustivas de escucha real sobre
hardware fisico y builds nativas Windows y macOS.

## 1.0 — 2026-10-27

Primera publicacion del codigo fuente. Historial preservado en Git.
