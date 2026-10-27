"""Ayuda contextual sobre todos los ajustes, sin alterar acciones ni modelos.

Se muestra tras posar el ratón. Desaparece inmediatamente al moverlo,
hacer clic, girar la rueda o abandonar la ventana. Admite widgets nuevos.
"""
from __future__ import annotations
from html import escape
import json
import os
import tempfile
from pathlib import Path
from professional_help_content import describe as professional_details
import re
import textwrap
from PySide6.QtCore import QObject, QEvent, Qt, QTimer, QPoint
from PySide6.QtWidgets import (
    QApplication, QWidget, QAbstractButton, QPushButton, QToolButton,
    QCheckBox, QRadioButton, QComboBox, QAbstractSlider,
    QAbstractSpinBox, QLineEdit, QTabBar, QToolTip, QLabel, QGridLayout,
    QFormLayout, QScrollBar, QTabWidget, QGroupBox, QProgressBar,
    QAbstractItemView, QPlainTextEdit, QTextEdit, QGraphicsView, QScrollArea
)

# Textos funcionales verificables a partir de los controles reales del programa.
FIELD_DESC={
 "sources":"Selecciona la fuente de audio real que se va a supervisar o grabar.",
 "playback_device":"Selecciona el dispositivo de salida utilizado para la escucha.",
 "capture_rate":"Selecciona la frecuencia de muestreo de la grabación.",
 "input_gain_db":"Ajusta la ganancia de la captura en decibelios.",
 "input_gain":"Ajusta la ganancia aplicada a la señal de entrada grabada.",
 "input_balance":"Desplaza el balance de la grabación entre izquierda y derecha.",
 "monitor_button":"Activa o detiene la supervisión de la fuente seleccionada.",
 "record_button":"Inicia la grabación de la fuente actual en el proyecto activo.",
 "record_name":"Establece el nombre de la grabación nueva.",
 "source_choice":"Elige una fuente del proyecto para escucharla o procesarla.",
 "profile":"Escoge el modelo de IA o el perfil de separación.",
 "quality":"Selecciona la calidad del procesamiento; la calidad alta puede tardar más.",
 "export_fmt":"Selecciona el formato de audio del resultado.",
 "dest_edit":"Carpeta donde se guardarán los resultados cuando apruebes la tarea.",
 "file_edit":"Archivo de audio de entrada. No se modifica el original.",
 "audio_path":"Archivo de origen que se analizará para generar notas MIDI.",
 "outdir":"Carpeta donde publicar los archivos MIDI aprobados.",
 "filename":"Nombre que recibirá el MIDI exportado.",
 "bpm":"Ajusta el tempo en pulsaciones por minuto (BPM).",
 "tempo_bpm":"Establece el tempo de reproducción o la nueva rejilla MIDI.",
 "tempo_mode":"Determina si el cambio de BPM afecta a la velocidad o solo a la rejilla temporal.",
 "tempo_auto":"Detecta automáticamente el tempo a partir del audio.",
 "onset":"Controla la sensibilidad para detectar el inicio de las notas.",
 "frame":"Ajusta el umbral de detección de notas entre fotogramas.",
 "min_duration":"Ignora eventos detectados más cortos que esta duración.",
 "low":"Límite inferior de altura de las notas detectadas.",
 "high":"Límite superior de altura de las notas detectadas.",
 "drum":"Ajusta la sensibilidad de detección de golpes de batería.",
 "min_velocity":"Velocidad MIDI mínima admitida para las notas detectadas.",
 "merge_gap":"Une eventos consecutivos próximos dentro del intervalo elegido.",
 "note_shift":"Desplaza temporalmente las notas MIDI detectadas.",
 "grid_offset":"Corrige el desplazamiento de la rejilla temporal MIDI.",
 "quant":"Elige la subdivisión de tiempo para ajustar los inicios de nota.",
 "grid":"Determina la resolución de cuantización del editor de notas.",
 "note_pitch":"Establece la altura MIDI de las notas seleccionadas.",
 "note_start":"Establece la posición inicial de las notas seleccionadas.",
 "note_duration":"Establece cuánto duran las notas seleccionadas.",
 "velocity":"Modifica la intensidad de las notas MIDI seleccionadas.",
 "zoom":"Acerca o aleja el contenido temporal del Piano Roll.",
 "zoom_digit":"Introduce con precisión la escala horizontal del Piano Roll.",
 "zoom_vertical":"Aumenta o reduce la altura de cada semitono del Piano Roll.",
 "zoom_vertical_digit":"Introduce la altura vertical de las notas en píxeles.",
 "timeline":"Mueve el cursor de reproducción por la línea de tiempo.",
 "position_label":"Muestra la posición del cursor y la duración.",
 "tonic":"Selecciona la nota fundamental para la afinación vocal.",
 "scale":"Selecciona la escala musical de referencia para afinar.",
 "strength":"Determina cuánto se corrige la altura de las notas vocales.",
 "preset":"Selecciona un ajuste de fábrica de la sección.",
 "retune":"Ajusta la rapidez con que la voz se corrige hacia la nota objetivo.",
 "humanize":"Conserva las variaciones naturales de la interpretación vocal.",
 "threshold":"Umbral en cents por debajo del que no se corrige la desviación tonal.",
 "compression":"Reduce las diferencias dinámicas entre pasajes fuertes y suaves.",
 "highpass":"Atenúa las frecuencias graves inferiores al corte elegido.",
 "character":"Escoge el tipo de tratamiento de carácter vocal.",
 "character_amount":"Regula la intensidad del carácter vocal seleccionado.",
 "warmth":"Modifica el balance tonal hacia una voz más cálida.",
 "presence":"Realza la presencia vocal en la zona media del espectro.",
 "air":"Ajusta el brillo y las frecuencias altas de la voz.",
 "deesser":"Reduce las sibilancias fuertes en la grabación vocal.",
 "gate":"Atenúa suavemente el ruido de fondo en pausas entre frases.",
 "reverb":"Ajusta la cantidad de ambiente o reverberación.",
 "wet":"Mezcla la voz original con la señal de efectos.",
 "doubler":"Añade un efecto de doblado artificial mediante retardos breves.",
 "delay":"Controla la cantidad de eco añadido a la voz.",
 "delay_ms":"Establece el intervalo en milisegundos entre ecos.",
 "stereo_width":"Regula la amplitud de la imagen estéreo.",
 "output_gain_db":"Ajusta el nivel final de salida en decibelios.",
 "reference":"Archivo de voz autorizado para analizar un estilo de interpretación.",
 "ref_consent":"Confirma que tienes autorización para analizar esa referencia vocal.",
 "source_preview":"Escucha el audio de origen sin cambiar el archivo.",
 "output_preview":"Escucha el archivo procesado antes de guardarlo.",
 "choices":"Elige un preset guardado o uno de fábrica y aplica sus parámetros.",
 "name":"Escribe el nombre con el que se guardará el preset propio.",
 "offset":"Establece en qué segundo empieza la preescucha de mezcla.",
 "output_fmt":"Selecciona el formato del audio que exportará el mezclador.",
 "midi_choice":"Selecciona el archivo MIDI que se abrirá en Piano Roll.",
 "note_velocity":"Edita el valor de velocidad de las notas MIDI.",
 "tempo_apply":"Aplica el cambio de tempo según el modo seleccionado.",
 "pan":"Distribuye el sonido del canal entre altavoces izquierdo y derecho.",
 "volume":"Ajusta el nivel de reproducción o mezcla de esta pista.",
 "gain":"Ajusta la ganancia de audio de la pista o del máster.",
 "swing":"Desplaza golpes alternos de la rejilla para crear swing.",
 "bars":"Establece el número de compases del patrón.",
 "seq_bpm":"Ajusta el tempo del secuenciador de batería.",
 "seq_swing":"Desplaza golpes alternos del patrón rítmico.",
 "seq_velocity":"Determina la fuerza de los golpes MIDI del patrón.",
 "seq_bars":"Selecciona cuántos compases tendrá el patrón de batería.",
 "edit_gain":"Modifica el volumen del audio editado de batería.",
 "eq_low":"Ajusta los graves del ecualizador del canal.",
 "eq_mid":"Ajusta los medios del ecualizador del canal.",
 "eq_high":"Ajusta los agudos del ecualizador del canal.",
 "trim_start":"Posición de inicio del fragmento de batería que vas a editar.",
 "trim_end":"Posición de finalización del fragmento de batería.",
 "fade_in":"Ajusta la duración del fundido de entrada.",
 "fade_out":"Ajusta la duración del fundido de salida.",
 "note_apply":"Aplica los valores numéricos a las notas MIDI seleccionadas.",
 "mix":"Regula los niveles y el balance de pistas al generar la mezcla.",
 "mute":"Silencia esta pista en el procesamiento de mezcla.",
 "solo":"Escucha esta pista sin las demás en la mezcla.",
 "slider":"Desliza para cambiar el valor de este control.",
 "number":"Introduce el valor del ajuste con precisión.",
 "midi_preset":"Carga una configuración de transcripción de Audio a MIDI.",
 "refine":"Escoge cómo refinar las notas MIDI obtenidas del análisis.",
 "precision_profile":"Selecciona el nivel de precisión del motor MIDI.",
 "stem_count":"Escoge el número de pistas que extraerá el separador automático.",
 "grid_choice":"Define la subdivisión temporal del Piano Roll de Inicio.",
 "roll_position":"Recorre la posición temporal del MIDI en la vista previa.",
 "note_velocity":"Regula la velocidad (intensidad) de las notas MIDI.",
 "vocal_source":"Elige la voz aislada del proyecto que quieres afinar.",
 "vocal_tonic":"Selecciona la nota fundamental de la tonalidad vocal.",
 "vocal_scale":"Selecciona la escala para ajustar la afinación vocal.",
 "vocal_strength":"Regula la intensidad de corrección de la voz.",
 "stem_preview_choice":"Selecciona qué pista aislada quieres preescuchar.",
 "refinement":"Escoge el método para mejorar la transcripción detectada.",
 "stem_shelf":"Selecciona una pista del proyecto para convertirla a MIDI.",
 "output_filename":"Introduce el nombre del archivo que será exportado."

}
ACTION_DESC={
 "guardar": "Guarda el elemento o configuración indicados en esta sección.",
 "borrar":"Elimina el elemento seleccionado de esta sección.",
 "cerrar":"Cierra la ventana o el proyecto indicado.",
 "cancelar":"Detiene la operación actual sin aplicar los cambios pendientes.",
 "detener":"Detiene el proceso o la reproducción activa.",
 "pausa":"Pausa la grabación o reproducción sin descartar el archivo.",
 "reanudar":"Continúa una operación que estaba en pausa.",
 "reproducir":"Inicia la escucha del audio o MIDI seleccionado.",
 "escuchar":"Reproduce la fuente o resultado indicado para comprobarlo.",
 "importar":"Abre un diálogo para elegir un archivo de entrada.",
 "cargar":"Carga un archivo o un conjunto de pistas para utilizarlo en esta sección.",
 "elegir":"Abre el selector del archivo o carpeta que se utilizará.",
 "abrir":"Abre la sección, proyecto o archivo indicado.",
 "actualizar":"Vuelve a consultar las fuentes o resultados disponibles.",
 "procesar":"Genera un archivo nuevo con los parámetros establecidos. No modifica el original.",
 "desglosar":"Procesa la pista de batería para extraer sus elementos.",
 "separar":"Inicia la separación de audio utilizando el modelo y ajustes elegidos.",
 "convertir":"Analiza la fuente de audio y genera una transcripción MIDI.",
 "grabar":"Inicia la captura del audio de la fuente elegida.",
 "grabar toma":"Captura una nueva toma de audio en el proyecto activo.",
 "aplicar":"Confirma los valores actuales y los utiliza en la acción indicada.",
 "analizar":"Ejecuta el análisis correspondiente sobre la fuente elegida.",
 "seleccionar":"Marca los elementos indicados para editar o utilizar.",
 "deshacer":"Revierte el último cambio del editor.",
 "rehacer":"Vuelve a aplicar el cambio que acababas de deshacer.",
 "copiar":"Copia al portapapeles las notas o el elemento seleccionado.",
 "pegar":"Pega las notas copiadas en la posición del editor.",
 "eliminar":"Elimina la nota o elemento seleccionado de la edición.",
 "cuantizar":"Alinea las notas a la subdivisión de tiempo elegida.",
 "zoom":"Ajusta la escala de visualización de las ondas o notas.",
 "volver":"Regresa a la sección anterior.",
 "ayuda":"Abre las instrucciones de uso de esta función.",
 "ajustes":"Abre la configuración avanzada de esta sección.",
 "preferencias":"Abre las preferencias y opciones de funcionamiento.",
 "reset":"Restaura los valores iniciales del control o de la sección.",
 "instalar":"Instala el modelo indicado si está disponible.",
 "ocultar":"Pliega el panel indicado sin perder sus parámetros.",
 "mostrar":"Despliega el panel indicado para acceder a sus ajustes.",
 "solo":"Activa o desactiva la escucha aislada de una pista.",
 "mute":"Silencia o recupera la pista sin borrarla.",
}
SPECIAL={
 "S":"Activa Solo: aísla este canal de audio en la escucha o mezcla.",
 "M":"Activa Mute: silencia este canal sin eliminarlo.",
 "▶":"Reproduce el archivo o la pista seleccionada.",
 "■":"Detiene la reproducción sin borrar ningún archivo.",
 "Ⅱ":"Pausa o continúa la reproducción actual.",
 "+":"Aumenta el nivel de zoom o el valor mostrado.",
 "−":"Reduce el nivel de zoom o el valor mostrado.",
 "-":"Reduce el nivel de zoom o el valor mostrado.",
 "↻":"Repite la reproducción o actualiza la vista, según la sección.",
}
VERB_HINT=("seleccion","ajust","cambia","modifica","activa","desactiva",
           "regula","elige","establece","guarda","abre","inicia","reproduce",
           "permite","controla","reduce","aumenta","indica","determina",
           "introduce","arrastr","pulsa","escribe","carga","mueve","convierte",
           "aplica","visualiza","muestra","detiene","pausa","confirma","define",
           "escucha","ejecuta","conserva","atenúa","realza","desplaza")

