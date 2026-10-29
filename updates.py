"""Read public GitHub release metadata without credentials or executing remote code."""
import json
import re
import urllib.request

from version import VERSION

REPOSITORY = 'i-strannik-i/QRMaster-Aspire'
API_URL = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
RELEASE_URL = f'https://github.com/{REPOSITORY}/releases/latest'


def version_tuple(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', value)
    return tuple(map(int, match.groups())) if match else None


def check_update():
    try:
        request = urllib.request.Request(API_URL, headers={
            'Accept': 'application/vnd.github+json', 'User-Agent': f'QRMaster-Aspire/{VERSION}'})
        with urllib.request.urlopen(request, timeout=3) as response:
            data = json.loads(response.read(256_000))
        remote = version_tuple(data.get('tag_name', ''))
        available = bool(remote and remote > version_tuple(VERSION)
                         and not data.get('draft') and not data.get('prerelease'))
        latest = '.'.join(map(str, remote)) if remote else ''
        message = (f'Доступна новая версия {latest}. Установлена {VERSION}.' if available
                   else f'Установлена версия {VERSION}. Новых обновлений нет.')
        return dict(ok=True, available=available, latest=latest, message=message,
                    release_url=RELEASE_URL)
    except Exception:
        return dict(ok=True, available=False, latest='', release_url=RELEASE_URL,
                    message=f'Версия {VERSION}. Проверка обновлений недоступна; генератор работает без интернета.')
