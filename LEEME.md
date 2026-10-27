# Monitor de Grabación (Debian 13)

Aplicación PySide6 para **supervisar y grabar el audio del ordenador** a través de los monitores de salida PipeWire/PulseAudio. El audio del sistema no se modifica ni se duplica en altavoces; se captura de la salida elegida mediante parec. Los medidores y el analizador de espectro muestran la señal en tiempo real.

## Abrir

Desde el gestor de archivos, abre el lanzador **Monitor_de_Grabacion.desktop** o ejecuta:

```bash
bash "/media/javi/Recuperacion/Monitor_de_Grabacion/lanzar.sh"
```

La aplicación arranca la supervisión automáticamente; pulsa **● Iniciar grabación** para comenzar y **■ Detener grabación** para finalizar el archivo correctamente.

## Formatos

- WAV (PCM, 16 bits): sin compresión
- FLAC: compresión sin pérdida
- MP3: codificación LAME de alta calidad
- OGG Vorbis: calidad variable
- Opus: 160 kb/s
- AAC/M4A: 256 kb/s

La captura se efectúa a 48 kHz, estéreo, con PCM de 16 bits. La calidad final depende de la fuente; FLAC evita pérdidas adicionales.

## Fuentes

El menú incluye las salidas monitor del ordenador: USB, HDMI u otras disponibles. Opcionalmente muestra micrófonos y entradas. Al cambiar el dispositivo, detén la supervisión y vuelve a iniciarla.

## Archivos y recursos

Todo reside en el disco Recuperación:

- `main.py`: interfaz gráfica
- `audio_engine.py`: captura y compresión de audio
- `widgets.py`: visualizadores de señal
- `grabaciones/`: grabaciones terminadas
- `configuracion.json`: preferencias (aparece al guardar)
- `pruebas/`: utilidades de comprobación
- `lanzar.sh`: lanzador autónomo
- `Monitor_de_Grabacion.desktop`: lanzador gráfico

Dependencias ya detectadas en el equipo: Debian 13, Python 3, PySide6, NumPy, PipeWire/PulseAudio, parec y FFmpeg. No es necesario un entorno virtual ni copiar dependencias al sistema.

## Solución de problemas

**Los indicadores no se mueven:** verifica que el menú de fuente corresponde al dispositivo por el que el ordenador está reproduciendo el audio. El monitor solo muestra sonido mientras esa salida lo recibe.

**Audio del micrófono:** activa "Incluir micrófonos", detén la supervisión, pulsa "Actualizar" y elige la entrada.

**No graba:** comprueba permisos de escritura y espacio disponible en la carpeta de destino; los mensajes detallados aparecerán en el registro de la aplicación.

**Retirar el disco:** detén primero cualquier grabación y cierra el programa. Nunca desconectes el disco durante la codificación de un archivo.

## Seguridad

No se cambia ningún dispositivo de audio predeterminado ni se abre o modifica un flujo de micrófono a menos que se elija explícitamente. No se sobrescriben grabaciones existentes.

## Separación de pistas con inteligencia artificial

Pulsa **Separar pistas musicales (IA)…** en la ventana principal.

1. Elige un archivo de audio (puede ser una grabación realizada en el programa o una canción importada).
2. Elige el tipo de separación y el formato de exportación.
3. Pulsa **Separar pistas**.
4. Cada pista aparecerá en la lista de resultados. Selecciónala para escucharla o abre la carpeta de archivos.

**Modos disponibles:**

- **2 pistas IA:** voces e instrumental, modelo UVR-MDX-NET-Inst_HQ_3.
- **4 pistas IA:** voces, batería, bajo y resto, modelo Demucs htdemucs.
- **6 pistas IA:** voces, batería, bajo, guitarra, piano y resto, modelo Demucs htdemucs_6s.
- **2 canales L/R:** separa canales izquierda/derecha mediante FFmpeg sin inferencia.

**Archivos:**

- `separador.py`: interfaz y cola de trabajos; escucha y exportación de pistas
- `entorno_ia/`: dependencias de inferencia aisladas; CPU sin CUDA
- `modelos/`: modelos de IA descargados (sin necesitar red para usarlos después)
- `cache_ia/`: caché específica del proyecto
- `pistas_separadas/`: resultados organizados en subcarpetas individuales
- `constraints-cpu.txt`: versiones compatibles con el procesador sin bibliotecas NVIDIA

La separación por IA no es instantánea: en CPU tarda más que la duración de la grabación para algunas canciones y depende del modelo elegido. **No equivale a disponer de los multitracks originales:** algunos instrumentos pueden filtrarse a otras pistas, especialmente en mezclas complejas.

El motor de inferencia utilizado es **audio-separator**, con modelos UVR y Demucs. Su código y las condiciones de redistribución pertenecen a sus respectivos titulares. Se ejecuta localmente, sin subir el audio.

No se sobrescribe ni se altera el archivo original. El programa puede seguir monitorizando audio mientras se calcula la separación en otro proceso. Si se cancela un trabajo, pueden quedar archivos parciales en su carpeta de salida.

**Pruebas hechas en Debian 13:** análisis de fuentes, grabación en FLAC, los seis formatos de captura, separación L/R con tonos distintos y separación neuronal a 2, 4 y 6 pistas. Estas pruebas verifican el funcionamiento técnico, no la calidad perceptual sobre música real.

## Actualización Studio (23 de octubre de 2026)

### Modelos de estudio y controles de calidad
- **MelBand Roformer**: modelo adicional especializado en voz/instrumental.
- **Demucs HT afinado (Fine Tuned)**: modelo nuevo para cuatro pistas, más exigente que el rápido.
- Los anteriores MDX, Demucs y Demucs 6 pistas siguen disponibles.
- **Calidad normal / alta / máxima**: controlan las predicciones desplazadas de Demucs y el solapamiento entre bloques. Las configuraciones más altas consumen más CPU y tiempo. La calidad perceptiva depende de la canción, no hay garantía de separación perfecta.
- Los nuevos modelos también están instalados localmente en `modelos/`; no se envía audio a internet.

### Mezclador multipista
Cuando termina la separación, pulsa **Mezclador multipista…**. La ventana permite:
- ajustar el nivel de cada pista entre 0 y 150 % (fader y valor en dB);
- activar MUTE o SOLO de cada instrumento;
- elegir el punto de comienzo de una preescucha de 20 segundos (se renderiza antes de sonar);
- exportar una mezcla completa en FLAC, WAV PCM 24 bits o MP3 de alta calidad, sin sobrescribir los stems;
- cancelar el proceso de exportación antes de terminar.

Puedes volver a cargar una carpeta de pistas de un trabajo anterior. Los archivos de preescucha se eliminan al detener o cerrar el mezclador. Los ajustes del separador se guardan en `preferencias_separador.json` en el propio disco Recuperación.

