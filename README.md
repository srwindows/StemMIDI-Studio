# StemMIDI Studio

**Versión 2.0 — macOS Intel (x86_64) — distribución de la aplicación y del código fuente**

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

**macOS Intel, versión 2.0:** abre el archivo `.dmg`, copia
`StemMIDI Studio.app` a Aplicaciones y ejecútala. El paquete lleva
su propio entorno de ejecución, FFmpeg/FFplay y SoundFont GM.
La primera vez permite elegir las IAs que se descargarán.
El paquete no está notarizado por Apple; según la configuración de
Gatekeeper puede requerir autorización manual en Privacidad y seguridad.

**Debian 13:** el código fuente y las instrucciones de la versión anterior
siguen documentados en la [guía Debian 13](docs/INSTALACION_DEBIAN.md).
La publicación 2.0 no se presenta como binario Debian actualizado.

La versión 2.0 está destinada a **macOS Intel**. Se compila con Python y
PyInstaller, incorporando sus bibliotecas y ejecutables de IA (sin los pesos
externos, que se ofrecen al usuario en el primer inicio). La versión 1.1.0
correspondía al código fuente de Debian 13. **La versión 3.0 para Windows
se preparará por separado.** La captura y escucha en hardware físico deben
comprobarse en cada equipo.

## Modelo entrenado compartido

Incluimos el modelo agregado de 42 perfiles:
[modelo multinstrumental](modelos_publicos/multinstrumental_markov_v1.json).
Son conteos y probabilidades de intervalos y transiciones de acordes;
**no son archivos MIDI, audio, letras ni canciones**. Hay un segundo
modelo opcional de aprendizaje sobre datos declarados CC0, en
composition_learned_model.json.

**No se distribuyen** los mas de 20.000 ficheros MIDI/KAR particulares
usados para el aprendizaje, ni ninguna de las 59 bases rítmicas originales.
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

No se conceden derechos sobre las canciones ni los ritmos privados originales
que no forman parte de esta distribucion.

## Notas de seguridad

- Activa manualmente Escucha procesada. Para micrófonos abiertos, utiliza
  auriculares y evita acoples.
- Vigila el nivel CLIP para no saturar la entrada.
- Los resultados de generacion musical necesitan revision antes de publicarse
  para no reproducir obras ajenas reconocibles.

**Versión 2.0 para macOS**: el código fuente y el paquete macOS se publican
por separado; los modelos externos no se adjuntan al instalador.
No se publica todavía la versión 3.0 destinada a Windows.


## Instalación inicial de modelos de IA

La distribución macOS ligera incorpora el motor de IA, el SoundFont GM y
el catálogo, **pero no incluye los pesos de los modelos de terceros**.
En un equipo nuevo, tras la intro, se abre un asistente que:

1. Muestra los 11 modelos verificados que se utilizaban en el desarrollo,
   distinguiendo los ya instalados y con tamaños medidos.
2. Permite elegir qué IA instalar; recomienda un conjunto de seis,
   sin iniciar descargas sin confirmación.
3. Verifica los archivos descargados (tamaño y SHA-256) antes de moverlos
   desde una carpeta temporal a la biblioteca.
4. Una vez terminado, ofrece abrir el catálogo de modelos opcionales,
   accesible en cualquier momento desde **Preferencias → Modelos de IA**.

Se puede posponer la descarga y utilizar los módulos sin IA. Las IAs externas
se descargan desde la fuente de sus autores, **no se redistribuyen desde
este repositorio**. Los enlaces y huellas de los modelos iniciales se
documentan en `first_run_models.json`; disponer de enlace de descarga no
implica que exista permiso de redistribución ni uso comercial.

En macOS, la biblioteca de modelos queda en
`~/Library/Application Support/StemMIDI Studio/modelos/`, separada
del ejecutable. No se borran modelos preexistentes. Un fallo de descarga
deja intacta la biblioteca anterior.

El empaquetado público macOS utiliza `StemMIDIStudio-macOS.spec` con
`STEMMIDI_MAC_BUNDLE_ALL_MODELS=0` (valor predeterminado). La opción
`=1` se reserva exclusivamente a pruebas locales con modelos que se tengan
instalados: no debe utilizarse para generar una publicación pública.

### Modelos propios integrados en macOS 2.0
La aplicación incluye de serie cuatro modelos estadísticos propios:
composition_learned_model.json,
modelos_publicos/multinstrumental_markov_v1.json,
stemmidi_drum_ai_trained_v1.json (944 perfiles anónimos),
genre_rhythm_trained_gm_v1.json (13 grupos rítmicos agregados).

No hace falta descargarlos ni instalarlos por separado. El asistente del primer
arranque se reserva para elegir las 11 IA externas disponibles y sus tamaños.
Los MIDI originales, patrones privados y pesos externos no forman parte del paquete.
