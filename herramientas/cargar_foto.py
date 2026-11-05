"""Carga fotos de productos que no tienen foto en el sistema: le saca el fondo a cada una (igual que
recortar_fotos.py), la guarda en fotos-auto/<nombre>.webp y la anota en fotos-auto/index.json con el
nombre del producto tal como está en el sistema. El catálogo la muestra cuando el sistema no tiene
IMAGEN para ese producto; si después se sube una foto en el sistema, esa tiene prioridad.

Uso: python herramientas/cargar_foto.py <foto> "NOMBRE DEL PRODUCTO" [<foto> "NOMBRE" ...]
"""
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import recortar_fotos as rf  # noqa: E402

CARPETA = os.path.join(rf.RAIZ, 'fotos-auto')
INDICE = os.path.join(CARPETA, 'index.json')


def norm(s):
    # Igual que norm() del catálogo: sin acentos, en mayúsculas y con los espacios normalizados
    s = ''.join(c for c in unicodedata.normalize('NFD', str(s)) if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', s.upper()).strip()


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', norm(s).lower()).strip('-')[:70] or 'producto'


def main():
    pares = sys.argv[1:]
    if not pares or len(pares) % 2:
        sys.exit(__doc__)
    from rembg import new_session
    sesion = new_session(rf.MODELO)
    indice = json.load(open(INDICE, encoding='utf-8')) if os.path.exists(INDICE) else {}
    for foto, nombre in zip(pares[0::2], pares[1::2]):
        cut, problema = rf.recortar(sesion, foto)
        if problema:
            print(f'{nombre}: NO SE CARGÓ ({problema})')
            continue
        archivo = slug(nombre) + '.webp'
        ruta = os.path.join(CARPETA, archivo)
        cut.save(ruta, 'WEBP', quality=82, method=6)
        indice[norm(nombre)] = [archivo, rf.huella(ruta)]
        print(f'{nombre}: fotos-auto/{archivo} ({cut.width}x{cut.height})')
    with open(INDICE, 'w', encoding='utf-8') as f:
        json.dump(dict(sorted(indice.items())), f, ensure_ascii=False, indent=1)
        f.write('\n')


if __name__ == '__main__':
    main()