### Pruebas adicionales
- Demucs FT: generación correcta de cuatro stems FLAC.
- MelBand Roformer: generación correcta de dos stems FLAC (voces y resto/instrumental).
- Exportación del mezclador: comprobada con MUTE y un fader a -4,4 dB; WAV PCM de 24 bits validado por FFprobe.
- Separación completa desde el diálogo gráfico con el nuevo modelo Demucs FT: cuatro archivos creados y reconocidos.
- Interfaz: revisadas disposición, desplazamiento y alineación de controles.

**Importante**: las pruebas automáticas usaron audio sintético y validan el procesamiento y los ficheros. Para confirmar la mejora *audible* respecto a los modelos antiguos aún hace falta comparar música real con referencias de calidad conocidas. El modelado por IA no recupera necesariamente las pistas máster originales.

## Módulo Audio a MIDI — 23 de octubre de 2026

Se ha añadido **Convertir AUDIO a MIDI…** en la ventana principal y **Convertir pistas a MIDI…** dentro del separador de instrumentos.

### Automático (recomendado)
1. Selecciona un archivo WAV, MP3, FLAC, etcétera.
2. Activa **Modo AUTOMÁTICO**.
3. Opcionalmente deja activado **Separar instrumentos automáticamente antes de generar el MIDI**. El programa separará la canción en 4 pistas (Demucs FT) o 6 pistas, convertirá cada una y las incluirá en un único MIDI multipista.
4. Puedes activar la estimación automática de tempo. Si el detector no determina un valor fiable, utilizará 120 BPM como referencia, no un BPM supuestamente real.
5. Pulsa **Convertir a MIDI**. Se escribirá un archivo `.mid` de tipo 1, acompañado de un informe `.json` con métodos, notas detectadas y tempo.

Las pistas de audio separadas automáticamente se conservan en una subcarpeta de destino `<nombre>_STEMS_<fecha>` para permitir escuchar y volver a procesar resultados sin repetir la separación.

### Parámetros avanzados
Desmarca **Modo AUTOMÁTICO** para acceder a:
- Umbral de inicio de nota (onset), entre 0,10 y 0,95
- Umbral de nota sostenida, entre 0,10 y 0,90
- Duración mínima de nota, de 40 a 2000 milisegundos
- Rango de alturas MIDI, de 21 a 108
- Sensibilidad de golpes de batería
- Tempo manual o detección automática
- Cuantización opcional a 1/4, 1/8, 1/16 y 1/32; por defecto respeta la ejecución

El programa puede transcribir una **carpeta de stems** ya separados: cada archivo se procesa individualmente y crea una pista con su nombre, programa General MIDI y canal independiente. La batería utiliza el canal 10 (índice 9). Hasta 16 pistas por trabajo.

### Motores de transcripción y precisión
- **Basic Pitch** (Spotify, ONNX): detector local polifónico (voz, bajo, guitarra, piano y otras fuentes tonales). El modelo ONNX se incluye en el entorno Python aislado.
- **Transkun V2** (Yujia Yan): detector especializado en piano polifónico. Se utiliza por defecto cuando se reconoce una pista etiquetada como Piano. Se puede desactivar en la interfaz; en caso de error del motor se utiliza Basic Pitch.
- **Batería**: extracción **aproximada** de golpes y clasificación por energía espectral en notas General MIDI 36/38/42. No es un modelo de transcripción de percusión de alta precisión, especialmente para toms, platos y redobles.
- En el flujo automático se omiten los restos casi silenciosos de un instrumento separados por Demucs, evitando falsas notas cuando el instrumento no existe en la canción.

Estos motores reconstruyen una **estimación MIDI**, NO los eventos MIDI originales que se grabaron en estudio. La separación, el audio fuente y el instrumento condicionan la exactitud. Los resultados admiten corrección en un secuenciador MIDI.

### Pruebas efectuadas
- Cinco notas sintéticas conocidas → cinco notas MIDI correctas (Basic Pitch).
- Piano sintetizado a partir de MIDI → cinco notas reconocidas por Transkun.
- Batería + bajo + piano en fuentes independientes → MIDI tipo 1 con tres pistas y canales General MIDI correctos.
- Parámetros manuales y cuantización 1/16 a 120 BPM → cinco notas alineadas con la rejilla.
- Flujo único: fuente WAV → separación Demucs FT en 4 stems → MIDI válido (MIDI tipo 1, cinco pistas incluida la de tempo).
- Corrección del reconocimiento de etiquetas de stems `(Bass)`, `(Drums)`, `(Other)`, `(Vocals)`: la fuente original puede contener palabras como `piano` sin provocar clasificación errónea.
- Corrección de residuos casi silenciosos en una prueba de solo piano: tres stems residuales quedaron sin notas; el instrumento real mantuvo sus cinco notas estimadas.
- Prueba automatizada desde PySide6 (ventana real, sin conexión gráfica física): MIDI creado correctamente y mostrado en la tabla.

### Archivos
- `midi_engine.py`: motor de conversión y creación del MIDI
- `midi_dialog.py`: interfaz gráfica automática y avanzada
- `midi_generados/`: MIDI finales, informes y stems automáticos
- `preferencias_midi.json`: parámetros recordados en el disco Recuperación
- `entorno_ia/`: Basic Pitch, Transkun, ONNX Runtime, Mido, Pretty-MIDI y dependencias CPU

No se han instalado dependencias del proyecto en la partición del sistema Debian. La transcripción se realiza localmente, y los archivos originales no se modifican.

### Avisos
La estimación automática de BPM puede ser incorrecta para rubato, ritmos sincopados o piezas sin percusión. Un MIDI musicalmente correcto puede requerir edición posterior. Para mejores resultados, evita MP3 de calidad baja, utiliza FLAC/WAV y separa los instrumentos antes de transcribir.

## Importación universal para separación y conversión a MIDI (23/10/2026)

### Dos rutas de importación, un solo motor
Los botones **Separar pistas musicales (IA)…** y **Convertir AUDIO a MIDI…** tienen un botón **Importar audio…**. También permiten arrastrar y soltar un archivo local directamente sobre el campo de ruta.

El selector incluye **Todos los archivos**, de modo que la compatibilidad se decide con un examen real de sus pistas de audio mediante FFprobe, no por la extensión del nombre. Si un vídeo contiene audio, se utiliza su primera pista de audio; los fotogramas y subtítulos se ignoran. Para Audio a MIDI multipista también se puede importar una **carpeta de stems** arrastrándola al campo de carpeta o mediante el explorador.

