# StemMIDI Studio 1.1.1 — Debian 13, amd64

Revisión de mantenimiento de Debian, independiente de la versión 2.0 de macOS.
Incluye de serie los cuatro modelos estadísticos propios:
composition_learned_model.json,
modelos_publicos/multinstrumental_markov_v1.json,
stemmidi_drum_ai_trained_v1.json (944 perfiles anonimizados) y
genre_rhythm_trained_gm_v1.json (13 familias General MIDI agregadas).

El compositor puede utilizar los perfiles rítmicos GM de forma local.
El botón «Batería IA» genera notas MIDI del canal 10 a partir de
parámetros aprendidos, sin copiar archivos MIDI originales.

Compilación comprobada con Debian 13, Python 3.13, PyInstaller 6.22.2,
NumPy 2.5.3 y SciPy 1.16.3. SciPy forma parte del ejecutable; no depende
de que el usuario lo instale en el sistema.

Las IA de terceros no se redistribuyen, ni se incluyen las colecciones
privadas de entrenamiento. El instalador Debian 1.1.1 no debe
confundirse con el asistente de selección de IA de la versión 2.0 macOS.

Las pruebas de arranque automatizadas no sustituyen la validación del
hardware de audio y MIDI de cada ordenador.