def _clean(s):
    return re.sub(r"\s+"," ",str(s or "")).strip()

def _parent_kind(obj):
    w=obj
    for _ in range(10):
        if w is None:break
        kind=getattr(w,"kind",None)
        if kind in ("vocal_completo","vocal_eq_fx","vocal_spatial",
                    "bateria_completa","monitor_grabacion","separar_audio",
                    "audio_a_midi","piano_roll_vista","mezclador",
                    "drum_mixer","drum_editor","drum_pattern"):
            return "preset"
        w=w.parentWidget()
    return ""

def _field_name(widget):
    # Nombres del código real: proceden de los widgets, no del texto de una ruta.
    if isinstance(widget,QWidget):
        cached=widget.property("contextHelpField")
        if cached:return str(cached)
    current=widget
    while isinstance(current,QWidget):
        for owner in (current,current.parentWidget()):
            if not isinstance(owner,QWidget):continue
            for key,value in vars(owner).items():
                if value is current and not key.startswith("_"):
                    if key not in ("slider","number","spin","choices"):
                        return key
        if current is widget:
            current=widget.parentWidget()
        else:
            break
    return ""

def _label(widget):
    # Buscar la etiqueta que comparte fila en QGridLayout / QFormLayout.
    target=widget
    for _ in range(4):
        parent=target.parentWidget()
        if not isinstance(parent,QWidget):break
        lay=parent.layout()
        if isinstance(lay,QFormLayout):
            label=lay.labelForField(target)
            if isinstance(label,QLabel) and _clean(label.text()):
                return _clean(label.text())
        if isinstance(lay,QGridLayout):
            ind=lay.indexOf(target)
            if ind>=0:
                row,col,_,_=lay.getItemPosition(ind)
                for candidate in range(col-1,-1,-1):
                    item=lay.itemAtPosition(row,candidate)
                    label=item.widget() if item else None
                    if isinstance(label,QLabel) and label.text().strip():
                        return _clean(label.text())
        if lay is not None:
            index=lay.indexOf(target)
            if index>0:
                for pos in range(index-1,max(-1,index-4),-1):
                    item=lay.itemAt(pos)
                    candidate=item.widget() if item else None
                    if isinstance(candidate,QLabel) and candidate.text().strip():
                        return _clean(candidate.text())
        target=parent
    return ""