Formatos de entrada habituales cubiertos por el FFmpeg local: WAV, WAV RF64, FLAC, MP3, MP2, OGG/Vorbis, OGG Opus, AAC, M4A/ALAC, WMA, AIFF, AU, CAF, WavPack, APE y diversos formatos de PCM. También se admiten archivos MP4, MKV, MOV, AVI, WEBM, MPG, MPEG y otros contenedores multimedia **cuando tienen una pista de audio decodificable**.

Es imposible garantizar literalmente todos los formatos del mundo: **no** se admiten flujos cifrados con DRM, archivos dañados, proyectos de DAW que no sean audio y determinados códecs privativos/RAW sin parámetros. Cuando FFmpeg no reconoce audio, se muestra el error antes de generar ninguna separación o MIDI.

### Normalización interna y seguridad
- Un importador común: audio_import.py (sondeo FFprobe y conversión FFmpeg); audio_import_gui.py (selección y arrastrar y soltar).
- Cada entrada se decodifica internamente a **FLAC PCM 24 bits, 44,1 kHz estéreo**, sin volver a aplicar compresión perceptual. Esto **no restaura** detalle perdido previamente en fuentes MP3/AAC.
- El separador mantiene la copia temporal dentro de la propia carpeta del trabajo, en _importacion_temporal, y la borra tras terminar o cancelar. La carpeta temporal no aparece entre los resultados.
- El conversor MIDI utiliza una carpeta temporal de importación por trabajo dentro del destino y la elimina al finalizar; la separación opcional por IA genera stems independientes que sí se conservan.
- No se modifican los archivos originales. Todo queda en Recuperación.
- Si falla un decodificador, se informa del formato/archivo que no pudo leerse sin inventar pistas o notas.

### Verificación del importador
- FFmpeg/FFprobe 7.1.5 del equipo, sin instalación de códecs de terceros en el sistema.
- Entradas WAV, FLAC, MP3, OGG Opus, AAC/M4A, WMA y AIFF: decodificación a FLAC 24 bits 44,1 kHz verificada.
- Audio AAC de MP4: extracción y conversión correctas.
- Archivo con extensión desconocida pero contenido FLAC: reconocido por su contenido.
- Vídeo MP4 sin audio: rechazo con mensaje explícito.
- Arrastrar/soltar una ruta MP3 al campo Qt: reconocido y admitido.
- Separación desde GUI de MP4 a L/R: dos pistas FLAC exportadas.
- Separación neuronal desde GUI de WMA: cuatro pistas FLAC exportadas con Demucs.
- MIDI a partir de WMA, Opus y M4A: archivos MIDI válidos generados, sin temporales restantes.
- MIDI desde GUI a partir de un MP4 con sonido: salida MID validada, nota 69 reconocida.

### Nota al abrir la actualización
En la sesión de desarrollo se encontró una **conversión MIDI del usuario en ejecución**; no se interrumpió ni se reinició la instancia activa para proteger la grabación, los stems y el MIDI. El código nuevo está instalado en Recuperación; al cerrar normalmente y volver a abrir la aplicación después de terminar ese trabajo aparecerá la versión actualizada.

## Previsualización integrada de archivos (23/10/2026)

La aplicación cuenta con el componente `preview_player.py`, un reproductor Qt Multimedia reutilizable para audio y MIDI. Los reproductores muestran el archivo seleccionado, su formato/duración, transporte (reproducir/pausar/detener), barra de búsqueda, posición actual, volumen y velocidad 0,75×/1×/1,25×. Los controles de fuente y resultado de la misma ventana evitan reproducirse simultáneamente.

**Dónde aparece:**
- **Ventana principal:** escuchar la última grabación guardada sin abrir un programa externo.
- **Separar pistas:** reproductor del audio original antes de extraer; reproductor de la pista extraída seleccionada. El doble clic reproduce esa pista. Cambiar de fila prepara la pista correcta y no reproduce otra por error.
- **Audio a MIDI:** reproductor del archivo de audio que se convertirá; puedes escoger una pista de la carpeta de stems o pulsar «Cargar MIDI para escuchar…» para previsualizar un MIDI fuente externo. El MIDI convertido se carga automáticamente en un segundo reproductor al terminar.
- **Mezclador:** selector y reproductor de stems fuente; segundo reproductor para la premezcla renderizada de 20 s y para la mezcla completa exportada.

Los audios se reproducen con Qt Multimedia y su backend FFmpeg. Si el backend no puede reproducir un códec, intenta preparar una copia FLAC de escucha, sin alterar el original. Los MIDI no se reproducen como audio digital hasta que TiMidity los sintetiza a una copia temporal WAV; la síntesis se inicia solamente al pulsar Reproducir. Todos los temporales se escriben en `previsualizaciones_temporales/` dentro del disco Recuperación y se eliminan al sustituir el archivo o cerrar el reproductor. Las premezclas de 20 s también se limpian al detener el mezclador.

**Pruebas efectivas en Debian:**
- QMediaPlayer + QAudioOutput reprodujeron PCM/WAV; pausa, cambio de posición y duración correctos.
- MIDI multipista real: TiMidity generó el audio en disco Rescate, QMediaPlayer lo reprodujo con duración 03:08 y se borró el WAV temporal en la limpieza.
- Audio a MIDI real desde la interfaz: MIDI generado, reconocido por el reproductor y reproducido tras síntesis diferida.
- Separador: vista previa asociada correctamente al cambio de fila y doble clic en pistas extraídas MP3.
- Mezclador: los dos reproductores visibles junto a MUTE/SOLO; preescucha FLAC de 20 s ejecutada, reproducida y eliminada; exportación FLAC completa cargada en el reproductor.
- Maquetación adaptada con scroll vertical para que los controles del mezclador no oculten los faders ni la lista de pistas.

**Límite:** la previsualización MIDI es una interpretación sintetizada aproximada usando el banco TiMidity del ordenador y no tiene por qué sonar igual que el instrumento original; el archivo MIDI y sus eventos no se modifican.

## Bibliotecas de resultados y editor Piano Roll (23/10/2026)

### Ventana 1: Biblioteca de separaciones
Desde la ventana principal pulsa **Biblioteca de separaciones…**. Al terminar cada separación correcta, esta ventana se abre automáticamente y muestra una fila por cada pista extraída de ese trabajo.

- Trabajos agrupados por carpeta, con nombre, tipo, tamaño y fecha.
- Seleccionar una pista permite previsualizarla; doble clic inicia la reproducción.
- **Mezclar pistas…** abre el mezclador de instrumentos de ese trabajo.
- **Convertir carpeta a MIDI…** envía todas las pistas a la transcripción multipista.
- **Añadir carpeta…** permite recuperar resultados antiguos guardados en una ubicación diferente, sin mover los archivos.
- El índice bibliotecas.json, almacenado en Recuperación, recuerda las carpetas y resultados de nuevos trabajos.

