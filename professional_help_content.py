"""Explicaciones profesionales verificables para controles de StemMIDI Studio.

No confunde etiquetas con funciones de audio. Las direcciones concretas
se documentan por parámetro; para los desconocidos solo se explica el
comportamiento Qt (no inventar un algoritmo DSP).
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractSlider,QAbstractSpinBox,QComboBox,QCheckBox,QRadioButton,
    QAbstractButton,QLineEdit,QTabBar,QProgressBar,QGroupBox,QLabel,
    QAbstractItemView,QPlainTextEdit,QTextEdit,QGraphicsView,QScrollArea
)

# (al aumentar, al disminuir, consejo) — semántica de la función real.
DIRECTION={
 "declick":("Activa la reparación de chasquidos puntuales.",
            "Desactiva la reparación de impulsos.",
            "No corrige distorsión permanente."),
 "bass":("Realza la banda grave de 120 Hz.",
         "Reduce la banda grave para limpiar retumbe.",
         "Ecualiza escuchando todo el material, no solo en solo."),
 "lowmid":("Añade cuerpo a unos 390 Hz.","Reduce sonido turbio cerca de 390 Hz.",
           "Evita vaciar el cuerpo de las voces."),
 "highmid":("Aumenta presencia a 2,8 kHz.","Suaviza la dureza de presencia.",
            "Pequeños cambios de ±2–3 dB son un buen punto de partida."),
 "treble":("Realza los agudos a 8 kHz.","Atenúa el siseo o aspereza de agudos.",
           "No recupera información perdida por compresión."),
 "denoise":("Reduce más ruido continuo, pero puede añadir artefactos.",
            "Conserva más componentes débiles de la señal original.",
            "Escucha el ruido de fondo y también las colas de las notas."),
 "comp_threshold":("Comprime solo los picos más altos.",
                   "Empieza a comprimir sonidos más suaves.",
                   "Es un umbral negativo en dB; -10 es mayor que -30."),
 "comp_ratio":("Aumenta la reducción de dinámica por encima del umbral.",
               "Conserva mayor contraste entre sonidos fuertes y suaves.",
               "Una ratio de 1:1 no comprime."),
 "comp_attack":("Comprime más lentamente y conserva más transitorios.",
                "Comprime antes y reduce el golpe inicial.",
                "Evita ataques rápidos cuando necesites conservar percusión."),
 "comp_release":("Mantiene la compresión más tiempo.",
                 "Suelta antes la compresión.",
                 "Busca un tiempo que no produzca bombeo."),
 "gate_threshold":("Cierra la puerta también ante niveles más altos.",
                   "Deja pasar sonidos suaves y más fondo.",
                   "Si se corta el final de palabras, reduce el umbral."),
 "lowpass":("Permite conservar más agudos.","Elimina más frecuencias agudas.",
            "Solo actúa si Paso bajo está activado."),
 "deesser":("Reduce más sibilancias, con riesgo de apagar las consonantes.",
            "Reduce menos las eses.","Es útil para voz, no siempre para música."),
 "comp_enabled":("Activa la compresión configurada.",
                 "Omite la compresión.","Puedes comparar sin perder la toma."),
 "stereo_width":("Aumenta la amplitud estéreo.","Disminuye la anchura hacia mono.",
                 "Escucha también en mono si lo vas a publicar."),
 "output_gain":("Aumenta nivel y riesgo de recorte.","Reduce el nivel de salida.",
                "Mantén el limitador si vas a aumentar mucho la señal."),
 "target_lufs":("Eleva la sonoridad objetivo (menos dB negativos).",
                "Reduce la sonoridad objetivo.",
                "La estimación de una pasada no garantiza el valor exacto."),
 "input_gain":("Amplifica más la señal capturada; puede saturar.",
               "Reduce el nivel de entrada; evita clipping pero puede quedar bajo.",
               "Mira los medidores: procura que los picos no lleguen a 0 dBFS."),
 "input_gain_db":("Aplica más ganancia a la grabación; puede saturar.",
                  "Reduce el nivel de captura.","Observa los VU y evita llegar a 0 dBFS."),
 "fader":("Incrementa la ganancia o volumen del canal.",
          "Reduce la ganancia del canal.","Controla picos y la suma en el máster."),
 "knob":("Desplaza la posición panorámica hacia la derecha.",
         "La desplaza hacia la izquierda.","El centro mantiene el balance estéreo."),
 "roll_position":("Avanza a una posición posterior de la vista previa MIDI.",
                  "Vuelve a una posición anterior.","No modifica notas: solo navega."),
 "timeline":("Avanza el cursor de reproducción hacia el final.",
             "Retrocede hacia el inicio.","Mover el cursor no modifica el audio."),
 "vocal_strength":("Intensifica la corrección tonal.",
                   "Conserva más la entonación original.",
                   "Escucha artefactos de corrección de tono."),
 "input_balance":("Desplaza la captura hacia el canal derecho.",
                  "Desplaza la captura hacia el canal izquierdo.",
                  "En el centro el balance queda equilibrado."),
 "volume":("Sube el nivel de escucha o mezcla.","Baja el nivel, hasta silenciarlo.",
           "Comprueba los VU para evitar saturación de la mezcla."),
 "gain":("Aumenta ganancia y nivel del canal.","Atenúa el canal.",
         "Los valores excesivos pueden producir recorte digital."),
 "edit_gain":("Aumenta el volumen del fragmento de batería.",
              "Atenúa el fragmento.","Comprueba los picos al reproducir."),
 "pan":("Envía más señal a la derecha.","Envía más señal a la izquierda.",
        "La posición central reparte sonido entre ambos canales."),
 "eq_low":("Realza las frecuencias graves.","Reduce las frecuencias graves.",
           "Escucha bombo y bajo para evitar enmascaramiento."),
 "eq_mid":("Realza las frecuencias medias.","Atenúa las frecuencias medias.",
           "La voz y gran parte de los instrumentos ocupan los medios."),
 "eq_high":("Realza las frecuencias agudas.","Atenúa los agudos.",
            "Vigila sibilancias y ruido cuando realces."),
 "warmth":("Aumenta la calidez tonal.","Conserva un sonido menos cálido.",
           "Compara con la señal original para evitar exceso de graves."),
 "presence":("Incrementa la presencia de la voz en medios.",
             "Reduce el realce de presencia.","Si es excesiva la voz puede sonar dura."),
 "air":("Aumenta el brillo y aire de la voz.",
        "Disminuye el realce de altas frecuencias.","Vigila las sibilancias."),
 "deesser":("Intensifica la reducción de sibilancias.",
            "Deja pasar más sonidos sibilantes.",
            "Demasiada reducción puede afectar a la claridad de consonantes."),
 "gate":("Aumenta la atenuación del ruido en pausas.",
         "Deja pasar más ruido de fondo.",
         "Un ajuste fuerte puede cortar finales de palabras."),
 "highpass":("Eleva la frecuencia de corte: elimina más graves.",
             "Baja el corte: conserva más graves.",
             "Evita cortar fundamentales graves de la voz."),
 "compression":("Comprime más la dinámica: reduce diferencias entre fuerte y suave.",
                "Deja una dinámica más natural.",
                "Compara el nivel percibido antes y después del procesado."),
 "reverb":("Aumenta la reverberación y sensación de espacio.",
           "Acerca la voz y reduce la cola reverberante.",
           "Demasiada reverb resta inteligibilidad."),
 "wet":("Aporta más señal procesada por los efectos.",
        "Conserva más voz seca original.",
        "Compara A/B para evaluar el balance seco/procesado."),
 "delay":("Añade más presencia del eco.","Disminuye la cantidad de eco.",
          "Escucha si las repeticiones enturbian las palabras."),
 "delay_ms":("Aumenta el intervalo entre ecos.","Reduce el intervalo entre ecos.",
             "Este tiempo se aplica solo si Delay está activado."),
 "doubler":("Intensifica el doblado artificial.","Reduce o desactiva el doblado.",
            "Puede introducir sensación de coro, incluso en una voz solista."),
 "stereo_width":("Amplía la separación estéreo.","Estrecha la imagen hacia el centro.",
                 "Comprueba el resultado también en mono."),
 "output_gain_db":("Eleva el volumen final y riesgo de clipping.",
                   "Disminuye el volumen final.","No superes el nivel digital máximo."),
 "retune":("Hace más lenta la transición tonal, conservando deslizamientos.",
           "Acorta el tiempo y corrige de forma más rápida.",
           "Son milisegundos: un tiempo muy corto puede sonar artificial."),
 "strength":("Acerca más las notas a la afinación elegida.",
             "Deja más variaciones de afinación de origen.",
             "No mejora la dicción: modifica la corrección tonal."),
 "humanize":("Conserva más variaciones humanas de altura.",
             "Permite una corrección más rígida.",
             "Busca un equilibrio entre precisión y naturalidad."),
 "threshold":("Ignora desviaciones de afinación mayores antes de corregir.",
              "Corrige también desviaciones pequeñas.",
              "En cents, controla el umbral mínimo de corrección."),
 "character_amount":("Intensifica el carácter vocal seleccionado.",
                     "Aproxima el carácter a la voz sin ese efecto.",
                     "Selecciona antes un carácter diferente de Natural."),
 "learn_melody":("Sigue más de cerca las notas de la voz de referencia.",
                 "Conserva más tu propia melodía de origen.",
                 "Requiere ambas voces cantando la misma canción."),
 "learn_vibrato":("Aplica más oscilaciones tonales de referencia.",
                  "Conserva más tu propio vibrato.",
                  "La transferencia aproximada puede introducir artefactos."),
 "learn_dynamics":("Sigue más las variaciones relativas de intensidad de la referencia.",
                   "Mantiene más tu dinámica original.",
                   "No transfiere pronunciación ni respiraciones."),
 "learn_timing":("Acerca más la duración global a la referencia.",
                 "Conserva más la duración de tu propia grabación.",
                 "En esta versión NO alinea cada sílaba individualmente."),
 "tempo_bpm":("Aumenta el número de pulsaciones por minuto; mayor velocidad si se aplica.",
              "Reduce las pulsaciones por minuto.",
              "Revisa el modo de tempo para saber si modifica reproducción o rejilla."),
 "bpm":("Más pulsaciones por minuto (tempo mayor).",
        "Menos pulsaciones por minuto (tempo menor).",
        "El BPM de detección afecta a la interpretación temporal del MIDI."),
 "seq_bpm":("Patrón de batería más rápido.","Patrón más lento.",
            "Escucha junto a las otras pistas antes de exportar."),
 "swing":("Desplaza más los tiempos alternos de la rejilla.",
          "Disminuye el desplazamiento hacia una rejilla más recta.",
          "Swing exagerado puede desajustar el acompañamiento."),
 "seq_swing":("Aumenta el swing de los golpes alternos.",
              "Acerca el ritmo a tiempos rectos.",
              "Compáralo con el acompañamiento."),
 "seq_velocity":("Genera golpes MIDI más intensos.",
                 "Genera golpes MIDI menos intensos.",
                 "La intensidad audible depende del instrumento o soundfont."),
 "min_velocity":("Descarta notas con velocidad inferior al nuevo límite.",
                 "Acepta más notas de intensidad baja.",
                 "Un umbral excesivo puede eliminar golpes suaves."),
 "note_velocity":("La nota seleccionada sonará más intensa en un instrumento MIDI.",
                  "Reducirá su intensidad.","La respuesta audible depende del instrumento."),
 "velocity":("Incrementa la fuerza MIDI de la nota.",
             "Reduce su fuerza.","MIDI no es audio; requiere instrumento al reproducir."),
 "note_pitch":("Sube el tono MIDI en semitonos.","Baja el tono MIDI en semitonos.",
               "Cada 12 semitonos se cambia una octava."),
 "note_start":("Mueve el comienzo de la nota hacia más tarde.",
               "Lo adelanta en la línea temporal.",
               "Comprueba si cambia la sincronía con otras notas."),
 "note_duration":("Prolonga la duración de la nota.","La acorta.",
                  "La duración puede afectar a notas superpuestas."),
 "grid":("Según el valor, modifica la densidad de la rejilla temporal.",
         "Según el valor, modifica la rejilla en sentido opuesto.",
         "La cuantización solo modifica las notas cuando la aplicas."),
 "zoom":("Acerca la vista, mostrando menos tiempo con más detalle.",
         "Aleja la vista, mostrando más tiempo.",
         "Solo cambia la visualización, no el sonido."),
 "zoom_vertical":("Las filas del piano son más altas.",
                  "Las filas se hacen más compactas.",
                  "Solo cambia la geometría del editor."),
 "zoom_digit":("Más píxeles por unidad temporal: mayor acercamiento.",
               "Menos píxeles: mayor extensión visible.",
               "No altera el MIDI."),
 "zoom_vertical_digit":("Aumenta la altura visual de cada nota.",
                        "Reduce esa altura.","No modifica el tono MIDI."),
 "fade_in":("La entrada tarda más tiempo en alcanzar su volumen.",
            "El fundido de entrada se acorta.",
            "Útil para evitar entradas bruscas."),
 "fade_out":("La salida tarda más en desvanecerse.",
             "El fundido final es más corto.",
             "Evita cortar notas que aún estén sonando."),
 "trim_start":("Recorta más contenido del principio.",
               "Conserva más contenido al comienzo.",
               "Comprueba que el inicio quede antes del final."),
 "trim_end":("Desplaza el final hacia más adelante.",
             "Lo adelanta y acorta el fragmento.",
             "No recortes la cola de los golpes."),
 "low":("Eleva la nota MIDI mínima del rango detectado.",
        "Incluye notas de registro más grave.",
        "Las notas fuera del rango quedan descartadas."),
 "high":("Permite incluir notas más agudas.",
         "Restringe el análisis a un registro más bajo.",
         "Mantén este límite por encima del mínimo."),
 "min_duration":("Descarta eventos de duración más corta.",
                 "Permite captar notas más breves.",
                 "Un filtro alto puede eliminar adornos o notas cortas."),
 "merge_gap":("Une eventos separados por silencios algo mayores.",
              "Une solo eventos muy próximos.",
              "Demasiado puede juntar notas que deberían estar separadas."),
 "note_shift":("Desplaza notas a un tiempo posterior.",
               "Las adelanta en el tiempo.",
               "Revisa la sincronización antes de aplicar."),
 "grid_offset":("Desplaza la rejilla temporal en sentido positivo.",
                "La mueve en sentido negativo.",
                "Un desfase afecta a la posición de todas las notas cuantizadas."),
 "bars":("Aumenta los compases del patrón.","Reduce los compases.",
         "Cambiar la longitud puede modificar cómo se repite el loop."),
 "seq_bars":("Patrón rítmico más largo.","Patrón más corto.",
             "Revisa que las notas queden dentro del patrón."),
 "onset":("Aumenta el valor del umbral de inicio de nota.",
          "Disminuye el umbral de inicio.",
          "El efecto exacto depende del detector MIDI y del preset activo."),
 "frame":("Aumenta el umbral de detección por fotograma.",
          "Lo reduce.",
          "Verifica si aparecen notas falsas o desaparecen notas débiles."),
 "drum":("Aumenta el parámetro de sensibilidad de percusión.",
         "Reduce ese parámetro.",
         "Comprueba bombo, caja y platos por separado."),
}
# Controles con efecto ON/OFF específico, sin atribuir efectos no implementados.
SWITCH={
 "auto_after":("Una copia nueva se procesa AUTOMÁTICAMENTE cuando termina la grabación.",
               "El laboratorio solo se ejecuta si pulsas Procesar.",
               ),
 "lowpass_enabled":("Activa el corte de agudos seleccionado.",
                     "No elimina agudos con un paso bajo."),
 "gate_enabled":("Reduce el ruido en silencios, según su umbral.",
                 "Desactiva la puerta de ruido."),
 "declick":("Aplica reparación de clics a la copia procesada.",
             "No repara clics."),
 "comp_enabled":("Activa compresor con threshold, ratio, ataque y release.",
                 "No aplica compresión."),
 "limiter":("Limita los picos finales a un techo aproximado de -1 dBFS.",
             "No aplica la protección final contra picos."),
 "loudnorm_enabled":("Activa normalización de sonoridad a LUFS objetivo.",
                     "No aplica normalización de sonoridad."),
 "ref_consent":("Confirma que posees autorización para procesar la voz de referencia.",
                "No se autoriza ni se inicia procesamiento con esa referencia."),
 "learn_same_song":("Autoriza el modo de comparación de dos interpretaciones de la misma canción.",
                     "Impide iniciar la transferencia asistida para evitar una comparación incorrecta."),
 "bypass_tune":("Se omite la corrección de notas; los efectos vocales pueden seguir funcionando.",
                "Se permite la corrección de afinación configurada."),
 "tempo_auto":("Calcula el tempo a partir del audio según el motor disponible.",
               "Utiliza el tempo establecido manualmente cuando el módulo lo admite."),
 "mute":("Silencia la pista sin borrarla.","La pista vuelve a participar en la mezcla."),
 "solo":("Se escucha prioritariamente esta pista de forma aislada.",
         "Se restaura la escucha normal según los demás SOLO activos."),
}

def _clean(text):
    return " ".join(str(text or "").split())

def directional(field,widget):
    from PySide6.QtWidgets import QScrollBar
    if isinstance(widget,QScrollBar):
        axis=("horizontal" if widget.orientation()==Qt.Horizontal else "vertical")
        return (f"Desplazamiento {axis}: arrastra el control para ver otra "
                "zona de la página o del editor. Hacia el final se avanza; "
                "hacia el principio se retrocede.\n"
                "No modifica la música, los parámetros de procesamiento ni "
                "los archivos; solo cambia qué parte queda visible.")
    key=field
    if key in ("preview","source_preview","output_preview","player"):
        key="timeline"
    if key=="body":
        desc=(str(widget.toolTip())+" "+str(widget.property("contextHelpDescription") or "")).lower()
        if "balance" in desc or "panorama" in desc:key="pan"
        elif "ganancia" in desc or "gain" in desc:key="input_gain"
    effect=DIRECTION.get(key)
    value=widget.value()
    minimum=widget.minimum()
    maximum=widget.maximum()
    orientation=("izquierda / derecha" if
                 not isinstance(widget,QAbstractSlider) or
                 widget.orientation()==Qt.Horizontal else
                 "abajo / arriba")
    if isinstance(widget,QAbstractSlider):
        reversed_direction=bool(widget.invertedAppearance())
        forward=("izquierda / abajo" if reversed_direction else
                 "derecha / arriba")
        backward=("derecha / arriba" if reversed_direction else
                  "izquierda / abajo")
    else:
        forward="aumentar el número / flecha superior"
        backward="reducir el número / flecha inferior"
    if effect:
        inc,dec,tips=effect
    else:
        inc=f"Sube el ajuste «{field or 'valor'}» hacia su máximo."
        dec=f"Baja el ajuste «{field or 'valor'}» hacia su mínimo."
        tips="Comprueba el resultado al aplicar o procesar; mover este control no garantiza un render inmediato."
    suffix=widget.suffix() if isinstance(widget,QAbstractSpinBox) else ""
    return (f"Al mover hacia {forward}: {inc}\n"
            f"Al mover hacia {backward}: {dec}\n"
            f"Valor actual: {value}{suffix}. Rango: {minimum}–{maximum}{suffix}.\n"
            f"Consejo: {tips}")

def describe(widget,field):
    if isinstance(widget,QAbstractSlider):
        return directional(field,widget)
    if isinstance(widget,QAbstractSpinBox):
        return directional(field,widget)
    if isinstance(widget,(QCheckBox,QRadioButton)):
        on,off=SWITCH.get(field,(
            "Incluye o activa esta opción en el módulo según sus parámetros.",
            "Excluye o desactiva esta opción en el módulo."))
        status="ACTIVADA" if widget.isChecked() else "DESACTIVADA"
        return (f"Estado actual: {status}.\n"
                f"Si marcas: {on}\nSi desmarcas: {off}\n"
                "Consejo: activar una casilla no siempre genera un resultado; "
                "usa Procesar/Aplicar si el módulo lo solicita.")
    if isinstance(widget,QComboBox):
        current=_clean(widget.currentText())
        return (f"Opción actual: {current or 'sin seleccionar'}. "
                f"Opciones disponibles: {widget.count()}.\n"
                "Al desplegar puedes comparar y elegir otra opción: cambia "
                "la fuente, perfil, escala, formato o destino según el selector.\n"
                "Consejo: elegir una opción puede preparar parámetros, pero "
                "no significa que el audio ya se haya procesado.")
    if isinstance(widget,QLineEdit):
        if widget.isReadOnly():
            return ("Campo de consulta: muestra la selección actual. "
                    "Para cambiarla utiliza Importar, Elegir o Explorar.\n"
                    "El contenido original no cambia por consultarlo.")
        return ("Introduce el nombre, ruta o valor indicado. "
                "Al editar este texto se prepara un parámetro.\n"
                "Consejo: verifica nombre, extensión y destino antes de guardar "
                "o procesar para evitar sobrescrituras.")
    if isinstance(widget,QTabBar):
        return ("Al seleccionar se cambia la sección visible. "
                "Los parámetros de las otras pestañas no se borran.\n"
                "Consejo: cambiar de pestaña no equivale a procesar ni guardar.")
    if isinstance(widget,QProgressBar):
        return ("El porcentaje refleja el progreso de una operación; "
                "no es ajustable con el ratón.")
    if isinstance(widget,QAbstractButton):
        if widget.isCheckable():
            return ("Estado: "+("ACTIVADO" if widget.isChecked() else "DESACTIVADO")+
                    ".\nAl pulsar alterna entre ambos estados; "
                    "consulta la explicación de su función anterior.")
        return ("Al pulsar se ejecuta la acción indicada. "
                "Pasar el ratón no cambia nada.\n"
                "Consejo: si la acción procesa, importa, guarda o elimina "
                "archivos, revisa antes la selección y el proyecto activo.")
    if isinstance(widget,QAbstractItemView):
        multi=(widget.selectionMode() in (
               QAbstractItemView.ExtendedSelection,
               QAbstractItemView.MultiSelection))
        return ("Tabla o lista de archivos, pistas o resultados: haz clic "
                "en una fila para seleccionarla. "+
                ("Ctrl permite añadir elementos; Mayús selecciona un rango."
                 if multi else "Selecciona un elemento cada vez.")+
                "\nLa selección no exporta ni elimina archivos por sí sola. "
                "Utiliza los botones de Guardar, Abrir o Procesar.")
    if isinstance(widget,QGraphicsView):
        return ("Zona de edición visual: muestra pistas o notas. "
                "Selecciona elementos con las herramientas del editor y "
                "guarda los cambios para conservarlos.\n"
                "El zoom modifica la vista, no el contenido musical.")
    if isinstance(widget,(QPlainTextEdit,QTextEdit)):
        return ("Área de texto o registro: contiene información, resultados "
                "y mensajes del módulo. Si es editable, puedes escribir; "
                "si es de solo lectura, no modifica la sesión.")
    if isinstance(widget,QScrollArea):
        return ("Área de trabajo desplazable: usa la rueda o las barras "
                "para mostrar los ajustes fuera de pantalla. "
                "No cambia el procesamiento.")
    if isinstance(widget,QGroupBox):
        if widget.isCheckable():
            return ("Al marcar se habilita el grupo de ajustes; "
                    "al desmarcar se deshabilita ese grupo.")
        return "Agrupa los controles relacionados de esta sección."
    if isinstance(widget,QLabel):
        return "Etiqueta explicativa: indica qué ajuste controla el campo próximo."
    return ""