def _describe_button(widget):
    text=_clean(widget.text())
    if not text and widget.objectName()=="cardHelpButton":
        return "Abre la explicación detallada de esta tarjeta y sus opciones."
    if widget.objectName()=="studioCloseControl":
        return "Cierra la ventana de la aplicación."
    if widget.objectName()=="studioWindowControl":
        return "Minimiza o maximiza la ventana, según el botón."
    if widget.objectName()=="studioCardHeading":
        return "Abre el módulo «"+text+"» para trabajar con sus controles."
    if _parent_kind(widget)=="preset":
        if text.lower()=="guardar":
            return "Guarda en este banco el preset propio con el nombre y los ajustes actuales."
        if text.lower()=="borrar":
            return "Elimina únicamente el preset propio seleccionado, no los audios ni las grabaciones."
    if text in ("↶","↷"):
        return ("Deshace el último cambio del Piano Roll." if text=="↶"
                else "Rehace el cambio deshecho en el Piano Roll.")
    if text=="⌕":return "Abre el editor Piano Roll completo."
    if text in ("◀","▶"):
        widget_parent=widget.parentWidget()
        if widget_parent is not None and widget_parent.__class__.__name__=="QWidget":
            current=widget_parent
            for _ in range(5):
                if current is None:break
                if current.__class__.__name__=="Card" and "piano" in _clean(
                        getattr(getattr(current,"header",None),"text",lambda:"")()).lower():
                    return ("Retrocede cuatro posiciones de la vista previa MIDI."
                            if text=="◀" else
                            "Avanza cuatro posiciones de la vista previa MIDI.")
                current=current.parentWidget()
    if text in SPECIAL:return SPECIAL[text]
    text=re.sub(r"^[^\wÁÉÍÓÚÜÑáéíóúüñ]+\s*","",text).strip()
    if not text:return "Ejecuta la función de este botón en el panel actual."
    for verb,description in ACTION_DESC.items():
        if verb in text.casefold():
            return description + (" Opción: "+text+"." if len(text)>len(verb)+4 else "")
    if widget.isCheckable():
        return "Activa o desactiva la opción «"+text+"» sin guardar automáticamente ningún archivo."
    return "Ejecuta «"+text+"» en el módulo actual."

