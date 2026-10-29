# Adaptación para Render Neon y Brevo

Fecha: 29 de octubre de 2026.

Se añadieron backend/cloud.py para el arranque público y administrador inicial, backend/mailer.py para Brevo mediante HTTPS y compatibilidad con SMTP local, conversión de DATABASE_URL al controlador psycopg y conexiones con comprobación previa para PostgreSQL suspendido. La configuración pública exige producción, PostgreSQL externo con TLS, dirección HTTPS y credenciales del proveedor de correo.

Dockerfile compila React con Node 22 y ejecuta Python 3.12/Gunicorn en un usuario sin privilegios, usando el puerto asignado por Render. render.yaml declara un solo servicio Free, sin base Render ni worker de pago. El primer administrador se crea únicamente en una base vacía y nunca se restablece al volver a desplegar.

AUTO_PROCESS_CUTS=1 recupera cortes en consultas autenticadas de cuentas/estados, con intervalo configurable y auditoría como Sistema. No mantiene el servicio despierto ni emite a la hora exacta mientras Render duerme. Los vínculos públicos usan RENDER_EXTERNAL_URL automáticamente o PUBLIC_URL explícita. El reloj de pruebas se oculta en la navegación pública.

Validación: 58 pruebas unittest aprobadas; integración en un esquema PostgreSQL temporal de inicialización, 2FA Brevo simulado, tienda, negocio, catálogo, cuenta, venta y estados; compilación de React; render.yaml validado con el esquema oficial de Render; manual HTML revisado a 1400 y 390 px.

No se construyó la imagen Docker en este equipo porque no tiene Docker instalado. El build real debe ejecutarse al publicar en Render. Se verificó Neon real mediante servidor HTTP y una rama aislada, y se aplicó el esquema probado a production. No se configuraron credenciales reales de Brevo ni se envió correo real ni se publicó la web en internet. Esas comprobaciones quedan incluidas en el manual de puesta en marcha.

La instalación local conserva su base y usa Mailpit. El ZIP público omite bases, claves, certificados, dependencias locales, respaldos y registros. La ruta del manual es docs/MANUAL-DESPLIEGUE-GRATUITO.html; también se entrega su fuente Markdown.