### Ventana 2: Biblioteca MIDI
Pulsa **Biblioteca MIDI y Piano Roll…** en la ventana principal. Tras finalizar una conversión correcta, se abre automáticamente la biblioteca enfocada en el archivo recién generado.

- Lista y agrupa los MIDI por su carpeta de origen/destino.
- Permite escuchar una conversión con el reproductor MIDI integrado.
- Doble clic sobre un MIDI, o **Abrir piano roll…**, abre el editor.
- **Importar MIDI externo…** permite editar también cualquier archivo MID/MIDI válido de tipo 0/1.
- Las copias editadas se registran en la biblioteca para poder abrirlas después.

### Editor de piano roll
Nuevo módulo piano_roll.py, construido en PySide6/QGraphicsScene y con lectura/escritura MIDI mediante Mido:

- Pistas MIDI seleccionables y separadas, incluidas las pistas de tempo y batería en canal 10.
- Teclado vertical cromático, cuadrícula por compases y rejilla de notas.
- Doble clic en hueco vacío = dibujar nota; arrastrar = mover nota; arrastrar el borde derecho = ajustar duración.
- Clic derecho sobre una nota o tecla Supr = eliminar.
- Editar velocidad de la nota seleccionada.
- Zoom horizontal y cuantización 1/4, 1/8, 1/16, 1/32, 1/64; botón para cuantizar una pista entera.
- Copiar y pegar nota, deshacer/rehacer (Ctrl+Z/Ctrl+Y).
- Piano roll enfoca automáticamente la octava donde se encuentra la música de la pista seleccionada.
- **Guardar MIDI editado…** propone un nombre distinto, nunca sobrescribe el original y preserva todos los eventos de la canción ajenos a las notas (tempo, compás, programas, CC, pitch bend, metadatos).
- El reproductor integrado escucha el MIDI original o la última versión guardada, no los cambios todavía sin guardar.

### Seguridad y almacenamiento
Todo se ejecuta y se registra en /media/javi/Recuperacion/Monitor_de_Grabacion. El archivo bibliotecas.json solo contiene rutas, no sonidos ni contenido MIDI. Las carpetas originales y los MIDI originales no se modifican por consultar, editar o reproducir.

### Pruebas reales del nuevo módulo
- MIDI tipo 1 de 3 pistas: leer y editar notas, undo/redo, copiar/pegar, borrar, cuantizar y exportar MIDI válido.
- Verificación de conservación de tempo, dos controles MIDI CC, dos pitch bend y canal 10 de batería.
- Dibujo interactivo mediante doble clic y deshacer en un MIDI de **1.500 notas**, dibujado en la GUI.
- Biblioteca MIDI: abre un archivo encontrado, luego abre directamente su piano roll.
- Biblioteca de stems: muestra cuatro FLAC de batería, bajo, voz y otros; abre el mezclador de cuatro pistas.
- Separación desde GUI: tras separar un WAV en dos MP3, se abre automáticamente la biblioteca con ambas pistas.
- Conversión desde GUI: tras convertir WAV a MIDI, la biblioteca aparece automáticamente y abre su piano roll.

Los motores de separación y Audio a MIDI mantienen sus limitaciones propias; el editor permite corregir los eventos MIDI resultantes sin repetir la transcripción.

## Rediseño integrado — una sola interfaz y resultados temporales (23/10/2026)

La aplicación se organiza ahora en una ventana principal con pestañas internas:

- **Monitor / Grabación:** supervisión del sonido del equipo, vúmetro compacto, analizador y grabadora.
- **Separar audio:** fuente + parámetros de extracción en el panel izquierdo; resultados de la tarea en el derecho.
- **Audio a MIDI:** archivo o carpeta de origen, parámetros automáticos/manuales y resultado MIDI multipista en el mismo espacio.
- **Piano Roll:** edición MIDI a pantalla ancha, sin abrir otra ventana.
- **Audio guardado** y **MIDI guardado:** bibliotecas para consultar archivos ya publicados.
- **Mezclador:** se incorpora como una pestaña adicional cuando se utiliza, sin ventana flotante.

Se han reducido botones, campos de entrada, espaciados y vúmetro. Cada pista resultante tiene **▶ Play**, **■ Stop**, casilla de selección y previsualización integrada; solo se reproduce una pista por vez en cada panel.

### Flujo para separar audio
1. En **Separar audio**, pulsa **Importar audio…** o arrastra un archivo al campo de origen.
2. Elige modelo (2, 4 o 6 stems), calidad y formato de salida; pulsa **Separar pistas**.
3. El motor escribe sus resultados exclusivamente bajo `tareas_temporales/separaciones/<identificador>/` en Recuperación. No se publica ningún resultado sin autorización.
4. Escucha por separado las pistas en las filas del panel derecho. Marca/desmarca cada una.
5. **Guardar todo** copia todas las pistas a una carpeta definitiva elegida con el explorador. **Guardar selección** copia únicamente las casillas marcadas. **Nueva tarea / Descartar** elimina solo el directorio temporal de la tarea después de confirmar.
6. Las pistas guardadas se pueden localizar en **Audio guardado**. Se puede enviar una separación temporal al conversor MIDI sin guardarla antes.

### Flujo para convertir audio a MIDI
1. En **Audio a MIDI**, importa un archivo de audio o una carpeta de pistas. Puedes elegir separación automática 4/6 stems previa.
2. Pulsa **Convertir a MIDI**; el motor guarda su MIDI completo solo en `tareas_temporales/midi/<identificador>/`.
3. Se generan pistas MIDI independientes en la zona temporal, con su propio Play/Stop. El reproductor sintetiza cada archivo MIDI con TiMidity.
4. **Guardar todo** publica el MIDI completo y sus pistas por separado. **Guardar selección** publica solo los MIDI correspondientes a las pistas marcadas.
5. Si quieres corregir notas, pulsa **Editar en Piano Roll**. Edita dentro de la pestaña; **Aplicar edición a la tarea temporal** registra el MIDI corregido como resultado provisional. Solo **Guardar todo/selección** publica las correcciones definitivamente.
6. **Nueva tarea / Descartar** elimina temporalmente lo no guardado, con confirmación. El original nunca se toca.