def _describe(widget):
    if widget.objectName()=="qt_spinbox_lineedit":
        parent=widget.parentWidget()
        if isinstance(parent,QAbstractSpinBox):
            return _describe(parent)
    explicit=widget.property("contextHelpDescription")
    if explicit:return str(explicit)
    if isinstance(widget,QScrollBar):return ""
    if widget.objectName()=="qt_tableview_cornerbutton":
        return "Selecciona las filas o columnas de la tabla."
    if isinstance(widget,QAbstractButton):
        if isinstance(widget,(QCheckBox,QRadioButton)):
            return "Activa o desactiva «"+_clean(widget.text())+"» al procesar o visualizar el contenido."
        return _describe_button(widget)
    name=_field_name(widget)
    if name in FIELD_DESC:return FIELD_DESC[name]
    parent=widget.parentWidget()
    if parent and parent.__class__.__name__ in ("SliderNumber","StudioSliderSpin"):
        outer=_field_name(parent)
        if outer in FIELD_DESC:return FIELD_DESC[outer]
    if _parent_kind(widget)=="preset":
        if isinstance(widget,QLineEdit):return "Escribe el nombre del preset que quieres guardar."
        if isinstance(widget,QComboBox):return "Selecciona un preset de fábrica o propio para cargar sus ajustes."
    label=_label(widget)
    if isinstance(widget,QComboBox):
        return ("Selecciona «"+label+"»: determina qué opción se utilizará en este módulo."
                if label else
                "Elige una opción de esta lista para configurar la función correspondiente.")
    if isinstance(widget,QLineEdit):
        placeholder=_clean(widget.placeholderText())
        if placeholder:
            return "Indica «"+placeholder+"». Este campo no modifica los archivos por sí solo."
        return ("Introduce o consulta «"+label+"» en este módulo."
                if label else "Introduce o consulta el texto asociado a este ajuste.")
    if isinstance(widget,(QAbstractSlider,QAbstractSpinBox)):
        return ("Regula «"+label+"»; el valor elegido se utiliza al aplicar o procesar."
                if label else
                "Ajusta este valor para la función del panel; el cambio no modifica el audio original.")
    return ""

