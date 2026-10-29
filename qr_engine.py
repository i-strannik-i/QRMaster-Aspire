"""Offline QR encoding and closed machining vectors for QRMaster Aspire."""
import math
import hashlib
import sys
from pathlib import Path
from urllib.parse import urlsplit

import segno
from shapely.geometry import box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from version import VERSION


def number(options, key, default, minimum, maximum):
    value = float(options.get(key, str(default)).replace(',', '.'))
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f'{key}: допустимое значение {minimum}…{maximum} мм.')
    return value


def generate(options):
    url = options.get('url', '').strip()
    if not url or any(c.isspace() or ord(c) < 32 for c in url):
        raise ValueError('Вставьте ссылку без пробелов и переносов строк.')
    if '://' not in url:
        url = 'https://' + url
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in ('http', 'https') or not parsed.hostname:
        raise ValueError('Нужна ссылка http:// или https:// с именем сайта.')
    cutter = number(options, 'cutter', 1, 0.01, 100)
    x = y = 0
    try:
        qr = segno.make_qr(url, error='h', encoding='utf-8', eci=True,
                           boost_error=False)
    except segno.DataOverflowError as exc:
        raise ValueError('Ссылка слишком длинная для одного QR-кода.') from exc
    matrix = [list(row) for row in qr.matrix_iter(border=0, scale=1, verbose=True)]
    n = len(matrix)
    matrix_hash = hashlib.sha256(bytes(v for row in qr.matrix for v in row)).hexdigest()
    # Leave 10% clearance for pocketing, then round upwards to 0.01 mm.
    required = cutter * 1.10 * (n + 8)
    size = math.ceil(required * 100) / 100
    if size > 10000:
        raise ValueError(f'Для этой фрезы нужен QR {size:.2f} мм — больше предела 10000 мм. '
                         'Выберите меньшую фрезу или сократите ссылку.')
    pitch = size / (n + 8)
    squares = []
    for row, values in enumerate(matrix):
        for col, value in enumerate(values):
            if not value >> 8:
                continue
            squares.append(box(col, n - row - 1, col + 1, n - row))
    merged = unary_union(squares)
    polygons = ([merged] if merged.geom_type == 'Polygon' else list(merged.geoms)) if squares else []
    contours = []
    for polygon in polygons:
        polygon = orient(polygon.simplify(0), sign=1)
        for ring in [polygon.exterior, *polygon.interiors]:
            contours.append([[x + (a + 4) * pitch, y + (b + 4) * pitch]
                             for a, b in ring.coords])
    resize_message = f'Автоматический размер QR {size:g} × {size:g} мм под фрезу {cutter:g} мм. '
    return dict(ok=True, version=VERSION, size=size,
                x=x, y=y, modules=n, pitch=pitch, cutter=cutter, matrix_hash=matrix_hash,
                diameter=pitch, contours=contours,
                count=len(contours), shape='squares',
                message=resize_message + f'QR {n} × {n}; шаг {pitch:.3f} мм; '
                        f'элемент {pitch:.3f} мм; поле {4*pitch:.2f} мм.')


def lua(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return '"' + ''.join(f'\\{b:03d}' for b in value.encode('utf-8')) + '"'
    if isinstance(value, list):
        return '{' + ','.join(lua(v) for v in value) + '}'
    if isinstance(value, dict):
        return '{' + ','.join(f'[{lua(k)}]={lua(v)}' for k, v in value.items()) + '}'
    raise TypeError(type(value))


def main():
    request, output = map(Path, sys.argv[1:3])
    try:
        options = dict(line.split('=', 1) for line in
                       request.read_text(encoding='utf-8-sig').splitlines() if '=' in line)
        if options.get('task') == 'update_check':
            from updates import check_update
            result = check_update()
        else:
            result = generate(options)
    except Exception as exc:
        result = dict(ok=False, message=str(exc))
    output.write_text('return ' + lua(result), encoding='ascii')


if __name__ == '__main__':
    main()
