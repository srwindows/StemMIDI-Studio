# StemMIDI Studio

**Version 1.1.0 — Debian 13 — distribucion del codigo fuente**

Estudio modular de grabacion y produccion de audio y MIDI. Incluye Monitor,
grabacion, separacion de stems con modelos opcionales, audio a MIDI, bateria,
Mezclador, Resultados, Piano Roll, Compositor multipista, afinacion vocal y
conversion MIDI a audio con bancos SoundFont.

## Que incluye esta version

- Inicio con 12 tarjetas en tres filas de cuatro, intercambio de posiciones,
  ventanas flotantes y controles sincronizados con las pestanas profesionales.
- Monitor/Grabacion: ecualizacion, ganancia, balance, presets, vúmetros,
  osciloscopio y espectro **sobre el mismo PCM procesado**.
- Escucha procesada opcional y salida elegible, con proteccion contra la
  realimentacion cuando se captura el monitor de la misma salida.
- Resultados con vista compacta y envio de archivos por copia a otros
  modulos compatibles. El original no se elimina al arrastrar.
- Piano Roll y Compositor con edicion y herramientas musicales avanzadas.
- Motor estadistico de composicion multinstrumental y modelo CC0 opcional.

Las tareas y modelos de IA avanzados pueden requerir dependencias y
recursos externos que **no estan incluidos** en esta distribucion.

## Instalar y ejecutar

Ver [guia Debian 13](docs/INSTALACION_DEBIAN.md).
Se necesita Python, PySide6, FFmpeg/FFplay, PipeWire/PulseAudio y bibliotecas
de audio compatibles. Algunos modulos requieren SoundFonts o modelos
opcionales adicionales.

**Windows y macOS no se presentan como sistemas validados.**
Esta version se comprobo en Debian 13 con tests automatizados y validacion de
ventanas. La latencia y escucha final en hardware fisico deben verificarse
en cada instalacion.

## Modelo entrenado compartido

Incluimos el modelo agregado de 42 perfiles:
[modelo multinstrumental](modelos_publicos/multinstrumental_markov_v1.json).
Son conteos y probabilidades de intervalos y transiciones de acordes;
**no son archivos MIDI, audio, letras ni canciones**. Hay un segundo
modelo opcional de aprendizaje sobre datos declarados CC0, en
composition_learned_model.json.

**No se distribuyen** los mas de 20.000 ficheros MIDI/KAR particulares
usados para el aprendizaje, ni ninguna de las 59 bases ritmicas Roland.
Tampoco grabaciones, proyectos ni configuraciones personales.

Ver la [ficha tecnica y procedencia del modelo](docs/MODELO_MUSICAL.md).

## Colaborar

Consulta [CONTRIBUTING.md](CONTRIBUTING.md). Se aceptan informes de errores,
pruebas, documentacion y mejoras que no incorporen contenido protegido ni
datos privados. Los parametros de las ventanas de Inicio, pestañas y motores
de procesamiento deben permanecer sincronizados.

## Licencia y derechos

El codigo original y el modelo multinstrumental agregado se distribuyen con
la licencia actual [PolyForm Noncommercial 1.0.0](LICENSE). Esto **no es
software open source OSI**, y restringe el uso comercial. Las aportaciones
de terceros, los modelos externos y los datos CC0 mantienen sus condiciones
propias. Si se decide pasar a MIT/GPL, sera una decision de licencia separada.

No se conceden derechos sobre las canciones ni los ritmos Roland originales
que no forman parte de esta distribucion.

## Notas de seguridad

- Activa manualmente Escucha procesada. Para micrófonos abiertos, utiliza
  auriculares y evita acoples.
- Vigila el nivel CLIP para no saturar la entrada.
- Los resultados de generacion musical necesitan revision antes de publicarse
  para no reproducir obras ajenas reconocibles.

Este repositorio distribuye el **codigo fuente de la version 1.1.0**. No incluye actualmente
una compilacion Windows .exe ni un instalador macOS .dmg verificados.
