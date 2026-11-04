# Modelo musical estadistico compartido

Archivo: modelos_publicos/multinstrumental_markov_v1.json

Este archivo es un modelo **simbolico de Markov**, no un sintetizador ni
una red neuronal. Contiene estadisticas agregadas de transiciones entre
grados de acordes y de intervalos melodicos. Tiene **42 perfiles**.

## Lo que NO contiene

- Ninguno de los mas de 20.000 archivos MIDI/KAR del corpus particular.
- Ninguna de las 59 bases ritmicas Roland originales.
- Archivos MIDI, audio, letras, titulos, nombres originales de canciones,
  muestras o secuencias de eventos completas de una cancion.
- Bases de datos, proyectos, configuraciones o rutas privadas.

## Procedencia y limitaciones

Las estadisticas proceden del aprendizaje sobre colecciones MIDI/KAR
particulares, que no se redistribuyen. No se garantiza que todos los
estilos musicales esten correctamente etiquetados. Las categorias
similares a ritmos del Roland representan aproximaciones estadisticas,
**no son generos verificados**.

Se ha verificado la ausencia de archivos fuente y cadenas identificativas
en la estructura JSON, pero esto no constituye un analisis juridico
exhaustivo ni una prueba absoluta de que nunca se reproduzcan parecidos
musicales reconocibles. Revisa las creaciones antes de redistribuirlas.

El programa prioriza un modelo local privado si el usuario lo posee;
si no, utiliza este modelo compartido. Sin modelo puede funcionar con
los algoritmos generativos integrados, segun el modulo.

Licencia del modelo estadistico agregado: PolyForm Noncommercial 1.0.0
para esta contribucion. El modelo independiente CC0 se identifica por
su propia etiqueta. No se otorgan derechos sobre los archivos originales.
