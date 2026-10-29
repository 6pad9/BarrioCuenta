# Administradores y contraseñas

## Crear hasta cinco administradores (o más)
1. Inicia sesión con un administrador del sistema.
2. Abre **Usuarios y accesos > Crear administrador**.
3. Selecciona **Administrador del sistema** e indica nombre, correo distinto y contraseña inicial.
4. Guarda y repite para las demás personas. Cada cuenta recibe su propio código de acceso por correo.

Para un administrador de negocio, selecciona ese perfil y una tienda activa.

## Recuperar una contraseña
1. En la pantalla de acceso, pulsa **Olvidé mi contraseña**.
2. Escribe el correo registrado y pulsa **Enviar enlace**.
3. Revisa tu correo y spam. Abre el enlace antes de 15 minutos.
4. Escribe y confirma la nueva contraseña; luego inicia sesión y verifica el código enviado por correo.

El enlace funciona una sola vez. Solicitar otro invalida el anterior. Por privacidad se muestra el mismo aviso aunque el correo no tenga cuenta. Las cuentas pendientes de invitación deben activarse mediante su invitación.

## Cambiar una contraseña conocida
Pulsa **Mi contraseña** en la barra superior. Escribe la actual y confirma la nueva. El cambio cierra todas las sesiones de esa cuenta.

Las contraseñas nuevas de administradores y las de cambio o recuperación requieren de 12 a 256 caracteres, mayúscula, minúscula y número. Los botones con un ojo permiten mostrar y ocultar el texto; no muestran contraseñas guardadas.

## Despliegue
No se necesitan tablas nuevas ni borrar datos. El despliegue usa las variables actuales de Brevo y PUBLIC_URL (configurada automáticamente desde RENDER_EXTERNAL_URL). RESET_SECONDS es opcional y vale 900 por defecto. No publiques claves ni archivos .env.
