# BarrioCuenta · Entrega académica

Aplicación publicada: https://barriocuenta.onrender.com

Abre **docs/entrega/INICIO-ENTREGA-FINAL.html** para el manual de uso, guion de exposición, matriz RF-01 a RF-12, comprobación financiera y capturas.

La entrega complementa el informe tp_vf.docx de análisis y diseño; documenta la construcción posterior. No se creó una cuenta para la profesora.

## Verificación

- `python -m unittest discover -s tests -v`
- `npm ci` y `npm run build`

## Configuración

Render aloja la aplicación; PostgreSQL está en Neon y el correo usa Brevo. Usa `.env.render.example` como referencia y configura claves privadas en el proveedor. No se incluyen conexiones ni contraseñas reales.

La publicación contiene tiendas y datos ficticios DEMO, además de dos escenarios de exposición en Mi Tienda Test. El ZIP no exporta la base de datos pública. `backend.seed` crea ejemplos solo en una base local vacía; `scripts/presentation_demo.py` es una función de carga explícita probada, no se ejecuta al arrancar el servidor.

Instalación local y accesos ficticios: ver el manual final. Despliegue: docs/MANUAL-DESPLIEGUE-GRATUITO.html. Sus notas de publicación pendiente documentan el procedimiento inicial; la dirección pública ya está operativa.
