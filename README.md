# StemMIDI Studio

Estudio modular de grabación, separación instrumental, transcripción
de audio a MIDI, mezcla y edición en Piano Roll.

## Funciones

La interfaz integra un monitor/grabador, separación mediante modelos de IA,
conversión audio→MIDI, previsualización, selección de resultados, transporte
individual por pista, mezclador y Piano Roll. Los resultados se conservan
como temporales hasta que el usuario los guarde o los descarte expresamente.

## Ejecución en Debian 13

Usa el acceso directo «Monitor de Grabación compilado» creado en el escritorio
o ejecuta `main.py` con sus dependencias Python instaladas. Es necesario
FFmpeg/FFplay para la previsualización y PipeWire/PulseAudio para la captura.
Las funciones de separación y transcripción precisan sus propios modelos y
dependencias opcionales; no se incluyen en este repositorio.

## Windows y macOS

El código es multiplataforma y existen instrucciones de compilación, pero
el funcionamiento completo de la captura y de los motores de IA requiere
pruebas nativas en cada sistema. No se afirma compatibilidad verificada
con Windows o macOS hasta superar esas pruebas.

## Guardar y descartar

Desde Inicio, selecciona varias filas de Resultados con Ctrl/Mayús y abre
«Guardar» para exportar la selección o todos los resultados. Cada copia
obtiene un nombre alternativo si el destino ya contiene un fichero igual.
«Descartar» permite eliminar tareas temporales (separación o MIDI) después
de confirmarlo. No elimina los originales importados ni resultados guardados.

## Licencia

El código original del proyecto está disponible con condiciones no
comerciales: [PolyForm Noncommercial 1.0.0](LICENSE). Puedes usarlo,
estudiarlo, modificarlo y compartirlo con fines no comerciales. Esto es
**código fuente disponible con restricciones no comerciales**, no una
licencia de «open source» conforme a la definición de OSI.

El proyecto emplea componentes de terceros que se distribuyen o instalan
según sus propias licencias. No publiques ni redistribuyas modelos de IA
ni archivos de terceros sin verificar sus condiciones.

## Privacidad

No subir grabaciones, ficheros de configuración, bancos de modelos ni
carpetas temporales a un repositorio público. El archivo `.gitignore`
excluye estos contenidos por defecto.

## Módulo «Desglose de batería» — 24 de octubre de 2026

StemMIDI Studio incorpora la pestaña **Desglose de batería**. Acepta la pista
`drums` ya separada en el proyecto o un archivo externo de batería y usa el
modelo real `MDX23C-DrumSep-aufr33-jarredou.ckpt` de audio-separator para
producir seis familias: **bombo, caja, toms, charles, ride y crash**.

El modelo NO se incluye en el código ni está descargado todavía. Desde el
módulo, pulsa **Instalar modelo** para descargarlo explícitamente antes de
procesar una pista. Es un peso de terceros y no debe incluirse en GitHub.
Si no hay modelo o la separación falla, no se generan pistas ficticias.

Los resultados se almacenan en la tarea **bateria** del proyecto activo,
se escuchan individualmente y se guardan de forma selectiva en FLAC sin
sobrescribir archivos existentes. También aparecen en Resultados. Al cambiar
de proyecto, los archivos permanecen asociados exclusivamente al proyecto
al que pertenecen.

Pruebas realizadas: interfaz PySide6, reconocimiento de seis nombres,
validación de resultados, guardado sin sobrescrituras, aislamiento y
recuperación entre proyectos. NO se ha validado aún un procesamiento IA
completo con los pesos descargados ni la calidad de separación con audio real.

## 24 de octubre de 2026 — Paneles inferiores y afinación vocal

El panel **Inicio** incluye ahora cuatro áreas en la fila inferior, de
izquierda a derecha: **Piano Roll · MIDI**, **Afinación vocal**, **Batería:
pistas separadas** e **Información**. El Piano Roll emplea dos filas de
controles para adaptarse al espacio disponible. A 1536 × 1024 la portada
completa es visible sin desplazamiento vertical.