### Persistencia y seguridad
- `task_staging.py`: gestión de trabajos provisionales, selección parcial, publicación por copia íntegra y borrado controlado.
- `workspace_ui.py`: controlador de paneles y navegación en la ventana única.
- `tareas_temporales/`: resultados transitorios en el disco Recuperación, con manifiestos `ACTIVA.json` para recuperarse después de cerrar o de una interrupción inesperada. Las tareas no guardadas **no se borran automáticamente al salir**.
- Las bibliotecas permanentes solo se actualizan después de utilizar Guardar; no incluyen resultados meramente temporales.
- Nunca se sobrescriben archivos definitivos: ante colisión de nombres se añade sufijo numérico.
- Nunca se borra un directorio fuera del espacio temporal al descartar una tarea.
- Si otra operación sigue procesando archivos de una tarea, no se permite descartarla.
- El editor MIDI preserva tempo, pistas, controles y mensajes originales al escribir una nueva copia.

### Pruebas efectuadas en Debian 13
- Todas las páginas incrustadas con flags de widget: sin ventanas auxiliares, una sola ventana principal.
- Grabadora y vúmetro reducido a una franja de 58–72 píxeles; botones de 11 px y altura compacta.
- WAV -> separación L/R -> dos FLAC provisionales -> Play/Stop -> se guardó únicamente uno -> descartar temporal sin perder el archivo publicado ni el original.
- WAV -> MIDI provisional -> un MIDI de pista guardado parcialmente -> edición de altura en piano roll -> aplicación a MIDI temporal -> Guardar todo -> descartar provisional sin perder los archivos publicados.
- MIDI externo -> importación temporal -> piano roll integrado -> original conservado y limpieza del temporal.
- Manifiestos para reabrir trabajos no guardados y limpieza con reintentos en disco NTFS.
- No se interrumpieron ni modificaron las canciones y grabaciones del usuario.

## Reparación de reproducción y selección de dispositivo — 23/10/2026

**Problema observado:** PipeWire tenía seleccionada por defecto la salida de cuatro canales `FANTOM-06 07 08 Pro`, mientras que también existía `USB Audio and HID Estéreo analógico`. El reproductor Qt utilizaba la salida predeterminada; podía avanzar la posición sin que el sonido llegara a los altavoces conectados a la otra salida.

**Corrección:**
- En la parte superior de Monitor / Grabación aparece **SALIDA DE ESCUCHA**. Los reproductores de audio, cada stem y los MIDI cuentan también con un selector **Salida de escucha**.
- El dispositivo elegido se aplica a todos los reproductores de inmediato y se recuerda en `salida_audio_preview.json`, dentro de Recuperación.
- Como elección inicial, si PipeWire tiene por defecto una salida multicanal, se prefiere una salida analógica estéreo disponible. En el equipo la detectada es **USB Audio and HID Estéreo analógico**.
- Es posible seleccionar expresamente **FANTOM-06 07 08 Pro** o **Audio Interno Estéreo digital (HDMI)** si son los dispositivos a los que se conectaron los altavoces.
- **No se modifica el dispositivo predeterminado de Debian** ni el motor de grabación.
- Corregidos los campos donde se escribía manualmente una ruta: al confirmar la ruta ahora se carga en el reproductor de previsualización.
- El selector dispone de fila propia para no comprimir los deslizadores de volumen, velocidad y posición.

**Prueba de enrutamiento:** QMediaPlayer con un WAV estéreo creado para validación avanzó su posición durante reproducción y PipeWire registró un nuevo flujo en el sumidero **59 (USB Audio and HID analógico)**. Se verificaron también selección y sincronización global con la salida Roland, reversión a USB analógico y persistencia del dispositivo elegido.

**Importante:** detectar un flujo en PipeWire confirma el enrutamiento del programa, pero no la conexión física de altavoces/auriculares. Elige el dispositivo donde realmente escuchas el equipo.

## 2026-10-23 — Corrección de tiempo de separación

La separación de la canción `tontxu` (aprox. 3:10) ejecutada el 23/oct/2026 tardó más de 22 minutos usando **Demucs FT** en **calidad Alta**, con `--demucs_shifts 2` y `--demucs_overlap 0.50`. El preset FT combina **cuatro modelos** (ver `modelos/htdemucs_ft.yaml`); Demucs rápido combina solo **uno** (ver `modelos/htdemucs.yaml`). Dos pasadas multiplican todavía más el coste.

Se detectó paralelamente `linthesia` utilizando aproximadamente el 800 % de CPU (8 hilos lógicos) en este i9-9880H de 16 hilos. No se cerró ni modificó ese proceso ajeno, ni se interrumpió la separación.

**Cambio realizado:** para las tareas nuevas el perfil seleccionado por defecto es `4 pistas · RÁPIDO — Demucs` con `Normal (más rápido)`. Usa `--demucs_shifts 1` y `--demucs_overlap 0.25`. Los modelos ESTUDIO, 6 pistas y los niveles Alta/Máxima siguen disponibles para trabajos en los que importe más la calidad.

Las preferencias se actualizaron en `preferencias_separador.json`. Existe también una migración de la combinación antigua FT+Alta al perfil rápido al abrir la nueva versión si aún no se ha confirmado la migración; la elección explícita posterior se respeta.

**Prueba real:** fragmento de 8 s de la propia grabación `tontxu` → 4 pistas FLAC generadas con Demucs rápido en 28 s, ejecutándose simultáneamente con Linthesia. Este tiempo no debe extrapolarse directamente a canciones completas, ya que la inicialización, la longitud y la carga del equipo influyen.

**El trabajo lento original terminó y se preservó íntegro** en su directorio temporal, con voz, batería, bajo y otros. No se ha publicado ni descartado, pendiente de la decisión del usuario.

La aplicación que estuviera abierta antes de editar el código debe cerrarse normalmente y volver a abrirse para usar el nuevo motor. No se forzó su cierre para evitar perder estados de edición todavía no guardados.

## 23/10/2026 — Restauración de reproducción y velocidad original

Diagnóstico del audio: Qt Multimedia generaba una señal de reproducción anormalmente tenue en la salida Roland FANTOM Pro. En una muestra de prueba, la monitorización de PipeWire midió un pico cercano a 0,00017 con Qt, frente a 0,0066–0,0078 usando FFplay con el mismo archivo. La comprobación se hizo con audio de prueba; no demuestra el estado físico de los altavoces.

Ahora preview_player.py utiliza FFplay con salida PulseAudio/PipeWire estéreo, seleccionada en la propia interfaz. Mantiene Play, Pausa/Continuar, Stop, cursor de búsqueda, velocidad y volumen. La previsualización MIDI emplea TiMidity y reproduce su WAV temporal a través del mismo backend. El archivo original no se altera. La señal FFplay fue comprobada en el monitor de la salida Roland con un pico 0,007843 y un flujo estéreo de 2 canales.

