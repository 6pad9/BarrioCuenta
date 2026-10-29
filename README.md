# BarrioCuenta para Render y Neon

Abre docs/MANUAL-DESPLIEGUE-GRATUITO.html.

Neon: proyecto super-base-33383770, rama production. El esquema ya está aplicado; no se cargaron muestras. Las conexiones privadas están en .env.local de la copia de nube y no están en este ZIP. Configura DATABASE_URL y DATABASE_URL_UNPOOLED en Render, además de Brevo y el primer administrador.

Pruebas: python -B -m unittest discover -s tests -v

El informe docs/NEON-CONEXION.md conserva los comandos, resultados y pendientes.
