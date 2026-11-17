"""Centro de ayuda contextual de StemMIDI Studio (sin conexión externa).

No abre un cuadro genérico: permite buscar procedimientos, recorrer módulos
y saltar al módulo real desde las explicaciones. No cambia archivos ni audio.
"""
from __future__ import annotations
from html import escape
from collections import OrderedDict

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QTextBrowser, QPushButton, QSplitter, QWidget
)

TOPICS=OrderedDict([
    ("inicio",{
        "title":"Inicio · guía general",
        "module":"Inicio",
        "intro":"La pantalla Inicio reúne los controles principales y resume el proyecto activo. Los indicadores están vacíos hasta que haya audio o MIDI real.",
        "steps":[
            "Elige una fuente en Monitor / Grabación antes de pulsar Grabar.",
            "Para separar una pista, selecciona sus instrumentos y abre Separación de audio.",
            "Para transcribir audio, abre Audio a MIDI. El piano muestra notas solo cuando existe un MIDI.",
            "En Resultados puedes escuchar y guardar archivos del proyecto abierto.",
            "Pulsa el símbolo ? de cualquier tarjeta para acceder directamente a su explicación.",
        ],
        "tips":"Un proyecto almacena parámetros y rutas; las grabaciones originales no se incorporan al archivo .stemstudio.json.",
    }),
    ("monitor",{
        "title":"Monitor y grabación",
        "module":"Monitor / Grabación",
        "intro":"Supervisa la señal y captura audio mediante PipeWire/PulseAudio. Los medidores indican los niveles de entrada.",
        "steps":[
            "Selecciona la fuente real de audio y pulsa Iniciar supervisión.",
            "Comprueba la señal en los medidores L/R antes de iniciar la grabación.",
            "El control de ganancia modifica la señal capturada; el dial Balance L/R controla la distribución estéreo.",
            "Elige formato, frecuencia y carpeta, y pulsa Grabar. Usa Pausa/Detener para finalizar.",
            "Escucha la última toma con el reproductor de esa pantalla antes de guardarla.",
        ],
        "tips":"Evita picos cerca de 0 dBFS para no saturar; subir de 48 a 96 kHz no añade información que no esté en la fuente.",
    }),
    ("separacion",{
        "title":"Separación de audio",
        "module":"Separación de audio",
        "intro":"Extrae pistas de voces, batería, bajo y otros instrumentos cuando existe un modelo compatible.",
        "steps":[
            "Importa audio real mediante el explorador y usa la escucha previa para confirmar la fuente.",
            "Selecciona los instrumentos disponibles y el motor de separación.",
            "Elige el formato sin pérdida si necesitas edición y mezcla posteriores.",
            "Pulsa Separar; escucha las pistas resultantes antes de guardarlas.",
            "Los resultados de una sesión solo aparecen en ese proyecto.",
        ],
        "tips":"Guitarra, piano y viento requieren un modelo que los separe expresamente. No se crean pistas simuladas.",
    }),
    ("bateria",{
        "title":"Desglose de batería",
        "module":"Desglose de batería",
        "intro":"Descompone una pista de batería en bombo, caja, toms, charles, ride y crash mediante un modelo de separación instalado.",
        "steps":[
            "Pulsa «Cargar batería…» para seleccionar un SOLO archivo con batería aislada: bombo, caja, toms y platos mezclados.",
            "WAV y FLAC son preferibles; también puedes cargar MP3, M4A, OGG, Opus, AIFF y otros códecs reconocidos por FFmpeg.",
            "Si el audio es una canción completa, pulsa «Extraer batería de canción…» y separa primero la batería del resto.",
            "Con «▶ Escuchar entrada» comprueba que has seleccionado la pista correcta.",
            "Si el modelo no está instalado, abre «Fuente y motor» y pulsa «Instalar modelo». No necesitas samples, SF2 ni archivos MIDI.",
            "Para descargar otros modelos, abre Preferencias → Modelos de IA, o pulsa «Más modelos de IA…» en Fuente y motor.",
            "El gestor reconoce modelos instalados, permite buscar por instrumento y arquitectura, e identifica qué motores pueden utilizarse en cada módulo.",
            "Pulsa Desglosar batería y espera resultados reales del motor.",
            "Todo está reunido en un panel único, sin subpestañas: ondas y mezclador arriba, editor y secuenciador debajo, resultados al final.",
            "Las seis ondas muestran audio real. El mezclador dispone de faders, panorama, Mute/Solo, presets y exportación FLAC 24 bits.",
            "En el editor recorta, ajusta fundidos, compresión y filtros sin alterar el original.",
            "En el secuenciador crea patrones MIDI de 16 pasos, swing, BPM y 1 a 8 compases con presets editables.",
            "Desplázate verticalmente por el panel para ver los cinco bloques; no necesitas cambiar de pestaña.",
            "Escucha resultados reales antes de guardarlos o descartar la tarea.",
        ],
        "tips":"La calidad depende del modelo y del material de entrada; algunos elementos pueden filtrarse entre pistas.",
    }),
    ("midi",{
        "title":"Audio a MIDI",
        "module":"Audio a MIDI",
        "intro":"Transcribe eventos musicales desde un archivo de audio. Los parámetros cambian el análisis, no el sonido original.",
        "steps":[
            "Importa un audio y escúchalo primero.",
            "Selecciona el modelo de transcripción adecuado al instrumento.",
            "Ajusta sensibilidad de ataque, duración mínima y desplazamiento temporal si las notas no encajan.",
            "Convierte y reproduce el MIDI resultante; abre Piano Roll para editar los errores.",
            "Guardar selección permite conservar una versión concreta.",
        ],
        "tips":"Los controles de cuantización pueden desplazar notas: compara el MIDI contra el audio de origen.",
    }),
    ("vocal",{
        "title":"Estudio vocal · afinación, carácter y efectos",
        "module":"Afinación vocal",
        "intro":"Corrige la afinación de una voz solista y permite procesar su carácter, dinámica y espacio. Guarda un FLAC nuevo sin sustituir el original.",
        "steps":[
            "Selecciona «Voz aislada del proyecto» o importa un archivo de cantante.",
            "En Afinación y análisis elige tonalidad y escala, analiza la voz y aplica un preset si resulta útil.",
            "En Carácter vocal ajusta Dulce, Rasgada, Cálida o Aireada. Son efectos DSP, no clonación de voz.",
            "En EQ · Dinámica · FX ajusta calidez, presencia, aire, de-esser, puerta, ambiente y mezcla.",
            "En Doblado · Delay · Máster regula ADT, eco, anchura estéreo y ganancia final.",
            "Los ajustes de todas estas secciones tienen deslizantes unidos a números editables.",
            "En las pestañas de EQ y Doblado hay presets de fábrica y puedes guardar los tuyos.",
            "Activa «Solo efectos» si no quieres corregir notas. Pulsa Procesar voz.",
            "Compara A (original) frente a B (procesado) y guarda la versión que prefieras.",
        ],
        "tips":"La conversión rasgada→dulce puede suavizar el sonido, pero no reconstruye información que se perdió en una grabación distorsionada.",
    }),
    ("mezclador",{
        "title":"Mezclador multipista",
        "module":"Mezclador",
        "intro":"Ajusta pistas separadas con fader, Mute, Solo y exporta la mezcla. Sin pistas cargadas, solo está disponible la preescucha.",
        "steps":[
            "Carga o separa audio antes de abrir el mezclador multipista.",
            "En el panel único de Desglose de batería, el mezclador de seis canales aparece junto a las ondas reales.",
            "Selecciona un canal por su nombre: su EQ e inspector se muestran horizontalmente debajo del mezclador, sin cambiar de pestaña.",
            "Usa Mute/Solo al generar la mezcla y ▶ para escuchar esa pista individualmente.",
            "En el inspector ajusta EQ de graves, medios y agudos: se aplica realmente al exportar.",
            "Los medidores de nivel muestran picos calculados del archivo mientras se preescucha, no una entrada de hardware en vivo.",
            "Si necesitas más altura, la configuración Fuente y motor permanece plegada con un botón para volver a abrirla.",
            "Aplica un preset, escucha, y exporta la mezcla FLAC de 24 bits.",
        ],
        "tips":"La pestaña Mezclador vacía no fabrica pistas: escucha archivos antes de añadirlos desde su botón de preescucha.",
    }),
    ("piano",{
        "title":"Piano Roll · editor MIDI",
        "module":"Piano Roll",
        "intro":"Editor de notas MIDI con piano vertical, rejilla temporal, controles de velocidad y reproducción.",
        "steps":[
            "Selecciona un archivo MIDI o abre una transcripción desde Resultados.",
            "Doble clic sobre la rejilla: insertar nota. Arrastrar: mover nota.",
            "Arrastra el borde derecho para cambiar su duración.",
            "Ctrl+rueda modifica el zoom; desplázate por el teclado con la barra vertical.",
            "Usa Deshacer/Rehacer y Cuantizar para corregir notas.",
            "Pulsa Aplicar edición a la tarea temporal para conservar la versión MIDI del proyecto.",
        ],
        "tips":"La rejilla visible con el proyecto vacío es solo una referencia de edición: no son notas inventadas.",
    }),
    ("resultados",{
        "title":"Resultados y preescucha",
        "module":"Resultados",
        "intro":"Solo muestra archivos de la sesión abierta. Puedes escucharlos, comparar y guardar versiones.",
        "steps":[
            "Selecciona un resultado de la tabla.",
            "Pulsa Reproducir para escucharlo; Detener interrumpe la reproducción.",
            "Pulsa Opciones en el reproductor para seleccionar salida, velocidad y volumen.",
            "Guarda una o varias pistas con Guardar selección. Descartar afecta solo a temporales, después de confirmar.",
            "Haz doble clic en un MIDI para abrir el Piano Roll.",
        ],
        "tips":"Los originales permanecen intactos. Guarda las salidas que quieras conservar antes de descartar una tarea temporal.",
    }),
    ("onda",{
        "title":"Vista de audio y forma de onda",
        "module":"Inicio",
        "intro":"La forma de onda muestra niveles decodificados del archivo real, no una gráfica ficticia.",
        "steps":[
            "Selecciona un archivo en Resultados o en la biblioteca del proyecto.",
            "Usa +/− para cambiar la escala de la vista.",
            "Haz clic en la onda para situar el cursor cuando el control admite búsqueda.",
            "Utiliza la preescucha para verificar que estás editando el archivo correcto.",
        ],
        "tips":"Si no existe audio seleccionado, el área se mantiene vacía.",
    }),
    ("pistas",{
        "title":"Pistas separadas y estado",
        "module":"Inicio",
        "intro":"Esta tarjeta muestra los stems existentes de la sesión. S indica Solo y V volumen/reproducción según la zona.",
        "steps":[
            "Ejecuta Separación de audio para generar pistas reales.",
            "Selecciona una pista existente para escucharla sin cambiar las demás.",
            "Abre Mezclador para regular los niveles de cada instrumento.",
        ],
        "tips":"Si no aparece una pista es porque el modelo no la produjo o el proyecto actual no dispone de ese archivo.",
    }),
    ("info",{
        "title":"Información del MIDI",
        "module":"Inicio",
        "intro":"Presenta información de la pieza MIDI elegida, como número de notas, duración, tempo y tonalidad estimada.",
        "steps":[
            "Selecciona un MIDI desde Inicio o Resultados.",
            "Comprueba tempo y duración antes de editar.",
            "Pulsa Editar MIDI para abrir el piano y ajustar sus notas.",
        ],
        "tips":"La tonalidad deducida del MIDI es orientativa; no equivale a una detección musical infalible.",
    }),
])