Rendimiento: el registro inicial pruebas/test_ia.log confirma que la primera versión usaba htdemucs.yaml, un único modelo. Más adelante se sustituyó por htdemucs_ft.yaml, un conjunto de cuatro modelos especializados, y dos pasadas de análisis con solapamiento 0,5. Linthesia consumía simultáneamente más de ocho núcleos lógicos. Se ha restaurado el perfil Demucs original de una pasada y solapamiento 0,25 en preferencias. El perfil FT sigue disponible para quien quiera ejecutar ese procesamiento más costoso.

La antigua instancia se cerró mediante la solicitud de cierre normal del gestor de ventanas, respetando su protección de ediciones, y se inició la nueva por lanzar.sh. Se comprobó que las cuatro pistas temporales de tontxu continúan presentes, sin borrado ni publicación automática.

## 23 de octubre de 2026: optimización Audio a MIDI y supervisión

**Diagnóstico de la tarea actual:** a las 19:17 (hora peninsular), el proceso iniciado a las 18:58 llevaba aproximadamente 19 minutos en separación IA. La entrada original era la pista `(Other)_htdemucs_ft.mp3` de «tontxu», ya separada previamente. En la configuración figuraba `separate_first=true`, por lo que el motor volvió a invocar `htdemucs_ft.yaml`, dos shifts y overlap 0,5 antes de intentar transcribir notas. No era todavía el cálculo de notas MIDI; estaba repitiendo la extracción de instrumentos. El proceso antiguo sigue ejecutándose, **no se ha cancelado ni modificado**, y sus temporales tampoco se han borrado.

**Cambios de código para futuras tareas:**
- `stem_detection.py` detecta stems de Demucs/MDX/Roformer a partir de nombres/etiquetas reconocibles y contextos de carpetas de extracciones. Se evita confundir títulos ordinarios con stems.
- `midi_dialog.py` desmarca separación previa al importar un instrumento que ya está separado. También impide re-separarlo si el usuario teclea directamente su ruta o mantiene una preferencia antigua marcada.
- `midi_engine.py` comprueba independientemente el fichero de origen, evitando relanzar Demucs incluso si llega un JSON antiguo con `separate_first=true`. Informa del salto en el registro y continúa con transcripción MIDI directa.
- Para mezclas completas que sí necesitan separar, la vía de cuatro instrumentos recupera `htdemucs.yaml` (modelo original de un solo conjunto) con una sola pasada y solapamiento 0,25, en lugar del ensemble FT de cuatro modelos con dos pasadas.
- `main.py` ya NO activa automáticamente la supervisión al abrir el programa. Al pasar a Separar audio / Audio a MIDI o al reproducir una previa, detiene la supervisión cuando no hay grabación. Si se está grabando, respeta y mantiene esa captura.

**Pruebas:** detector de stems con casos positivos (Other/Bass/Drums/Vocals, distintos motores) y negativos (títulos normales); interfaz comprobada con el archivo `Other` auténtico; prueba de pipeline inyectando eventos MIDI sintéticos para validar que Demucs NO se llama y que se genera un MIDI válido; GUI sin supervisión automática y protección de la grabación en curso.

**Límite:** este cambio no actúa retroactivamente sobre el proceso MIDI ya iniciado con el código antiguo. Aplicarlo a ese archivo requiere finalizar o cancelar ese trabajo y volver a abrir la aplicación para cargar el código nuevo. No se ha reiniciado para no perder la ejecución y el estado de edición del usuario.

## 23/10/2026 — Tempo preciso y ajustes avanzados para Audio → MIDI

Se ha ampliado el motor existente Basic Pitch ONNX sin sustituirlo. Los MIDI originales, stems ya separados y trabajos temporales del usuario no se modifican por analizar o variar parámetros.

### Detección de tempo más fiable
Nuevo módulo `tempo_precision.py`: decodifica archivos de audio y vídeo con FFmpeg, revisa hasta tres fragmentos de una canción y combina estimación de beat tracking y ataques de nota. Refina el BPM a partir de múltiples intervalos para superar la resolución gruesa de un solo fotograma de audio. Informa **BPM principal**, alternativas de pulso a **mitad/doble velocidad**, grado de coherencia (NO certeza estadística) y aviso si el ritmo no es estable.

En la pestaña **Audio a MIDI**, controles:
- **Detectar automáticamente**: aplicar análisis multipaso cuando se convierte una canción.
- **Analizar BPM**: ejecutar el análisis independientemente de la transcripción MIDI y presentar las alternativas sin repetir el motor de IA.
- **BPM**: valor decimal, de 35 a 300, con incrementos finos de 0,1.
- **Tap**: pulsar rítmicamente para fijar un tempo manual.
- **Cuantización**: opcional, desactivada por defecto para no alterar la interpretación.
- **Alinear automáticamente la rejilla al primer pulso**: cuando se usa cuantización y tempo automático, compensar el comienzo musical de la señal; se puede ajustar la fase manualmente en milisegundos.

El analizador de BPM puede detectar mal canciones con rubato, síncopas, pasajes sin ataques claros o cambios internos de tempo. En tales casos conviene analizar la pista de batería o introducir el BPM manualmente. El motor del conversor genera por ahora un BPM **constante** por archivo; no reconstruye mapas de tempo variables de las grabaciones originales.

### Controles de precisión del algoritmo
- **Perfil Equilibrado** conserva el algoritmo anterior.
- **Perfil Estricto** eleva umbrales de ataque/sostenido y duración mínima para reducir falsos positivos, pero puede descartar notas suaves.
- **Perfil Sensible** reduce umbrales y duración para recuperar notas tenues, con posible aumento de falsas notas.
- En modo **Manual** quedan accesibles los umbrales exactos de onset, nota sostenida, duración mínima y rango de notas.
- En ambos modos se pueden ajustar: **filtro de notas de velocidad baja (0=desactivado)**, **unión de microcortes de una nota en milisegundos**, **desplazamiento fino de ataques** y **desplazamiento de la rejilla de cuantización**.
- Los parámetros activos y el informe de tempo se guardan en el JSON que acompaña a cada conversión para facilitar comparaciones posteriores.

### Corrección posterior del BPM en el Piano Roll
Dentro de la misma interfaz, la pestaña **Piano Roll** ofrece BPM decimal y dos modos:
1. **Corregir rejilla sin alterar los segundos**: cambia BPM y escala la posición de los eventos en ticks para conservar la duración audible real de la interpretación.
2. **Cambiar la velocidad de reproducción**: conserva las posiciones en ticks y cambia el tempo MIDI, por lo que la música se acelera o se ralentiza.

El botón **Aplicar BPM** permite probar estas variaciones, con Deshacer/Rehacer también para cambios de tempo. **Aplicar edición a la tarea temporal** deja la versión corregida en la tarea temporal; **Guardar todo / Guardar selección** es la única forma de publicar los archivos finales. La fuente original no se sobrescribe.