def _use_existing(widget,new):
    existing=_clean(widget.toolTip())
    if not existing:return new
    if existing.startswith(new):return existing
    if existing.startswith(("Ajusta este valor para la función del panel",
                             "Elige una opción de esta lista",
                             "Introduce o consulta el texto asociado")):
        return new
    # Qt anterior mostraba sólo un nombre de opción o una ruta; ofrecer contexto.
    if isinstance(widget,QComboBox) and existing==_clean(widget.currentText()):
        return new
    if isinstance(widget,QLineEdit):
        text=_clean(widget.text())
        if existing==text and (text.startswith("/") or text.startswith("~")):
            return new+"\nArchivo o ruta actual: "+text
    # Los controles del editor de notas heredaban una ayuda idéntica
    # («Introduce un valor MIDI») que no distinguía Altura/Inicio/Duración.
    if existing.casefold().startswith("introduce un valor midi numérico"):
        return new+" "+existing
    # El antiguo «arrastra para ajustar» no indica qué parámetro cambia.
    if isinstance(widget,(QAbstractSlider,QAbstractSpinBox)) and (
            "arrastra para ajustar" in existing.casefold()
            or existing.casefold() in ("ajusta el valor","valor")):
        return new+" "+existing
    if any(word in existing.casefold() for word in VERB_HINT):
        return existing
    # Conserva los detalles técnicos de ayudas incompletas.
    if len(existing)>6 and existing!=new:
        return new+"\n"+existing
    return new

