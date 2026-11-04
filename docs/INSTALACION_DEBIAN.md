# Instalar StemMIDI Studio en Debian 13

Es una beta de codigo fuente. Se recomienda instalarla en un entorno
Python virtual con PipeWire/PulseAudio activos.

Instala las dependencias del sistema (terminal):

    sudo apt update
    sudo apt install -y python3 python3-venv python3-pip ffmpeg       pulseaudio-utils libportaudio2 libsndfile1 libfluidsynth3       fluid-soundfont-gm xvfb

Descarga el repositorio y configura el entorno:

    git clone https://github.com/srwindows/StemMIDI-Studio.git
    cd StemMIDI-Studio
    python3 -m venv .venv
    . .venv/bin/activate
    pip install -r requirements-base.txt
    python main.py

La instalacion de IA externa, bancos SoundFont u otros complementos es
opcional y requiere comprobar sus propias licencias. Algunas funciones
no estaran disponibles sin esos recursos.

Captura con PipeWire/PulseAudio: selecciona una entrada real; la escucha
procesada requiere configurar una salida distinta de la que se captura
cuando se utiliza una fuente tipo sink.monitor. No se activa por defecto.
Para micrófonos abiertos, usa auriculares.

Para comprobar sintaxis y privacidad del paquete:

    python3 -m compileall -q .
    python3 -m unittest discover -s pruebas -p 'test_publicacion_privacidad.py'

Opcionalmente, para crear el ejecutable Linux (requiere revisar las
dependencias de PyInstaller en el equipo de destino):

    pip install pyinstaller
    pyinstaller --noconfirm MonitorDeGrabacion.spec

No se distribuyen archivos personales, modelos de terceros ni binarios
.exe/.dmg validados en este repositorio.
