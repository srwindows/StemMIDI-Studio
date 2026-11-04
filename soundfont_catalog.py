"""Inventario real de presets SF2: RIFF/pdta/phdr (sin cargar muestras PCM).

El orden/listado se obtiene del banco elegido, nunca de una tabla GM fija.
Las voces de batería SF2 pertenecen al banco 128.
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import re
import struct


def system_soundfont():
    """SF2 de TiMidity activo en Debian; None si no se puede determinar."""
    def scan(config, seen):
        path=Path(config)
        if path in seen or not path.is_file():return None
        seen.add(path)
        try:lines=path.read_text(encoding='utf-8',errors='replace').splitlines()
        except OSError:return None
        directory=Path('/usr/share/sounds/sf2')
        for line in lines:
            line=line.strip()
            if not line or line.startswith('#'):continue
            found=re.match(r'^dir\s+(.+)',line)
            if found:directory=Path(found.group(1).strip().strip('"'))
            match=re.match(r'^source\s+(.+)',line)
            if match:
                answer=scan(match.group(1).strip().strip('"'),seen)
                if answer:return answer
            match=re.search(r'%font\s+"([^"]+\.sf2)"',line,re.I)
            if not match:continue
            target=Path(match.group(1))
            if not target.is_absolute():target=directory/target
            if target.is_file():return target.resolve()
            # SF2 puede estar junto al propio .cfg, no en el dir anterior.
            candidate=path.parent/target.name
            if candidate.is_file():return candidate.resolve()
        return None
    return scan('/etc/timidity/timidity.cfg',set())


@lru_cache(maxsize=20)
def _presets(filename,mtime_ns,size):
    """Devuelve (banco, programa, nombre) existentes, sin el registro EOP."""
    result=[]
    with open(filename,'rb') as stream:
        if stream.read(4)!=b'RIFF':raise ValueError('No es un archivo RIFF')
        total=struct.unpack('<I',stream.read(4))[0]
        if stream.read(4)!=b'sfbk':raise ValueError('No es SoundFont SF2')
        limit=min(size,total+8)
        while stream.tell()+8<=limit:
            chunk=stream.read(4)
            length_bytes=stream.read(4)
            if len(length_bytes)!=4:break
            length=struct.unpack('<I',length_bytes)[0]
            end=stream.tell()+length+(length&1)
            if end>limit:raise ValueError('Chunk SF2 truncado')
            if chunk==b'LIST':
                group=stream.read(4)
                if group==b'pdta':
                    stop=stream.tell()+length-4
                    while stream.tell()+8<=stop:
                        tag=stream.read(4)
                        n=struct.unpack('<I',stream.read(4))[0]
                        if stream.tell()+n>stop:raise ValueError('Lista pdta truncada')
                        if tag==b'phdr':
                            if n%38:raise ValueError('Tabla phdr SF2 inválida')
                            raw=stream.read(n)
                            for pos in range(0,n-38,38):
                                name,program,bank,bag,*_=struct.unpack_from('<20sHHHIII',raw,pos)
                                next_bag=struct.unpack_from('<H',raw,pos+38+24)[0]
                                if next_bag<=bag:continue  # preset vacío
                                name=name.partition(b'\x00')[0].decode('latin1').strip()
                                if name:result.append((bank,program,name))
                            return tuple(dict.fromkeys(result))
                        stream.seek(n+(n&1),1)
            stream.seek(end)
    raise ValueError('SoundFont sin tabla de presets phdr')


def presets(path):
    file=Path(path).resolve()
    if file.suffix.lower()!='.sf2' or not file.is_file():
        raise ValueError('Banco SoundFont SF2 inexistente')
    stat=file.stat()
    return _presets(str(file),stat.st_mtime_ns,stat.st_size)
