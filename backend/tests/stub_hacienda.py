"""
Una Hacienda de mentira para la pila de pruebas (F7, T-708, T-709).

Contesta lo que contesta la de verdad —el token, el 202 del envío, el veredicto
con su `respuesta-xml`— sin validar nada, para que la batería HTTP pueda ver un
comprobante recorrer `numerado → firmado → enviado → aceptado` dentro del
contenedor, con Vault y MinIO de verdad y sin internet.

Lo que hace está escrito de antemano y se gobierna con dos cosas:

* **La contraseña.** `mala` → el IdP contesta `invalid_grant` (credenciales
  rechazadas). Cualquier otra → un token.
* **La clave.** Si el `POST /recepcion` trae una clave que termina en `00`,
  responde 400 con `X-Error-Cause` (estructura inválida); la consulta de una
  clave que termina en `99` devuelve `rechazado`; el resto, `aceptado` desde la
  primera consulta.

Corre con la biblioteca estándar: `python tests/stub_hacienda.py 8080`.
"""

from __future__ import annotations

import base64
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

RESPUESTA = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<MensajeHacienda xmlns="https://cdn.comprobanteselectronicos.go.cr/xml-schemas/v4.4/mensajeHacienda">'
    "<Clave>{clave}</Clave><NombreEmisor>Prueba</NombreEmisor><TipoIdentificacionEmisor>02</TipoIdentificacionEmisor>"
    "<NumeroCedulaEmisor>3101702934</NumeroCedulaEmisor><FechaEmisionDoc>2026-10-03T00:13:39-06:00</FechaEmisionDoc>"
    "<Mensaje>{mensaje}</Mensaje><DetalleMensaje>{detalle}</DetalleMensaje>"
    "<MontoTotalImpuesto>0</MontoTotalImpuesto><TotalFactura>0</TotalFactura>"
    "</MensajeHacienda>"
)

recibidas: dict[str, dict] = {}


class Hacienda(BaseHTTPRequestHandler):
    def log_message(self, formato, *args):  # noqa: D401 — callado: el registro es del contenedor
        pass

    def _json(self, codigo: int, cuerpo: dict, cabeceras: dict | None = None) -> None:
        datos = json.dumps(cuerpo).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        for k, v in (cabeceras or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(datos)

    def _token(self) -> str:
        """El token del `Bearer`, o vacío: un `Bearer ` sin nada es no tenerlo."""
        auth = self.headers.get("Authorization", "")
        return auth[7:].strip() if auth.startswith("Bearer ") else ""

    def _leer(self) -> bytes:
        largo = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(largo) if largo else b""

    def do_POST(self) -> None:  # noqa: N802 — nombre que exige http.server
        if self.path.endswith("/token"):
            campos = parse_qs(self._leer().decode("utf-8"))
            if campos.get("password", [""])[0] == "mala":
                self._json(401, {"error": "invalid_grant", "error_description": "Invalid user credentials"})
                return
            self._json(200, {"access_token": "token-de-prueba", "expires_in": 300, "token_type": "Bearer"})
            return
        if self.path.rstrip("/").endswith("/recepcion"):
            if not self._token():
                self._json(401, {"error": "unauthorized"})
                return
            try:
                cuerpo = json.loads(self._leer().decode("utf-8"))
            except ValueError:
                self._json(400, {}, {"X-Error-Cause": "cuerpo ilegible"})
                return
            clave = str(cuerpo.get("clave") or "")
            if len(clave) != 50 or "comprobanteXml" not in cuerpo:
                self._json(400, {}, {"X-Error-Cause": "clave o comprobante ausentes"})
                return
            if clave.endswith("00"):
                self._json(400, {}, {"X-Error-Cause": "El XML no cumple con la estructura"})
                return
            if clave in recibidas:
                self._json(400, {}, {"X-Error-Cause": "clave duplicada"})
                return
            recibidas[clave] = cuerpo
            self._json(202, {})
            return
        self._json(404, {})

    def do_GET(self) -> None:  # noqa: N802
        partes = self.path.rstrip("/").split("/")
        if len(partes) >= 2 and partes[-2] == "recepcion":
            if not self._token():
                self._json(401, {"error": "unauthorized"})
                return
            clave = partes[-1]
            if clave not in recibidas:
                self._json(404, {})
                return
            rechazada = clave.endswith("99")
            xml = RESPUESTA.format(
                clave=clave,
                mensaje="3" if rechazada else "1",
                detalle="Rechazado por la prueba" if rechazada else "Aceptado por la prueba",
            )
            self._json(
                200,
                {
                    "clave": clave,
                    "fecha": "2026-10-03T00:13:39-06:00",
                    "ind-estado": "rechazado" if rechazada else "aceptado",
                    "respuesta-xml": base64.b64encode(xml.encode("utf-8")).decode("ascii"),
                },
            )
            return
        if self.path.startswith("/health"):
            self._json(200, {"status": "ok", "recibidas": len(recibidas)})
            return
        self._json(404, {})


def main(puerto: int) -> None:
    servidor = ThreadingHTTPServer(("0.0.0.0", puerto), Hacienda)
    print(f"Hacienda de mentira en :{puerto}", flush=True)
    servidor.serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8080)