class HelpCenter(QDialog):
    def __init__(self,main):
        super().__init__(main)
        self.main=main
        self.setObjectName("stemmidiHelpCenter")
        self.setWindowTitle("Centro de ayuda · StemMIDI Studio")
        self.resize(1000,670)
        self.setMinimumSize(760,490)
        layout=QVBoxLayout(self)
        layout.setContentsMargins(15,13,15,13)
        layout.setSpacing(10)
        heading=QLabel("CENTRO DE AYUDA · STEMMIDI STUDIO")
        heading.setObjectName("title")
        layout.addWidget(heading)
        subtitle=QLabel("Selecciona un tema, busca un control o abre directamente la pantalla que necesitas.")
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)
        self.search=QLineEdit(self)
        self.search.setPlaceholderText("Buscar por ejemplo: grabación, notas, mezcla, tonalidad, audio, rasgada…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)
        split=QSplitter(Qt.Horizontal,self)
        self.topic_list=QListWidget(self)
        self.topic_list.setMinimumWidth(315)
        self.topic_list.setMaximumWidth(365)
        self.topic_list.setAlternatingRowColors(True)
        self.topic_list.setWordWrap(True)
        self.topic_list.setStyleSheet("""
        QListWidget {background:#041a42;color:#e0f8ff;
            alternate-background-color:#052050;
            border:1px solid #2bb1fc;border-radius:6px;
            font-size:13px;outline:none;}
        QListWidget::item {color:#e0f8ff;min-height:29px;
            border-bottom:1px solid #2494d4;padding:5px 8px;}
        QListWidget::item:selected {background:#0d59e0;color:#e0f8ff;}
        QListWidget::item:hover {background:#0a42a5;color:#e0f8ff;}
        """)
        self.topic_list.currentItemChanged.connect(self._on_item)
        split.addWidget(self.topic_list)
        self.description=QTextBrowser(self)
        self.description.setReadOnly(True)
        self.description.setOpenExternalLinks(False)
        self.description.setStyleSheet(
            "QTextBrowser {font-size:13px;background:#04183b;color:#e0f8ff;"
            "border:1px solid #2bb1fc;border-radius:6px;padding:12px;}")
        split.addWidget(self.description)
        split.setStretchFactor(0,0)
        split.setStretchFactor(1,1)
        layout.addWidget(split,1)
        controls=QHBoxLayout()
        self.context=QLabel("Ayuda integrada, disponible sin Internet.")
        self.context.setObjectName("muted")
        controls.addWidget(self.context,1)
        self.open_btn=QPushButton("Ir a esta pantalla")
        self.open_btn.setObjectName("primary")
        self.open_btn.clicked.connect(self.open_module)
        controls.addWidget(self.open_btn)
        self.close_btn=QPushButton("Cerrar ayuda")
        self.close_btn.clicked.connect(self.close)
        controls.addWidget(self.close_btn)
        layout.addLayout(controls)
        QShortcut(QKeySequence("Ctrl+F"),self,activated=self.search.setFocus)
        self._filter("")
        self.select_topic("inicio")

    def _filter(self,search):
        chosen=self.topic_list.currentItem()
        selected=chosen.data(Qt.UserRole) if chosen else None
        query=search.casefold().strip()
        self.topic_list.blockSignals(True)
        self.topic_list.clear()
        for code,topic in TOPICS.items():
            haystack=" ".join((topic["title"],topic["intro"],
                                " ".join(topic["steps"]),topic["tips"])).casefold()
            if query and query not in haystack:
                continue
            item=QListWidgetItem(topic["title"])
            item.setData(Qt.UserRole,code)
            self.topic_list.addItem(item)
        self.topic_list.blockSignals(False)
        for row in range(self.topic_list.count()):
            if self.topic_list.item(row).data(Qt.UserRole)==selected:
                self.topic_list.setCurrentRow(row)
                return
        if self.topic_list.count():
            self.topic_list.setCurrentRow(0)
        else:
            self.description.setHtml("<h3>Sin coincidencias</h3><p>Prueba con otra palabra.</p>")
            self.open_btn.setEnabled(False)

    def select_topic(self,code):
        if code not in TOPICS:
            code="inicio"
        # El acceso directo contextual debe funcionar aunque haya un filtro previo.
        if self.search.text():
            self.search.clear()
        for i in range(self.topic_list.count()):
            if self.topic_list.item(i).data(Qt.UserRole)==code:
                self.topic_list.setCurrentRow(i)
                return

    def _on_item(self,item,previous):
        if item is None:return
        code=item.data(Qt.UserRole)
        topic=TOPICS[code]
        steps="".join("<li style='margin-bottom:9px'>"+escape(s)+"</li>" for s in topic["steps"])
        html=(
            "<div style='color:#e0f8ff'>"
            "<h2 style='color:#85f0ff'>"+escape(topic["title"])+"</h2>"
            "<p>"+escape(topic["intro"])+"</p>"
            "<h3 style='color:#85f0ff'>Cómo utilizarlo</h3>"
            "<ol>"+steps+"</ol>"
            "<p style='color:#e0f8ff'><b>Nota:</b> "+escape(topic["tips"])+"</p>"
            "</div>")
        self.description.setHtml(html)
        self.open_btn.setEnabled(True)
        self.context.setText("Módulo: "+topic["module"]+" · F1 para abrir ayuda contextual")

    def open_module(self):
        item=self.topic_list.currentItem()
        if item is None:return
        name=TOPICS[item.data(Qt.UserRole)]["module"]
        for i in range(self.main.tabs.count()):
            label=self.main.tabs.tabText(i).casefold()
            if name.casefold() in label:
                self.main.tabs.setCurrentIndex(i)
                self.hide()
                return
        self.context.setText("Esa pantalla todavía no está disponible en esta sesión.")

def current_topic(main):
    try:
        tab=main.tabs.tabText(main.tabs.currentIndex()).casefold()
    except (AttributeError,RuntimeError):
        return "inicio"
    for needle,code in (
        ("monitor","monitor"),("separación","separacion"),
        ("batería","bateria"),("midi","midi"),("vocal","vocal"),
        ("mezclador","mezclador"),("piano roll","piano"),
        ("resultados","resultados")):
        if needle in tab:return code
    return "inicio"

def open_help(main,topic=None):
    dlg=getattr(main,"_help_center",None)
    if dlg is None:
        dlg=HelpCenter(main)
        main._help_center=dlg
    dlg.select_topic(topic or current_topic(main))
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    return dlg

def install_shortcuts(main):
    action=QShortcut(QKeySequence("F1"),main)
    action.setContext(Qt.ApplicationShortcut)
    action.activated.connect(lambda:open_help(main))
    main._help_shortcut=action