### Pruebas efectuadas y resultados
- Referencias sintéticas con tempos de **93,7** y **128,6** BPM detectadas como **93,70** y **128,61** (con advertencias sobre medias/dobles).
- Pista real `(Other)_htdemucs_ft` de tontxu: **129,19 BPM**, coherencia interna 91 % calculada por el algoritmo, tres fragmentos que coinciden, alternativas 64,59/258,37. Esta coherencia es un indicador interno, no una garantía de BPM real.
- Mismo patrón rítmico en WAV, MP3, AAC/M4A y WMA: ~93,7 BPM.
- Validación real de Basic Pitch con una melodía de 12 notas: **12 notas correctas en altura y secuencia**, transcripción terminada y exportación MIDI válida con los parámetros avanzados.
- Filtrado de velocidades y combinación de microcortes, presets automático estricto/equilibrado/sensible, tempo automático y alineación de rejilla probados.
- GUI integrada: Analizar BPM, alternativas, edición decimal, opciones avanzadas y Piano Roll; se comprobó análisis real del tema y valor mostrado 129,19 BPM, desfase de rejilla -41 ms.
- Piano roll: cambio de **93,7 a 125,4 BPM** conservando duración audible, y cambio real de velocidad, verificados releyendo la copia MIDI. Controladores, notas y tempo conservados. Deshacer/Rehacer sobre BPM verificados.

Toda la instalación continúa en `/media/javi/Recuperacion/Monitor_de_Grabacion` y utiliza el entorno Python aislado sobre el mismo disco Recuperación.

## Actualización 23/10/2026 — Controles prácticos, presets y Piano Roll interactivo

La versión anterior obligaba a recorrer pantallas para cambiar números, limpiaba la selección del audio original al procesar otra toma y solo mostraba la última versión MIDI en la biblioteca temporal. Se ha revisado la organización, manteniendo **una única ventana** con pestañas.

### Audio → MIDI
- Dentro de la pestaña **Audio a MIDI** se distinguen las subsecciones **Fuente**, **Parámetros** y **Destino**, con alturas compactas. La previsualización del audio original se muestra a la derecha, junto a las versiones MIDI.
- Los controles BPM, umbral de ataque, umbral de sostenido, duración mínima, nota más baja y alta, sensibilidad de batería, notas débiles, unión de microcortes y desplazamientos temporales disponen de **deslizante más valor numérico editable** (módulo `ux_controls.py`). Ambos están sincronizados en tiempo real.
- El audio de origen **NO se descarga ni desaparece** al iniciar o completar otra conversión. Queda en el campo Fuente para hacer tantas pruebas como sea necesario, con parámetros y presets diferentes.
- Al abrir el programa, si existía un MIDI temporal antiguo y la preferencia no recordaba la ruta, el código recupera el origen desde el JSON de metadatos de la conversión; solo si ese fichero todavía existe.
- El estado de edición, fuente, BPM y parámetros se guarda automáticamente después de cambios (con una breve consolidación de eventos) y también al cerrar la ventana principal.
- La interfaz ofrece presets iniciales **Equilibrado, Melodía precisa, Notas suaves, Piano polifónico y Ritmo cuantizado**, y un campo para crear, guardar, recuperar y borrar presets personalizados. Los presets solo incluyen parámetros, no rutas de archivos.
- **Versiones de conversión:** una nueva ejecución escribe en su propia carpeta temporal `procesado/toma_HHMMSS_xxxxxx/`, sin borrar los MIDI de las tomas anteriores. `tareas_temporales/midi/ACTIVA.json` ahora conserva el historial de versiones dentro de esa misma tarea.
- El panel de resultados muestra el selector **Conversión a revisar**; puedes alternar versiones, escuchar pistas, guardar todo o una selección, y abrir cada archivo con su botón **Editar**.
- `Nueva tarea / Descartar` sigue siendo la acción de eliminar los resultados temporales de la tarea, con confirmación; **no elimina las fuentes originales ni las copias ya guardadas**.
- El selector de presets se deshabilita durante un trabajo en curso para evitar discrepancias entre parámetros que se ven y parámetros con los que se procesa.

### Piano Roll
- Selector **MIDI PARA EDITAR** con tomas temporales, pistas MIDI individuales y archivos de la biblioteca guardada. Ya no estás limitado al último MIDI.
- Transporte **▶ Reproducir, ■ Stop**, posición temporal visible, cursor amarillo animado y opción **Seguir cursor** durante reproducción.
- Clic en la regla superior para mover el cursor a otra posición; la posición se conserva incluso cuando el MIDI debe ser sintetizado antes del primer Play.
- Teclado vertical y regla superior se mantienen visibles al desplazar horizontal o verticalmente el contenido.
- **Ctrl + rueda**: zoom horizontal; **Mayús + rueda**: desplazamiento horizontal; **botón central arrastrando**: mover la vista; rueda normal: desplazar verticalmente.
- Zoom con slider y número en píxeles/negra; **Centrar notas** posiciona la vista en las primeras barras, evitando compactar canciones extensas hasta que resulte imposible editar.
- Se mantienen las operaciones de dibujar notas con doble clic, arrastrar para mover, estirar duración, borrar, copiar, pegar, cuantizar, velocidad de nota, Deshacer y Rehacer. También los dos modos de cambio BPM sin alterar el original.
- Presets de visualización **Edición detallada, Edición clásica, Vista general y Edición libre**, más presets propios y restauración de los últimos ajustes de zoom, rejilla y seguimiento.

### Otras pestañas
- **Separar audio**: presets para 4 pistas rápidas, 4 pistas estudio, 6 pistas detalladas, voces rápidas y canales estéreo; presets propios, fuente y últimos ajustes recordados.
- **Monitor / Grabación**: presets para FLAC sin pérdida, WAV y MP3, además de presets propios; mantiene la configuración de la fuente y formato.
- **Mezclador**: presets para mezcla equilibrada, solo voz, sin voz y pistas al 80 %, además de presets propios; cada nivel posee **slider + porcentaje numérico editable + ganancia dB**, con restauración de los últimos ajustes por nombre de instrumento.
- Las bibliotecas Audio guardado y MIDI guardado mantienen las funciones de consulta, escucha y apertura dentro de la interfaz, sin generar presets para un listado que no tiene parámetros de procesado.

