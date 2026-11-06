"""Fixed HTTPS destination; no credentials or redirects on a hall computer."""
import http.client
import json

from .diagnostic_upload import UploadError, _number, _uuid

HOST = 'diag.shmyrev52.ru'
BASE = '/v1/reports/'


class Relay:
    def put(self, report_id, report):
        _uuid(report_id)
        conn = None
        try:
            body = json.dumps({'report': report}, ensure_ascii=False, allow_nan=False).encode('utf-8')
            if len(body) > 65536:
                raise UploadError('size')
            conn = http.client.HTTPSConnection(HOST, timeout=10)
            conn.request('PUT', BASE + report_id, body=body, headers={
                'Content-Type': 'application/json', 'Accept': 'application/json',
                'User-Agent': 'ma2-panel-diagnostics'})
            response = conn.getresponse()
            if response.status == 409:
                raise UploadError('relay_conflict')
            if response.status == 429 or response.status == 507:
                raise UploadError('relay_limit')
            if not 200 <= response.status < 300:
                raise UploadError('relay_http')
            raw = response.read(8193)
            if len(raw) > 8192:
                raise UploadError('relay_response')
            data = json.loads(raw)
            if (not isinstance(data, dict) or data.get('report_id') != report_id
                    or data.get('state') not in ('queued', 'pending', 'sent')
                    or set(data) - {'report_id', 'state', 'number'}):
                raise UploadError('relay_response')
            if data['state'] == 'sent':
                _number(data)
            elif 'number' in data:
                raise UploadError('relay_response')
            return data
        except UploadError:
            raise
        except (ValueError, UnicodeError, TypeError, RecursionError):
            raise UploadError('relay_response') from None
        except Exception:
            raise UploadError('network') from None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