def _candidate(widget):
    return isinstance(widget,(QAbstractButton,QComboBox,QAbstractSlider,
                               QAbstractSpinBox,QLineEdit,QTabBar,QGroupBox,
                               QLabel,QProgressBar,QAbstractItemView,
                               QPlainTextEdit,QTextEdit,QGraphicsView,
                               QScrollArea))

class ContextHelp(QObject):
    def __init__(self,root):
        super().__init__(root)
        self.root=root
        # Preferencia GLOBAL: independiente del proyecto en uso.
        try:
            self.enabled=bool(root.config.get("professional_help_enabled",True))
        except (AttributeError,TypeError):
            self.enabled=True
        self._last=None
        self._hover_shown=False
        self._cache={}
        self._app=QApplication.instance()
        self._app.installEventFilter(self)
        self.populate()
        self.dynamic=QTimer(self)
        self.dynamic.setInterval(1800)
        self.dynamic.timeout.connect(self.populate)
        self.dynamic.start()

    def _belongs(self,obj):
        if not isinstance(obj,QWidget):return False
        widget=obj
        for _ in range(36):
            if widget is self.root:return True
            widget=widget.parentWidget()
            if widget is None:break
        return False

    def set_enabled(self,enabled):
        """Cambiar toda la ayuda inmediatamente y recordar la preferencia."""
        self.enabled=bool(enabled)
        self._hide()
        self.root.config["professional_help_enabled"]=self.enabled
        # Guardar en configuracion.json (ya existente) sin introducir
        # otro archivo de preferencias ni tocar proyectos del usuario.
        try:
            from main import PREFS
            path=Path(PREFS)
            old=json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            if not isinstance(old,dict):old={}
            old["professional_help_enabled"]=self.enabled
            fd,temp=tempfile.mkstemp(prefix=".stem_help_",suffix=".json",
                                     dir=path.parent)
            try:
                with os.fdopen(fd,"w",encoding="utf-8") as stream:
                    json.dump(old,stream,ensure_ascii=False,indent=2)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp,path)
            finally:
                Path(temp).unlink(missing_ok=True)
        except (OSError,ValueError,TypeError):
            # La sesión debe seguir funcionando aunque el disco no permita
            # guardar la preferencia.
            pass

    def _tip(self,obj,position=None):
        if not self.enabled:return ""
        if isinstance(obj,QTabBar):
            pos=position if position is not None else QPoint(0,0)
            idx=obj.tabAt(pos)
            if idx<0:return ""
            caption=_clean(obj.tabText(idx))
            basic=("Pestaña «"+caption+"». "+
                   _clean(obj.tabToolTip(idx)))
            return basic+"\n"+professional_details(obj,"")
        if isinstance(obj,QLabel):
            title=_clean(obj.text())
            if len(title)>65 or not title or "<" in title:return ""
            basic=obj.toolTip() or "Etiqueta «"+title+"»."
        elif isinstance(obj,QGroupBox):
            basic=obj.toolTip() or "Grupo de ajustes «"+_clean(obj.title())+"»."
        elif isinstance(obj,QProgressBar):
            basic=obj.toolTip() or "Progreso de la tarea."
        elif isinstance(obj,(QAbstractItemView,QPlainTextEdit,QTextEdit,
                             QGraphicsView,QScrollArea)):
            basic=obj.toolTip() or "Área de trabajo del módulo."
        else:
            description=_describe(obj)
            basic=_use_existing(obj,description) if description else obj.toolTip()
        from_field=_field_name(obj) if isinstance(obj,QWidget) else ""
        details=professional_details(obj,from_field)
        if not basic and not details:return ""
        return (basic+"\n"+details).strip()

    def populate(self):
        # Identificar parámetros incluso si sus widgets se crearon en un
        # contenedor intermedio (por ejemplo, los controles de DSP vocal).
        # No se inspeccionan carpetas ni se alteran preferencias.
        for owner in (self.root,*self.root.findChildren(QWidget)):
            for key,obj in vars(owner).items():
                # «slider», «spin» y «number» son piezas internas de un
                # ajuste con nombre propio: nunca reemplazar esa semántica.
                if key in ("slider","spin","number"):continue
                if key in FIELD_DESC and isinstance(obj,QWidget):
                    obj.setProperty("contextHelpField",key)
                    # SliderNumber y StudioSliderSpin contienen tanto fader
                    # como editor numérico: los dos explican el mismo ajuste.
                    for field in ("slider","spin","number"):
                        child=getattr(obj,field,None)
                        if isinstance(child,QWidget):
                            child.setProperty("contextHelpField",key)
        # Los controles de la consola y la preescucha se crean por canal;
        # su función depende del panel y no de un nombre genérico «slider».
        for owner in self.root.findChildren(QWidget):
            if owner.__class__.__name__=="ConsoleStrip":
                part=str(getattr(owner,"part",""))
                for key,description in (
                    ("fader","Ajusta la ganancia en dB del canal «"+part+"» al mezclar."),
                    ("knob","Distribuye el canal «"+part+"» a izquierda o derecha (PAN).")):
                    target=getattr(owner,key,None)
                    if isinstance(target,QWidget):
                        target.setProperty("contextHelpDescription",description)
            elif owner.__class__.__name__=="PreviewPlayer":
                for key,description in (
                    ("slider","Mueve el cursor temporal de escucha a otra posición del archivo."),
                    ("speed","Selecciona la velocidad de reproducción de esta preescucha."),
                    ("volume","Regula el volumen de escucha, sin modificar el archivo."),
                    ("device_choice","Elige el dispositivo que reproducirá este audio o MIDI.")):
                    target=getattr(owner,key,None)
                    if isinstance(target,QWidget):
                        target.setProperty("contextHelpDescription",description)
            elif owner.__class__.__name__=="StudioHome":
                for key,child in getattr(owner,"midi_sliders",{}).items():
                    if key in FIELD_DESC and isinstance(child,QWidget):
                        for candidate in (child,getattr(child,"slider",None),
                                          getattr(child,"number",None)):
                            if isinstance(candidate,QWidget):
                                candidate.setProperty("contextHelpField",key)
                for part,data in getattr(owner,"mixer_rows",{}).items():
                    if isinstance(data,dict):
                        fader=data.get("fader")
                        if isinstance(fader,QWidget):
                            fader.setProperty("contextHelpDescription",
                                "Regula el nivel del canal «"+str(part)+"» en la mezcla de Inicio.")
                for key,description in (
                    ("input","Selecciona la fuente de audio para grabar."),
                    ("vocal_source","Elige la voz del proyecto que se procesará."),
                    ("vocal_tonic","Selecciona la nota fundamental de la voz."),
                    ("vocal_scale","Elige la escala musical de afinación."),
                ):
                    target=getattr(owner,key,None)
                    if isinstance(target,QWidget):
                        target.setProperty("contextHelpDescription",description)
            elif owner.__class__.__name__=="VocalTuneModule":
                target=getattr(owner,"input",None)
                if isinstance(target,QWidget):
                    target.setProperty("contextHelpDescription",
                        "Indica el archivo de voz que se procesará. Su contenido original no cambia.")
            elif owner.__class__.__name__=="DrumModule":
                target=getattr(owner,"input",None)
                if isinstance(target,QWidget):
                    target.setProperty("contextHelpDescription",
                        "Indica la pista de batería original para separar sus instrumentos.")
        for tabs in self.root.findChildren(QTabWidget):
            for i in range(tabs.count()):
                if not tabs.tabToolTip(i).strip():
                    tabs.setTabToolTip(i,"Muestra las herramientas y los ajustes de «"
                                       +tabs.tabText(i)+"».")
        for obj in self.root.findChildren(QWidget):
            if not _candidate(obj) or isinstance(obj,QTabBar):
                continue
            if obj.objectName()=="qt_spinbox_lineedit":
                continue
            try:
                desc=_describe(obj)
                if not desc:continue
                result=_use_existing(obj,desc)
                if _clean(obj.toolTip())!=result:
                    obj.setToolTip(result)
                obj.setToolTipDuration(20000)
            except RuntimeError:
                pass

    def _hide(self):
        QToolTip.hideText()
        # Qt puede demorar ~300 ms el ocultado normal para evitar parpadeos;
        # aquí el requisito es desaparecer INMEDIATAMENTE al mover/clicar.
        for popup in self._app.topLevelWidgets():
            if popup.isVisible() and popup.windowType()==Qt.ToolTip:
                popup.hide()
        self._last=None
        self._hover_shown=False

    def eventFilter(self,obj,event):
        typ=event.type()
        if typ==QEvent.Show and self._belongs(obj) and _candidate(obj):
            # Nuevos controles del mezclador/diálogos: ayuda en cuanto
            # se presentan, sin depender de la siguiente actualización.
            if not isinstance(obj,QTabBar):
                explanation=_describe(obj)
                if explanation:
                    value=_use_existing(obj,explanation)
                    if _clean(obj.toolTip())!=value:
                        obj.setToolTip(value)
        if typ==QEvent.ToolTip and self._belongs(obj):
            if not self.enabled:
                # Desactivado: no mostrar tampoco el tooltip nativo de Qt.
                event.accept()
                return True
            target=obj
            if not _candidate(target):
                # QTableWidget / Piano Roll envían ToolTip a su viewport.
                parent=target.parentWidget() if isinstance(target,QWidget) else None
                if isinstance(parent,(QAbstractItemView,QGraphicsView)):
                    target=parent
                else:
                    return False
            message=self._tip(target,event.pos())
            if message:
                # Máximo unos 75 caracteres por línea, para que no tape el módulo.
                lines=[]
                for paragraph in message.splitlines():
                    lines.extend(textwrap.wrap(paragraph,width=67) or [""])
                colored=[]
                for part in lines:
                    safe=escape(part)
                    if any(part.startswith(pre) for pre in (
                            "Al mover", "Al pulsar","Si marcas","Si desmarcas",
                            "Estado actual","Valor actual","Consejo:",
                            "Opción actual", "Al seleccionar")):
                        safe="<b>"+safe+"</b>"
                    colored.append(safe)
                display="<div style='max-width:500px;white-space:normal'>"+(
                    "<br>".join(colored))+"</div>"
                QToolTip.showText(event.globalPos(),display,obj)
                self._last=obj
                self._hover_shown=True
                event.accept()
                return True
        elif typ in (QEvent.MouseMove,QEvent.HoverMove,QEvent.MouseButtonPress,
                     QEvent.MouseButtonDblClick,QEvent.Wheel,QEvent.Leave,
                     QEvent.WindowDeactivate,QEvent.KeyPress,QEvent.TouchBegin):
            if self._hover_shown and (self._belongs(obj) or obj is self._last or
                                       typ==QEvent.WindowDeactivate):
                self._hide()
        return False

def install(root):
    if hasattr(root,"_context_help") and root._context_help:
        return root._context_help
    root._context_help=ContextHelp(root)
    return root._context_help