### Pruebas de regresión
1. Dos conversiones sucesivas reales de un archivo sintético de 4 segundos usando Basic Pitch con distintos umbrales: **2 MIDI completos y sus pistas** conservados en la misma tarea y visibles con selector de versiones; el archivo WAV fuente mantuvo su ruta intacta. Los ficheros de QA se eliminaron.
2. Guardar un preset MIDI propio con ataque 0,43, sostenido 0,29 y filtro 38, cambiar ajustes, volver a elegir el preset y comprobar restauración exacta; borrar el preset. Probado con almacén aislado de QA.
3. Recuperación al iniciar: la fuente `Other` de «tontxu» reaparece en Audio a MIDI por el JSON de resultados, y el piano roll carga el MIDI con **773 notas** de la tarea real, sin modificarlo.
4. Verificación de teclas y regla ancladas tras desplazar la vista y de controles compactos visuales en Fuente y Parámetros.
5. Reproducción MIDI de «tontxu» en modo de prueba silencioso: cursor se movió de x=69 a x=245,9 tras ~2 s, en sincronía con la reproducción. Se probó detener limpiamente.
6. Sintaxis de los módulos Qt y de los motores separados comprobada.

La última configuración recuperada de la conversión auténtica de `tontxu_piano.mid` se extrajo de su informe JSON, corrigiendo un valor del ataque que había sido modificado por una prueba automatizada. Ninguna pista ni MIDI real se borró o sobrescribió.

## 24/10/2026 — Refinamiento real del reconocimiento de notas MIDI

**Problema identificado:** en modo Automático el motor utilizaba umbrales fijos por instrumento y omitía los deslizantes de ataque, sostenido y duración. Así podían salir conversiones idénticas tras modificar parámetros. Además la opción de unir microcortes podía fusionar dos pulsaciones reales de la misma nota, incluso cuando Basic Pitch había detectado un nuevo ataque.

**Motor `midi_engine.py` y nuevo `midi_refine.py`:**
- Los deslizantes afectan también al modo Automático: se suman como corrección relativa sobre el perfil instrumental; en modo Manual son valores absolutos.
- Refinado apoyado en las matrices **onset** y **note** del modelo neuronal Basic Pitch. Reconoce ataques nuevos dentro de una nota larga y divide la nota solo si son suficientemente claros, o si existe caída previa en la activación del mismo tono. Evita generar pequeñas notas falsas por vibrato u oscilaciones débiles.
- «Unir microcortes» reconoce los nuevos ataques de una nota repetida y **no une** dos pulsaciones cuando el modelo confirma un nuevo ataque; conserva la función de unir cortes artificiales sin retrigger.
- Selector **Refinar ataques y notas repetidas**: Equilibrado (conservador), Rigor alto (filtra señales débiles y puede perder notas suaves) o Desactivado (sin análisis adicional, para comparación).
- Se muestran los **umbrales efectivos** de ataque, sostenido, mínimo en ms y rango MIDI en el registro. Se guardan en el informe JSON individual por pista, junto con número de ataques divididos, eventos originales y eventos descartados.
- Los presets de conversión ahora incluyen explícitamente valores de todos los controles implicados para que elegir el mismo preset reproduzca su configuración. Cada toma sigue siendo independiente y se conserva en almacenamiento temporal.
- El refinador se aplica a Basic Pitch; Transkun sigue siendo el motor especializado de piano cuando la pista es de piano. El éxito de Transkun no depende de estadísticas de Basic Pitch.
- Todos los cambios respetan origen y MIDI existentes. No se ejecutó una nueva transcripción completa de la canción.

**Validaciones:**
- Caso sintético controlado: 1 nota con 3 ataques bien definidos antes se fusionaba en 1; ahora se obtiene **3 notas MIDI**. Un sostenido con una oscilación débil permanece como **1 nota**.
- En un fragmento real de 14 segundos de la pista «Other» de tontxu: el posprocesado antiguo con la preferencia de unión de 223 ms daba 49 notas; el refinado conservador dio **75**, al proteger ataques originales ya detectados; no dividió notas largas sin evidencia suficiente en ese fragmento. Esto NO significa que las 75 notas sean todas correctas, porque no existe MIDI de referencia de la interpretación.
- Dos conversiones reales de un mismo fragmento de 8 segundos con ataque 0,35 frente a 0,65: el motor recibió los dos valores y produjo eventos neuronales diferentes. Ambas exportaciones MIDI válidas.
- Melodía de control de 6 alturas [57,60,60,64,67,69]: transcripción final reproducida exactamente en ese orden; informe guardó ataque efectivo 0,38 y estadísticas de refinado. Se probaron el modo Automático, los presets y la sección Parámetros visible sin controles recortados.
- Verificadas las **seis** tomas MIDI de usuario y las **cuatro** pistas de separación. No se sobrescribió ni eliminó ninguna.


## StemMIDI Studio — implementación de la interfaz aprobada (24/10/2026)

La pantalla INICIO en PySide6 respeta la estructura de la referencia visual aprobada,
con la cabecera y logo SVG azul/cian, frase:
«Libre para usar, estudiar y mejorar. Hecho para compartir, no para lucrarse con el código.»

Archivos: studio_home.py, studio_shell.py y assets/*.svg.
Pestañas: Inicio, Monitor/Grabación, Separación de audio, Audio a MIDI,
Mezclador, Piano Roll y Resultados.

Incluye controles conectados a motores reales: Grabar / Pausa / Detener;
entrada y niveles de monitorización; separación con modelos disponibles,
visibilidad de stems y selección para exportar; presets y controles numéricos
de Basic Pitch/Transkun; formas de onda reales decodificadas a 320 Hz con
FFmpeg; resultados temporales con audición y exportación; seis faders de
mezclador con ganancia, Solo y Mute; niveles derivados de la reproducción
de las propias pistas; mini piano roll generado a partir del MIDI real
con apertura del editor completo; información de duración y BPM. El
análisis de tonalidad es solamente orientativo.

Los botones Abrir/Guardar proyecto utilizan archivos .stemstudio.json
con rutas y ajustes, nunca sobreescriben los originales ni incluyen música.

Limitaciones deliberadas: la referencia estática mostraba instrumentos,
duraciones y señales ficticias; la aplicación representa solamente los datos
de la instalación. Demucs separa conjuntamente los stems de cada modelo,
y las casillas marcan cuáles se guardarán sin borrar los demás temporales.

QA: renderizado 1536x1024 y 1920x1080; 4 stems reales y 6 versiones MIDI
temporales de tontxu preservadas, carga de 710 notas reales y formas de onda.
Comprobados modelo, ajustes MIDI, Solo/Mute, ganancia por pista, casillas de
exportación, Piano Roll, Abrir/Guardar proyecto y Pause/Continue de captura.
Se cancelan los QProcess de onda sin destruir objetos en uso.

Compilación Debian PyInstaller con recursos SVG y entorno IA completo regenerada.
Windows PyInstaller x64 recompilado con recursos actualizados, pendiente
prueba de hardware real y motores IA nativos. Mac dispone de código y script
actualizados para compilar .app y .dmg en Mac real.
