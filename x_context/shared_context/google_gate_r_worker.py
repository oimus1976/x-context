"""Private GET worker for the separately guarded Gate R caller; no retry."""
import json
import re
import sys
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result

def _bad_constant(value):
    raise ValueError
def main():
    try:
        data = sys.stdin.buffer.read(65537)
        if len(data) > 65536:
            raise ValueError
        arg = json.loads(data)
        if set(arg) != {'service', 'path', 'query', 'token', 'timeout'}:
            raise ValueError
        service, path, query, token, timeout = (arg[k] for k in ('service','path','query','token','timeout'))
        valid = ((service == 'drive' and (path == 'about' or re.fullmatch(r'files(?:/[A-Za-z0-9_-]{1,200}(?:/permissions)?)?', path)))
                 or (service == 'docs' and re.fullmatch(r'documents/[A-Za-z0-9_-]{1,200}', path)))
        if (not valid or not isinstance(query, dict) or not isinstance(token, str)
                or not token or any(ord(ch) < 33 or ord(ch) > 126 for ch in token)
                or not isinstance(timeout, (int, float)) or timeout <= 0 or timeout > 30):
            raise ValueError
        base = {'drive':'https://www.googleapis.com/drive/v3/', 'docs':'https://docs.googleapis.com/v1/'}[service]
        url = base + path + ('?' + urlencode(query) if query else '')
        request = Request(url, method='GET', headers={'Authorization':'Bearer ' + token, 'Accept':'application/json'})
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout) as response:
            data = response.read(1048577)
            if response.status != 200 or len(data) > 1048576:
                raise ValueError
        value = json.loads(data, object_pairs_hook=_unique_pairs, parse_constant=_bad_constant)
        if not isinstance(value, dict):
            raise ValueError
        sys.stdout.buffer.write(json.dumps(value, ensure_ascii=True, allow_nan=False).encode('ascii'))
        return 0
    except Exception:
        return 1

if __name__ == '__main__':
    sys.exit(main())
