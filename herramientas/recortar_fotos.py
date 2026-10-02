"""Fotos con fondo blanco: le saca el fondo a las fotos de los productos.

Cada foto de la raíz del repo (jpg, jpeg, jfif, png, webp) se recorta con un modelo
de recorte de fondo (IS-Net, licencia Apache 2.0: tarda ~1 s por foto en una
computadora común) y se guarda en recortes/<nombre>.webp, con fondo transparente y
ajustada al borde de la botella. El catálogo la muestra sobre blanco.

recortes/index.json dice qué foto tiene recorte: {"FOTO.JPG": ["FOTO.webp", "huella"]}.
La huella es la de la foto original: si alguien sube otra foto con el mismo nombre,
se vuelve a recortar. Las que ya están recortadas no se tocan.

Uso:  pip install "rembg[cpu]" pillow
      python herramientas/recortar_fotos.py            (solo las nuevas o cambiadas)
      python herramientas/recortar_fotos.py --todas    (rehace todas)
"""
import hashlib
import json
import os
import sys
import time

from PIL import Image, ImageOps

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA = os.path.join(RAIZ, 'recortes')
INDICE = os.path.join(CARPETA, 'index.json')
EXTENSIONES = ('.jpg', '.jpeg', '.jfif', '.png', '.webp')
MODELO = os.environ.get('MODELO_RECORTE', 'isnet-general-use')
LADO_MAX = 900   # alcanza para la ficha en un celular con pantalla de alta densidad


def huella(ruta):
    # La misma que usa git para el archivo: si la foto no cambió, la huella tampoco
    with open(ruta, 'rb') as f:
        datos = f.read()
    return hashlib.sha1(b'blob %d\0' % len(datos) + datos).hexdigest()[:10]


def nombre_recorte(foto, usados):
    base = os.path.splitext(foto)[0]
    nombre, n = base + '.webp', 2
    while nombre in usados:            # "X.JPG" y "X.jpg" no se pisan
        nombre, n = '%s-%d.webp' % (base, n), n + 1
    return nombre


def recortar(sesion, ruta):
    from rembg import remove
    im = ImageOps.exif_transpose(Image.open(ruta)).convert('RGB')
    cut = remove(im, session=sesion)
    # Limpia el velo casi transparente que queda alrededor y deja firme lo que es botella
    alfa = cut.getchannel('A').point(lambda v: 0 if v < 10 else (255 if v > 245 else v))
    cut.putalpha(alfa)
    caja = alfa.point(lambda v: 255 if v > 24 else 0).getbbox()
    if not caja:
        return None, 'no encontró ningún producto'
    ancho, alto = caja[2] - caja[0], caja[3] - caja[1]
    ocupa = ancho * alto / float(im.width * im.height)
    if ocupa < 0.03:
        return None, 'el recorte quedó demasiado chico (%.0f%%)' % (ocupa * 100)
    if ancho > 0.97 * im.width and alto > 0.97 * im.height:
        return None, 'no pudo separar el fondo'
    margen = round(0.02 * max(ancho, alto))
    caja = (max(0, caja[0] - margen), max(0, caja[1] - margen),
            min(im.width, caja[2] + margen), min(im.height, caja[3] + margen))
    cut = cut.crop(caja)
    cut.thumbnail((LADO_MAX, LADO_MAX), Image.LANCZOS)
    return cut, None


def main():
    todas = '--todas' in sys.argv
    os.makedirs(CARPETA, exist_ok=True)
    indice = {}
    if os.path.exists(INDICE) and not todas:
        with open(INDICE, encoding='utf-8') as f:
            indice = json.load(f)

    fotos = sorted(f for f in os.listdir(RAIZ)
                   if os.path.isfile(os.path.join(RAIZ, f)) and f.lower().endswith(EXTENSIONES))

    # Las fotos que ya no están en el repo se sacan del índice (y su recorte se borra)
    for foto in [f for f in indice if f not in fotos]:
        viejo = os.path.join(CARPETA, indice.pop(foto)[0])
        if os.path.exists(viejo):
            os.remove(viejo)
        print('borrado (ya no está la foto):', foto)

    pendientes = []
    for foto in fotos:
        h = huella(os.path.join(RAIZ, foto))
        hecho = indice.get(foto)
        if hecho and hecho[1] == h and os.path.exists(os.path.join(CARPETA, hecho[0])):
            continue
        pendientes.append((foto, h))
    print('%d fotos, %d para recortar' % (len(fotos), len(pendientes)), flush=True)
    if not pendientes:
        limpiar(indice)
        return

    from rembg import new_session
    sesion = new_session(MODELO)
    dudosas, t0 = [], time.time()
    for i, (foto, h) in enumerate(pendientes, 1):
        try:
            cut, problema = recortar(sesion, os.path.join(RAIZ, foto))
        except Exception as e:          # una foto rota no frena al resto
            cut, problema = None, 'error: %s' % e
        if problema:
            dudosas.append((foto, problema))
            indice.pop(foto, None)
            print('[%d/%d] %s → SIN RECORTE: %s' % (i, len(pendientes), foto, problema), flush=True)
            continue
        anterior = indice.get(foto)
        usados = {v[0] for k, v in indice.items() if k != foto}
        nombre = anterior[0] if anterior and anterior[0] not in usados else nombre_recorte(foto, usados)
        cut.save(os.path.join(CARPETA, nombre), 'WEBP', quality=82, method=6)
        indice[foto] = [nombre, h]
        print('[%d/%d] %s → %s (%dx%d)' % (i, len(pendientes), foto, nombre, cut.width, cut.height), flush=True)
        if i % 10 == 0:                 # guarda a cada rato: si se corta, no se pierde lo hecho
            guardar(indice)
    guardar(indice)
    limpiar(indice)
    print('listo en %.0f s. Recortadas: %d. Sin recorte: %d' % (time.time() - t0, len(pendientes) - len(dudosas), len(dudosas)))
    for foto, problema in dudosas:
        print('   -', foto, '→', problema)


def limpiar(indice):
    # Borra los recortes que ya no corresponden a ninguna foto
    en_uso = {v[0] for v in indice.values()} | {'index.json'}
    for archivo in os.listdir(CARPETA):
        if archivo not in en_uso:
            os.remove(os.path.join(CARPETA, archivo))
            print('borrado (sin foto):', archivo)


def guardar(indice):
    with open(INDICE, 'w', encoding='utf-8') as f:
        json.dump(dict(sorted(indice.items())), f, ensure_ascii=False, separators=(',', ':'))
        f.write('\n')


if __name__ == '__main__':
    main()