**Batería: pistas separadas** muestra hasta seis formas de onda reales
(bombo, caja, toms, charles, ride y crash) con reproducción y parada por
pista. Cuando aún no hay separación válida, aparecen vacías y sus controles
están deshabilitados. La tarjeta «Desglose de batería» continúa visible en
Inicio y la pestaña principal también permanece.

El nuevo módulo **Afinación vocal** se abre desde Inicio o desde su pestaña:
elige una voz solista aislada, la tónica, la escala y la cantidad de
corrección. Se ejecuta en un proceso separado usando
`entorno_ia/bin/python`, `librosa`/pYIN y corrección tonal sobre las
regiones con notas detectadas. El motor no sustituye el cantante ni
perfecciona dicción, interpretación, tiempo o timbre. Algunas grabaciones
pueden presentar artefactos y requieren valoración auditiva.

Los resultados se guardan en FLAC de 24 bits, preservando la frecuencia
y la cantidad de canales de la fuente, sin sobrescribir originales.
La afinación tiene almacenamiento temporal y resultados aislados por
proyecto. Se pueden escuchar, guardar o descartar sus archivos.

**Pruebas ejecutadas:** un tono de ~452 Hz se corrigió a ~440 Hz;
archivo estéreo de 48 kHz y FLAC 24 bits verificado; prueba integral de
interfaz con proceso de afinación real, listado de resultados y cambio
entre proyectos completada; compilación de Debian verificada.

Las pistas de batería reales siguen requiriendo instalar el modelo
DrumSep, y la calidad de afinación con una grabación vocal humana aún
necesita escucharse y evaluarse. El procesamiento de voz utiliza el
entorno IA local, que debe mantenerse disponible en el disco del proyecto.

## Actualización: estudio vocal y campos de rutas — 24/10/2026

**Estudio vocal** dispone ahora de cuatro pestañas: Afinación y análisis,
Carácter vocal, EQ · Dinámica · FX y Voz de referencia. El modo Carácter
ofrece Natural, Dulce, Rasgada, Cálida y Aireada con intensidad regulable.
Los nuevos presets Voz rasgada · Rock, Voz dulce · Balada, Voz cálida · Soul,
Voz aireada · Pop y Voz limpia · Estudio configuran parámetros reales de DSP
además de la afinación anterior.

El motor externo vocal_fx.py aplica saturación paralela focalizada para
añadir armónicos en modo Rasgada; filtrado para suavizar la aspereza en
modo Dulce; calidez, presencia, aire, de-esser, puerta suave, ambiente
y mezcla seca/húmeda. La corrección de entonación sigue siendo opcional:
«Solo efectos · sin corregir notas» permite tratar voz hablada o canciones
sin notas detectables. No transforma la identidad del cantante y no puede
recuperar por completo la voz limpia de una toma ya distorsionada.

Se ha añadido conmutación A/B entre audio original y resultado, con
reproductor plegable. Los controles avanzados mantienen espacio suficiente
sin solapamiento y los resultados disponen de más altura. Campos de rutas
de archivos limitados a 500 px en todas las pantallas, con ruta completa
en información emergente y acceso a su contenido.

Las preferencias del estudio vocal, preset, tipo de carácter, intensidad,
parámetros EQ/FX, mezcla y bypass de afinación se incluyen en el archivo
de proyecto.

Pruebas efectuadas en Debian 13: onda de prueba rasgada con armónicos
añadidos, atenuación de 6.2 kHz en modo dulce, salida FLAC24 estéreo a
48 kHz, ejecución real de QProcess y separación por proyecto, rutas de
archivo limitadas, reproductor A/B y auditoría visual de las cuatro
pestañas. No se ha realizado una valoración auditiva con una interpretación
humana real; los presets son puntos de partida, no un resultado garantizado.
